import os
import time
import logging
from flask import Flask, request, jsonify, render_template
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone
import pytz  # Add this import for timezone handling
from prometheus_flask_exporter import PrometheusMetrics
from sqlalchemy.exc import SQLAlchemyError
from prometheus_client import Gauge, Counter, Histogram

# Logging Configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Prometheus Metrics Initialization
metrics = PrometheusMetrics(app)

# Database Configuration
db_uri = os.getenv(
    'DB_URI',
    'mysql+mysqlconnector://flask_user:password@mysql/flask_app_db'
)
app.config['SQLALCHEMY_DATABASE_URI'] = db_uri
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_recycle': 280,
    'pool_pre_ping': True
}

db = SQLAlchemy(app)

# Specify your local timezone (e.g., 'Asia/Jakarta' for Indonesia)
LOCAL_TIMEZONE = pytz.timezone('Asia/Jakarta')

# Database Model
class Absensi(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nrp = db.Column(db.String(20), nullable=False)
    nama = db.Column(db.String(100), nullable=False)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(pytz.utc))
    
    def to_dict(self):
        # Convert timestamp to local timezone (Asia/Jakarta)
        local_timezone = pytz.timezone('Asia/Jakarta')
        local_timestamp = self.timestamp.astimezone(local_timezone)
        return {
            'id': self.id,
            'nrp': self.nrp,
            'nama': self.nama,
            'timestamp': local_timestamp.strftime('%Y-%m-%d %H:%M:%S %Z')
        }


# Wait for Database Connection
def wait_for_database(max_retries=5, delay=5):
    """Wait for the database to be available."""
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
    """Create database tables if not already present."""
    try:
        with app.app_context():
            db.create_all()
        logger.info("Database tables created successfully.")
    except Exception as e:
        logger.error(f"Error creating database tables: {e}")
        raise


# Metrics for process memory and CPU
PROCESS_CPU_SECONDS_TOTAL = Counter('process_cpu_seconds_total', 'Total user and system CPU time spent in seconds')
PROCESS_MEMORY_BYTES = Gauge('process_resident_memory_bytes', 'Resident memory size in bytes')

# Register custom metrics for the process
@metrics.gauge('process_cpu_seconds_total', 'Total user and system CPU time spent in seconds')
def track_cpu_usage():
    # You can add logic to track CPU usage over time, if needed
    return 0  # Return the current CPU usage (e.g., from psutil)

@metrics.gauge('process_resident_memory_bytes', 'Resident memory size in bytes')
def track_memory_usage():
    # You can add logic to track memory usage over time, if needed
    return 0  # Return the current memory usage (e.g., from psutil)

# Routes
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/health', methods=['GET'])
def health_check():
    """Health check to monitor the app status."""
    try:
        with app.app_context():
            db.session.execute('SELECT 1')
        return jsonify({'status': 'healthy', 'app_number': os.getenv('APP_NUMBER', '1')}), 200
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({'status': 'unhealthy', 'error': str(e)}), 500


@app.route('/absensi', methods=['POST'])
def create_absensi():
    """Add a new attendance record."""
    try:
        data = request.json
        if not data or 'nrp' not in data or 'nama' not in data:
            return jsonify({'message': 'Input tidak valid'}), 400

        # Create the new Absensi record
        new_absensi = Absensi(nrp=data['nrp'], nama=data['nama'])
        
        # Use db.session to manage the transaction
        db.session.add(new_absensi)
        db.session.commit()

        return jsonify({'message': 'Absensi berhasil ditambahkan', 'data': new_absensi.to_dict()}), 200
    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error(f"SQLAlchemy error during create_absensi: {e}")
        return jsonify({'message': 'Gagal menambahkan absensi', 'error': str(e)}), 500
    except Exception as e:
        logger.error(f"Unexpected error during create_absensi: {e}")
        return jsonify({'message': 'An unexpected error occurred', 'error': str(e)}), 500


@app.route('/absensi', methods=['GET'])
def get_absensi():
    """Get all attendance records."""
    try:
        with app.app_context():
            absensi_list = Absensi.query.order_by(Absensi.timestamp.desc()).all()
        logger.info(f"Fetched {len(absensi_list)} absensi records.")
        return jsonify({
            'message': 'Berhasil mengambil data absensi',
            'total': len(absensi_list),
            'data': [absensi.to_dict() for absensi in absensi_list]
        }), 200
    except SQLAlchemyError as e:
        logger.error(f"SQLAlchemy error during get_absensi: {e}")
        return jsonify({
            'message': 'Gagal mengambil data absensi', 
            'error': str(e)
        }), 500
    except Exception as e:
        logger.error(f"Unexpected error during get_absensi: {e}")
        return jsonify({
            'message': 'Terjadi kesalahan tidak terduga', 
            'error': str(e)
        }), 500


@app.route('/absensi/<int:id>', methods=['PUT'])
def update_absensi(id):
    """Update an existing attendance record."""
    try:
        data = request.json
        # Cari absensi berdasarkan id
        absensi = Absensi.query.get(id)
        if not absensi:
            return jsonify({'message': 'Absensi tidak ditemukan'}), 404

        # Perbarui field berdasarkan data yang diberikan
        absensi.nrp = data.get('nrp', absensi.nrp)
        absensi.nama = data.get('nama', absensi.nama)

        # Commit perubahan ke database
        db.session.commit()

        # Fetch the updated record
        updated_absensi = Absensi.query.get(id)
        
        return jsonify({'message': 'Absensi berhasil diperbarui', 'data': updated_absensi.to_dict()}), 200
    except SQLAlchemyError as e:
        db.session.rollback()  # Rollback jika terjadi kesalahan
        logger.error(f"SQLAlchemy error during update_absensi: {e}")
        return jsonify({'message': 'Gagal memperbarui absensi', 'error': str(e)}), 500
    except Exception as e:
        logger.error(f"Unexpected error during update_absensi: {e}")
        return jsonify({'message': 'An unexpected error occurred', 'error': str(e)}), 500


@app.route('/absensi/<int:id>', methods=['DELETE'])
def delete_absensi(id):
    """Delete an attendance record."""
    try:
        with app.app_context():
            absensi = Absensi.query.get(id)
            if not absensi:
                return jsonify({
                    'message': 'Absensi tidak ditemukan', 
                    'error': f'Tidak ada data dengan ID {id}'
                }), 404

            db.session.delete(absensi)
            db.session.commit()

        return jsonify({
            'message': 'Absensi berhasil dihapus',
            'deleted_id': id
        }), 200
    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error(f"SQLAlchemy error during delete_absensi: {e}")
        return jsonify({
            'message': 'Gagal menghapus absensi', 
            'error': str(e)
        }), 500
    except Exception as e:
        logger.error(f"Unexpected error during delete_absensi: {e}")
        return jsonify({
            'message': 'Terjadi kesalahan tidak terduga', 
            'error': str(e)
        }), 500

# Main Application
if __name__ == '__main__':
    if wait_for_database():
        create_tables()
        app.run(host='0.0.0.0', port=5000)
    else:
        logger.critical("Tidak dapat terhubung ke database. Aplikasi berhenti.")
        exit(1)
