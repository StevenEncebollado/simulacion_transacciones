-- schema.sql
-- Ejecutar con: psql -U postgres -d reservas_turisticas -f schema.sql
-- (o pegar directamente en tu cliente SQL / pgAdmin)

DROP TABLE IF EXISTS auditoria_reservas CASCADE;
DROP TABLE IF EXISTS vuelos CASCADE;
DROP TABLE IF EXISTS hoteles CASCADE;
DROP TABLE IF EXISTS transportes CASCADE;

CREATE TABLE vuelos (
    vuelo_id             SERIAL PRIMARY KEY,
    origen               VARCHAR(50) NOT NULL,
    destino               VARCHAR(50) NOT NULL,
    asientos_disponibles  INTEGER NOT NULL CHECK (asientos_disponibles >= 0)
);

CREATE TABLE hoteles (
    hotel_id                  SERIAL PRIMARY KEY,
    nombre                    VARCHAR(50) NOT NULL,
    ciudad                    VARCHAR(50) NOT NULL,
    habitaciones_disponibles  INTEGER NOT NULL CHECK (habitaciones_disponibles >= 0)
);

CREATE TABLE transportes (
    transporte_id          SERIAL PRIMARY KEY,
    tipo                    VARCHAR(50) NOT NULL,
    ciudad                  VARCHAR(50) NOT NULL,
    vehiculos_disponibles   INTEGER NOT NULL CHECK (vehiculos_disponibles >= 0)
);

CREATE TABLE auditoria_reservas (
    id          SERIAL PRIMARY KEY,
    creado_en   TIMESTAMP DEFAULT NOW(),
    operacion   VARCHAR(50),
    detalle     TEXT
);

-- Datos de prueba: 10 vuelos, 10 hoteles (hotel_id=2 SIN cupo a propósito), 10 transportes
INSERT INTO vuelos (origen, destino, asientos_disponibles)
SELECT 'Ciudad_' || i, 'Bogota', 5 FROM generate_series(1, 10) AS i;

INSERT INTO hoteles (nombre, ciudad, habitaciones_disponibles)
SELECT 'Hotel_' || i, 'Bogota', CASE WHEN i = 2 THEN 0 ELSE 5 END
FROM generate_series(1, 10) AS i;

INSERT INTO transportes (tipo, ciudad, vehiculos_disponibles)
SELECT CASE WHEN i % 2 = 0 THEN 'Van' ELSE 'Auto' END, 'Bogota', 5
FROM generate_series(1, 10) AS i;
