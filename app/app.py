from flask import Flask, request, jsonify
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import pytz

# Inisialisasi Flask
app = Flask(__name__)

# Setup timezone
timezone = pytz.timezone("Asia/Jakarta")

# Setup SQLAlchemy
Base = declarative_base()

# Model Absensi
class Absensi(Base):
    __tablename__ = 'absensi'
    
    id = Column(Integer, primary_key=True)
    name = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __init__(self, name):
        self.name = name
    
    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }

# Setup database session
DATABASE_URL = "sqlite:///absensi.db"  # Ganti dengan URL database Anda
engine = create_engine(DATABASE_URL, echo=True)
Session = sessionmaker(bind=engine)

# Inisialisasi tabel (untuk pertama kali)
Base.metadata.create_all(engine)

def get_session():
    return Session()

# Fungsi untuk operasi CRUD
# 1. Create Absensi
def create_absensi(name):
    session = get_session()
    try:
        absensi = Absensi(name=name)
        session.add(absensi)
        session.commit()
        return absensi
    except Exception as e:
        session.rollback()
        print(f"Error: {e}")
        raise
    finally:
        session.close()

# 2. Get Absensi
def get_all_absensi():
    session = get_session()
    try:
        absensi_list = session.query(Absensi).all()
        return absensi_list
    finally:
        session.close()

# 3. Update Absensi
def update_absensi(absensi_id, new_data):
    session = get_session()
    try:
        absensi = session.query(Absensi).filter_by(id=absensi_id).first()
        if absensi:
            absensi.name = new_data.get('name', absensi.name)
            absensi.updated_at = datetime.now(timezone)  # Set updated_at ke waktu lokal
            session.commit()
            return absensi
        else:
            raise ValueError(f"Absensi with ID {absensi_id} not found")
    except Exception as e:
        session.rollback()
        print(f"Error: {e}")
        raise
    finally:
        session.close()

# 4. Delete Absensi
def delete_absensi(absensi_id):
    session = get_session()
    try:
        absensi = session.query(Absensi).filter_by(id=absensi_id).first()
        if absensi:
            session.delete(absensi)
            session.commit()
        else:
            raise ValueError(f"Absensi with ID {absensi_id} not found")
    except Exception as e:
        session.rollback()
        print(f"Error: {e}")
        raise
    finally:
        session.close()

# Route untuk GET Absensi
@app.route("/absensi", methods=["GET"])
def get_absensi():
    try:
        absensi_list = get_all_absensi()
        return jsonify([absensi.to_dict() for absensi in absensi_list]), 200
    except Exception as e:
        return jsonify({"message": f"Error: {e}"}), 500

# Route untuk DELETE Absensi
@app.route("/absensi/<int:id>", methods=["DELETE"])
def delete_absensi_route(id):
    try:
        delete_absensi(id)
        return jsonify({"message": f"Absensi with ID {id} deleted successfully"}), 200
    except Exception as e:
        return jsonify({"message": f"Error: {e}"}), 500

# Route untuk PUT Absensi (Update)
@app.route("/absensi/<int:id>", methods=["PUT"])
def update_absensi_route(id):
    new_data = request.get_json()
    try:
        updated_absensi = update_absensi(id, new_data)
        return jsonify({"message": f"Absensi with ID {id} updated successfully", "data": updated_absensi.to_dict()}), 200
    except Exception as e:
        return jsonify({"message": f"Error: {e}"}), 500

# Route untuk POST Absensi (Create)
@app.route("/absensi", methods=["POST"])
def create_absensi_route():
    new_data = request.get_json()
    try:
        absensi = create_absensi(new_data['name'])
        return jsonify({"message": "Absensi created successfully", "data": absensi.to_dict()}), 201
    except Exception as e:
        return jsonify({"message": f"Error: {e}"}), 500

# Menjalankan aplikasi Flask
if __name__ == "__main__":
    app.run(debug=True)
