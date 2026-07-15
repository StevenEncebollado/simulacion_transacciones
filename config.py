"""
config.py
----------
Configuración de conexión a la base de datos PostgreSQL.

"""

import os

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
    "dbname": os.getenv("DB_NAME", "reservas_turisticas"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", "05092005sC"),
}
