CREATE DATABASE IF NOT EXISTS flask_app_db;

USE flask_app_db;

CREATE TABLE IF NOT EXISTS absensi (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nrp VARCHAR(20) NOT NULL,
    nama VARCHAR(100) NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Optionally, you can insert some initial data
INSERT INTO absensi (nrp, nama) VALUES ('123456', 'John Doe');
INSERT INTO absensi (nrp, nama) VALUES ('654321', 'Jane Smith');
