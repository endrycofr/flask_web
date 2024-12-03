import os
import time
import logging
from flask import Flask, request, jsonify, render_template, g
from flask_sqlalchemy import SQLAlchemy
import pytz
from datetime import datetime
from sqlalchemy.exc import SQLAlchemyError
from prometheus_flask_exporter import PrometheusMetrics
from prometheus_client import Counter

# Logging Configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
metrics = PrometheusMetrics(app)

# Database Configuration
db_uri = os.getenv('DB_URI', 'mysql+mysqlconnector://flask_user:password@mysql/flask_app_db')
app.config['SQLALCHEMY_DATABASE_URI'] = db_uri
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'pool_recycle': 280, 'pool_pre_ping': True}

db = SQLAlchemy(app)

# Timezone configuration
LOCAL_TIMEZONE = pytz.timezone('Asia/Jakarta')

# Database Model
class Absensi(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nrp = db.Column(db.String(20), nullable=False)
    nama = db.Column(db.String(100), nullable=False)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(pytz.utc))

    def to_dict(self):
        local_timestamp = self.timestamp.astimezone(LOCAL_TIMEZONE)
        return {
            'id': self.id,
            'nrp': self.nrp,
            'nama': self.nama,
            'timestamp': local_timestamp.strftime('%Y-%m-%d %H:%M:%S %Z')
        }

# Prometheus custom metrics
DATABASE_OPERATIONS = Counter('database_operations', 'Database operation count', ['operation_type', 'status'])
EXCEPTIONS = Counter('exceptions', 'Exception count', ['method', 'endpoint', 'exception_type'])

# Middleware for tracking request metrics
@app.before_request
def before_request():
    g.request_start_time = time.time()

@app.after_request
def after_request(response):
    record_request_end(
        method=request.method,
        endpoint=request.endpoint or request.path,
        start_time=g.request_start_time,
        status_code=response.status_code
    )
    return response

# Function to record the request end
def record_request_end(method, endpoint, start_time, status_code):
    """Record the end of a request, including its duration and status code."""
    duration = time.time() - start_time
    logger.info(f"Request {method} {endpoint} completed with status {status_code} in {duration:.4f} seconds.")
    # Optionally, you can also add Prometheus metrics here:
    # record_duration_metric(duration, status_code)

# Define the event processing logging function
def record_event_processing(event_type, status, duration):
    """Log the processing of an event, including its status and duration."""
    logger.info(f"Event '{event_type}' completed with status '{status}' in {duration:.4f} seconds.")
    # Optionally, you could also add Prometheus metrics here for event processing
    # record_event_metric(event_type, status, duration)

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/health', methods=['GET'])
def health_check():
    """Health check to monitor the app status."""
    start_time = time.time()
    try:
        with app.app_context():
            db.session.execute('SELECT 1')
        
        record_event_processing(
            event_type='health_check', 
            status='success', 
            duration=time.time() - start_time
        )
        
        return jsonify({'status': 'healthy', 'app_number': os.getenv('APP_NUMBER', '1')}), 200
    except Exception as e:
        record_event_processing(
            event_type='health_check', 
            status='failure', 
            duration=time.time() - start_time
        )
        
        logger.error(f"Health check failed: {e}")
        return jsonify({'status': 'unhealthy', 'error': str(e)}), 500

@app.route('/absensi', methods=['POST'])
def create_absensi():
    """Add a new attendance record."""
    start_time = time.time()
    try:
        data = request.json
        if not data or 'nrp' not in data or 'nama' not in data:
            record_event_processing(
                event_type='absensi_create', 
                status='validation_failed', 
                duration=time.time() - start_time
            )
            return jsonify({'message': 'Input tidak valid'}), 400

        new_absensi = Absensi(nrp=data['nrp'], nama=data['nama'])
        db.session.add(new_absensi)
        db.session.commit()

        record_event_processing(
            event_type='absensi_create', 
            status='success', 
            duration=time.time() - start_time
        )

        return jsonify({'message': 'Absensi berhasil ditambahkan', 'data': new_absensi.to_dict()}), 200
    except SQLAlchemyError as e:
        db.session.rollback()
        DATABASE_OPERATIONS.labels(operation_type='create', status='failure').inc()
        EXCEPTIONS.labels(method=request.method, endpoint=request.path, exception_type='SQLAlchemyError').inc()
        logger.error(f"SQLAlchemy error during create_absensi: {e}")
        return jsonify({'message': 'Gagal menambahkan absensi', 'error': str(e)}), 500
    except Exception as e:
        EXCEPTIONS.labels(method=request.method, endpoint=request.path, exception_type='Exception').inc()
        logger.error(f"Unexpected error during create_absensi: {e}")
        return jsonify({'message': 'An unexpected error occurred', 'error': str(e)}), 500

@app.route('/absensi', methods=['GET'])
def get_absensi():
    """Get all attendance records."""
    try:
        absensi_list = Absensi.query.order_by(Absensi.timestamp.desc()).all()
        logger.info(f"Fetched {len(absensi_list)} absensi records.")

        DATABASE_OPERATIONS.labels(operation_type='read', status='success').inc()

        return jsonify({
            'message': 'Berhasil mengambil data absensi',
            'total': len(absensi_list),
            'data': [absensi.to_dict() for absensi in absensi_list]
        }), 200
    except SQLAlchemyError as e:
        logger.error(f"SQLAlchemy error during get_absensi: {e}")
        DATABASE_OPERATIONS.labels(operation_type='read', status='failure').inc()
        EXCEPTIONS.labels(method=request.method, endpoint=request.path, exception_type='SQLAlchemyError').inc()
        return jsonify({'message': 'Gagal mengambil data absensi', 'error': str(e)}), 500
    except Exception as e:
        logger.error(f"Unexpected error during get_absensi: {e}")
        EXCEPTIONS.labels(method=request.method, endpoint=request.path, exception_type='Exception').inc()
        return jsonify({'message': 'Terjadi kesalahan tidak terduga', 'error': str(e)}), 500

@app.route('/absensi/<int:id>', methods=['PUT'])
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

        DATABASE_OPERATIONS.labels(operation_type='update', status='success').inc()
        updated_absensi = Absensi.query.get(id)

        return jsonify({'message': 'Absensi berhasil diperbarui', 'data': updated_absensi.to_dict()}), 200
    except SQLAlchemyError as e:
        db.session.rollback()
        DATABASE_OPERATIONS.labels(operation_type='update', status='failure').inc()
        EXCEPTIONS.labels(method=request.method, endpoint=request.path, exception_type='SQLAlchemyError').inc()
        return jsonify({'message': 'Gagal memperbarui absensi', 'error': str(e)}), 500
    except Exception as e:
        EXCEPTIONS.labels(method=request.method, endpoint=request.path, exception_type='Exception').inc()
        return jsonify({'message': 'An unexpected error occurred', 'error': str(e)}), 500

@app.route('/absensi/<int:id>', methods=['DELETE'])
def delete_absensi(id):
    """Delete an attendance record."""
    try:
        absensi = Absensi.query.get(id)
        if not absensi:
            return jsonify({'message': 'Absensi tidak ditemukan'}), 404

        db.session.delete(absensi)
        db.session.commit()

        DATABASE_OPERATIONS.labels(operation_type='delete', status='success').inc()

        return jsonify({'message': 'Absensi berhasil dihapus'}), 200
    except SQLAlchemyError as e:
        db.session.rollback()
        DATABASE_OPERATIONS.labels(operation_type='delete', status='failure').inc()
        EXCEPTIONS.labels(method=request.method, endpoint=request.path, exception_type='SQLAlchemyError').inc()
        return jsonify({'message': 'Gagal menghapus absensi', 'error': str(e)}), 500
    except Exception as e:
        EXCEPTIONS.labels(method=request.method, endpoint=request.path, exception_type='Exception').inc()
        return jsonify({'message': 'An unexpected error occurred', 'error': str(e)}), 500

# Start the Flask application
if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)