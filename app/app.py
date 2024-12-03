from flask import Flask, request, jsonify, render_template
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os
import time
import pytz
import logging
import psutil
from prometheus_flask_exporter import PrometheusMetrics
from prometheus_client import Counter, Histogram, Gauge
from sqlalchemy.exc import SQLAlchemyError

# Logging Configuration
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Prometheus Metrics Initialization
metrics = PrometheusMetrics(app)
metrics.info("app_info", "Application Info", version="1.0.0")

# Prometheus Custom Metrics
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
ERROR_COUNT = Counter(
    "flask_request_errors_total",
    "Total number of errors by endpoint and HTTP status",
    ["endpoint", "http_status"],
)
LATENCY_PERCENTILES = Histogram(
    "flask_request_duration_seconds",
    "Request duration distribution",
    buckets=[0.1, 0.25, 0.5, 0.75, 1, 2, 5, 10],
)
CPU_USAGE = Gauge("cpu_usage_percent", "CPU usage percentage")
MEMORY_USAGE = Gauge("memory_usage_percent", "Memory usage percentage")

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


# Monitoring Middleware
@app.before_request
def before_request():
    request.start_time = time.time()


@app.after_request
def after_request(response):
    if hasattr(request, "start_time"):
        latency = time.time() - request.start_time
        REQUEST_LATENCY.labels(endpoint=request.endpoint, method=request.method).observe(latency)
        LATENCY_PERCENTILES.observe(latency)
        REQUEST_COUNT.labels(endpoint=request.endpoint, method=request.method, http_status=response.status_code).inc()

    if response.status_code >= 400:
        ERROR_COUNT.labels(endpoint=request.endpoint, http_status=response.status_code).inc()

    CPU_USAGE.set(psutil.cpu_percent(interval=0.1))
    MEMORY_USAGE.set(psutil.virtual_memory().percent)

    return response


# Wait for Database Connection
def wait_for_database(max_retries=5, delay=5):
    for attempt in range(1, max_retries + 1):
        try:
            with app.app_context():
                with db.engine.connect() as connection:
                    logger.info("Database connected successfully.")
                    return True
        except Exception as e:
            logger.warning(f"Database connection attempt {attempt} failed: {e}")
            time.sleep(delay)
    logger.error("Max retries reached. Cannot connect to the database.")
    return False


# Create Tables if Needed
def create_tables():
    try:
        with app.app_context():
            db.create_all()
        logger.info("Database tables created successfully.")
    except Exception as e:
        logger.error(f"Error creating database tables: {e}")
        raise


# Routes
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/health", methods=["GET"])
def health_check():
    try:
        with app.app_context():
            db.session.execute("SELECT 1")
        return jsonify({"status": "healthy", "app_number": os.getenv("APP_NUMBER", "1")}), 200
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({"status": "unhealthy", "error": str(e)}), 500


@app.route("/absensi", methods=["POST"])
def create_absensi():
    try:
        data = request.json
        if not data or "nrp" not in data or "nama" not in data:
            return jsonify({"message": "Input tidak valid"}), 400

        new_absensi = Absensi(nrp=data["nrp"], nama=data["nama"])
        db.session.add(new_absensi)
        db.session.commit()

        return jsonify({"message": "Absensi berhasil ditambahkan", "data": new_absensi.to_dict()}), 200
    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error(f"SQLAlchemy error during create_absensi: {e}")
        return jsonify({"message": "Gagal menambahkan absensi", "error": str(e)}), 500
    except Exception as e:
        logger.error(f"Unexpected error during create_absensi: {e}")
        return jsonify({"message": "An unexpected error occurred", "error": str(e)}), 500


@app.route("/absensi", methods=["GET"])
def get_absensi():
    try:
        absensi_list = Absensi.query.order_by(Absensi.timestamp.desc()).all()
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


@app.route('/absensi/<int:id>', methods=['PUT'])
def update_absensi(id):
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
def delete_absensi(id):
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


if __name__ == "__main__":
    if wait_for_database():
        create_tables()
        app.run(host="0.0.0.0", port=5000)
    else:
        logger.critical("Tidak dapat terhubung ke database. Aplikasi berhenti.")
        exit(1)
