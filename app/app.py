import os
import time
import logging
from datetime import datetime
import pytz
from dotenv import load_dotenv
from flask import Flask, request, jsonify, render_template
from flask_sqlalchemy import SQLAlchemy
from marshmallow import Schema, fields, ValidationError, validate
from prometheus_flask_exporter import PrometheusMetrics
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import scoped_session, sessionmaker

# Load environment variables
load_dotenv()

# Logging Configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Prometheus Metrics Initialization
metrics = PrometheusMetrics(app)

# Database Configuration
DB_URI = os.getenv('DB_URI', 'mysql+mysqlconnector://flask_user:password@mysql/flask_app_db')
app.config['SQLALCHEMY_DATABASE_URI'] = DB_URI
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_recycle': 280,
    'pool_pre_ping': True,
    'pool_size': 10,
    'max_overflow': 20
}

# Database Initialization
db = SQLAlchemy(app)
db_session = scoped_session(sessionmaker(autocommit=False, autoflush=False))

# Specify your local timezone (e.g., 'Asia/Jakarta' for Indonesia)
LOCAL_TIMEZONE = pytz.timezone('Asia/Jakarta')

# Input Validation Schema
class AbsensiSchema(Schema):
    nrp = fields.String(required=True, validate=[validate.Length(min=1, max=20)])
    nama = fields.String(required=True, validate=[validate.Length(min=1, max=100)])

absensi_schema = AbsensiSchema()

# Database Model
class Absensi(db.Model):
    __tablename__ = 'absensi'
    
    id = db.Column(db.Integer, primary_key=True)
    nrp = db.Column(db.String(20), nullable=False)
    nama = db.Column(db.String(100), nullable=False)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(pytz.utc))
    
    def to_dict(self):
        # Convert timestamp to local timezone
        local_timestamp = self.timestamp.astimezone(LOCAL_TIMEZONE)
        return {
            'id': self.id,
            'nrp': self.nrp,
            'nama': self.nama,
            'timestamp': local_timestamp.strftime('%Y-%m-%d %H:%M:%S %Z')
        }

def init_db():
    """Initialize database connection and create tables."""
    try:
        engine = create_engine(DB_URI, pool_size=10, max_overflow=20, pool_timeout=30, pool_recycle=1800)
        db_session.configure(bind=engine)

        with app.app_context():
            db.create_all()

        logger.info("Database initialized successfully.")
        return True
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        return False

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

# Global Error Handlers
@app.errorhandler(404)
def not_found_error(error):
    return jsonify({
        'message': 'Resource not found',
        'error': str(error)
    }), 404

@app.errorhandler(500)
def internal_error(error):
    db_session.rollback()  # Rollback on error
    logger.error(f"Internal Server Error: {error}")
    return jsonify({
        'message': 'Internal server error',
        'error': str(error)
    }), 500

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
        return jsonify({
            'status': 'healthy', 
            'app_number': os.getenv('APP_NUMBER', '1')
        }), 200
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({
            'status': 'unhealthy', 
            'error': str(e)
        }), 500

@app.route('/absensi', methods=['POST'])
def create_absensi():
    """Add a new attendance record with improved validation."""
    try:
        data = request.json
        try:
            validated_data = absensi_schema.load(data)
        except ValidationError as err:
            logger.warning(f"Validation failed: {err.messages}")
            return jsonify({'message': 'Validation failed', 'errors': err.messages}), 400

        # Create the new Absensi record
        new_absensi = Absensi(nrp=validated_data['nrp'], nama=validated_data['nama'])
        db_session.add(new_absensi)
        db_session.commit()

        return jsonify({'message': 'Absensi successfully added', 'data': new_absensi.to_dict()}), 201
    except SQLAlchemyError as e:
        db_session.rollback()
        logger.error(f"Database error during create_absensi: {e}")
        return jsonify({'message': 'Failed to add absensi', 'error': 'Database error occurred'}), 500

@app.route('/absensi', methods=['GET'])
def get_absensi():
    """Get paginated attendance records."""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        per_page = min(per_page, 100)

        pagination = Absensi.query.order_by(Absensi.timestamp.desc()).paginate(page=page, per_page=per_page, error_out=False)

        return jsonify({
            'message': 'Absensi data retrieved successfully',
            'total': pagination.total,
            'page': page,
            'per_page': per_page,
            'data': [absensi.to_dict() for absensi in pagination.items]
        }), 200
    except Exception as e:
        logger.error(f"Error retrieving absensi: {e}")
        return jsonify({'message': 'Failed to retrieve absensi data', 'error': str(e)}), 500

@app.route('/absensi/<int:id>', methods=['PUT'])
def update_absensi(id):
    """Update an existing attendance record."""
    try:
        data = request.json
        try:
            validated_data = absensi_schema.load(data, partial=True)
        except ValidationError as err:
            logger.warning(f"Validation failed: {err.messages}")
            return jsonify({'message': 'Validation failed', 'errors': err.messages}), 400

        absensi = Absensi.query.get(id)
        if not absensi:
            return jsonify({'message': 'Absensi not found'}), 404

        absensi.nrp = validated_data.get('nrp', absensi.nrp)
        absensi.nama = validated_data.get('nama', absensi.nama)
        db_session.commit()

        updated_absensi = Absensi.query.get(id)
        
        return jsonify({'message': 'Absensi successfully updated', 'data': updated_absensi.to_dict()}), 200
    except SQLAlchemyError as e:
        db_session.rollback()
        logger.error(f"SQLAlchemy error during update_absensi: {e}")
        return jsonify({'message': 'Failed to update absensi', 'error': str(e)}), 500

# Main Application
if __name__ == '__main__':
    if wait_for_database() and init_db():
        app.run(host='0.0.0.0', port=5000, debug=os.getenv('FLASK_ENV', 'development') == 'development')
    else:
        logger.critical("Unable to connect to the database. The application will stop.")
        exit(1)
