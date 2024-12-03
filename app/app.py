import os
import time
import logging
from flask import Flask, request, jsonify, render_template
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import pytz
from prometheus_flask_exporter import PrometheusMetrics
from prometheus_client import Counter, Histogram
from sqlalchemy.exc import SQLAlchemyError

# Logging Configuration
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Prometheus Metrics Initialization
metrics = PrometheusMetrics(app)
metrics.info("app_info", "Application Info", version="1.0.0")

# Custom Prometheus Metrics
REQUEST_COUNT = Counter(
    "flask_request_operations_total",
    "Total number of requests by endpoint, method, and HTTP status",
    ["endpoint", "method", "http_status"],
)
REQUEST_LATENCY = Histogram(
    "flask_request_latency_seconds",
    "Request latency in seconds",
    ["endpoint", "method"],
)
DB_QUERY_LATENCY = Histogram(
    "db_query_latency_seconds", "Database query latency in seconds", ["operation"]
)

# Database Configuration
db_uri = os.getenv(
    "DB_URI",
    "mysql+mysqlconnector://flask_user:password@mysql/flask_app_db",
)
app.config["SQLALCHEMY_DATABASE_URI"] = db_uri
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 280,
    "pool_pre_ping": True,
}

db = SQLAlchemy(app)

# Timezone Configuration
LOCAL_TIMEZONE = pytz.timezone("Asia/Jakarta")

# Database Model
class Absensi(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nrp = db.Column(db.String(20), nullable=False)
    nama = db.Column(db.String(100), nullable=False)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(pytz.utc))

    def to_dict(self):
        local_timestamp = self.timestamp.astimezone(LOCAL_TIMEZONE)
        return {
            "id": self.id,
            "nrp": self.nrp,
            "nama": self.nama,
            "timestamp": local_timestamp.strftime("%Y-%m-%d %H:%M:%S %Z"),
        }


# Monitor Function for Requests
def monitor_request(endpoint):
    """Decorator to measure request count and latency."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            method = request.method
            start_time = time.time()
            try:
                response = func(*args, **kwargs)
                status_code = response.status_code
            except Exception as e:
                status_code = 500
                raise e
            finally:
                latency = time.time() - start_time
                REQUEST_COUNT.labels(endpoint=endpoint, method=method, http_status=status_code).inc()
                REQUEST_LATENCY.labels(endpoint=endpoint, method=method).observe(latency)
            return response
        return wrapper
    return decorator


# Monitor Function for Database Operations
def monitor_db(operation):
    """Decorator to measure database query latency."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                return func(*args, **kwargs)
            finally:
                latency = time.time() - start_time
                DB_QUERY_LATENCY.labels(operation=operation).observe(latency)
        return wrapper
    return decorator


# Database Utility Functions
@monitor_db("create_tables")
def create_tables():
    """Create database tables if not already present."""
    with app.app_context():
        db.create_all()


# Routes
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/health", methods=["GET"])
@monitor_request("health_check")
def health_check():
    """Health check to monitor the app status."""
    try:
        with app.app_context():
            db.session.execute("SELECT 1")
        return jsonify({"status": "healthy", "app_number": os.getenv("APP_NUMBER", "1")}), 200
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({"status": "unhealthy", "error": str(e)}), 500


@app.route("/absensi", methods=["POST"])
@monitor_request("create_absensi")
def create_absensi():
    """Add a new attendance record."""
    try:
        data = request.json
        if not data or "nrp" not in data or "nama" not in data:
            return jsonify({"message": "Input tidak valid"}), 400

        @monitor_db("insert_absensi")
        def insert_absensi(data):
            new_absensi = Absensi(nrp=data["nrp"], nama=data["nama"])
            db.session.add(new_absensi)
            db.session.commit()
            return new_absensi

        new_absensi = insert_absensi(data)
        return jsonify({"message": "Absensi berhasil ditambahkan", "data": new_absensi.to_dict()}), 200
    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error(f"SQLAlchemy error during create_absensi: {e}")
        return jsonify({"message": "Gagal menambahkan absensi", "error": str(e)}), 500
    except Exception as e:
        logger.error(f"Unexpected error during create_absensi: {e}")
        return jsonify({"message": "An unexpected error occurred", "error": str(e)}), 500


@app.route("/absensi", methods=["GET"])
@monitor_request("get_absensi")
def get_absensi():
    """Get all attendance records."""
    try:
        @monitor_db("fetch_absensi")
        def fetch_absensi():
            return Absensi.query.order_by(Absensi.timestamp.desc()).all()

        absensi_list = fetch_absensi()
        return jsonify(
            {
                "message": "Berhasil mengambil data absensi",
                "total": len(absensi_list),
                "data": [absensi.to_dict() for absensi in absensi_list],
            }
        ), 200
    except SQLAlchemyError as e:
        logger.error(f"SQLAlchemy error during get_absensi: {e}")
        return jsonify({"message": "Gagal mengambil data absensi", "error": str(e)}), 500
    except Exception as e:
        logger.error(f"Unexpected error during get_absensi: {e}")
        return jsonify({"message": "Terjadi kesalahan tidak terduga", "error": str(e)}), 500


@app.route("/absensi/<int:id>", methods=["PUT"])
@monitor_request("update_absensi")
def update_absensi(id):
    """Update an existing attendance record."""
    try:
        data = request.json
        absensi = Absensi.query.get(id)
        if not absensi:
            return jsonify({'message': 'Absensi tidak ditemukan'}), 404

        absensi.nrp = data.get('nrp', absensi.nrp)
        absensi.nama = data.get('nama', absensi.nama)
        db.session.commit()
        return jsonify({'message': 'Absensi berhasil diperbarui', 'data': absensi.to_dict()}), 200
    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error(f"SQLAlchemy error during update_absensi: {e}")
        return jsonify({'message': 'Gagal memperbarui absensi', 'error': str(e)}), 500
    except Exception as e:
        logger.error(f"Unexpected error during update_absensi: {e}")
        return jsonify({'message': 'An unexpected error occurred', 'error': str(e)}), 500


@app.route("/absensi/<int:id>", methods=["DELETE"])
@monitor_request("delete_absensi")
def delete_absensi(id):
    """Delete an attendance record."""
    try:
        absensi = Absensi.query.get(id)
        if not absensi:
            return jsonify({"message": "Absensi tidak ditemukan"}), 404

        db.session.delete(absensi)
        db.session.commit()
        return jsonify({"message": "Absensi berhasil dihapus", "deleted_id": id}), 200
    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error(f"SQLAlchemy error during delete_absensi: {e}")
        return jsonify({"message": "Gagal menghapus absensi", "error": str(e)}), 500
    except Exception as e:
        logger.error(f"Unexpected error during delete_absensi: {e}")
        return jsonify({"message": "An unexpected error occurred", "error": str(e)}), 500


# Main Application
if __name__ == "__main__":
    with app.app_context():
        create_tables()
    app.run(host="0.0.0.0", port=5000)
