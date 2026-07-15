"""
simulacion_transacciones.py
Simula un sistema de reservas (vuelo + hotel + transporte) usando
savepoints, transacciones de compensación, deadlocks y timeouts.
Requiere que ya exista la base de datos y las tablas (ver schema.sql).
"""
import logging
import threading
import time

import psycopg2
import psycopg2.errors

from config import DB_CONFIG

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(threadName)s - %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("logs/simulacion.log")],
)
log = logging.getLogger("reservas")


def conectar():
    return psycopg2.connect(**DB_CONFIG)


def log_evento(cur, operacion, detalle):
    cur.execute(
        "INSERT INTO auditoria_reservas (operacion, detalle) VALUES (%s, %s)",
        (operacion, detalle),
    )


def cancelar_vuelo(vuelo_id):
    """Transacción de COMPENSACIÓN: libera el asiento ya comprado."""
    conn = conectar()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE vuelos SET asientos_disponibles = asientos_disponibles + 1 "
            "WHERE vuelo_id = %s", (vuelo_id,)
        )
        log_evento(cur, "COMPENSACION_CANCELAR_VUELO", f"vuelo_id={vuelo_id}")
        conn.commit()
        log.warning(f"[COMPENSACIÓN] Vuelo {vuelo_id} cancelado, asiento liberado.")
    finally:
        conn.close()


def reservar_paquete(vuelo_id, hotel_id, transporte_id):
    """Vuelo -> Hotel -> Transporte, con SAVEPOINTS y compensación si falla."""
    conn = conectar()
    try:
        cur = conn.cursor()

        # Paso 1: vuelo (se confirma solo, como si fuera un servicio externo)
        cur.execute(
            "UPDATE vuelos SET asientos_disponibles = asientos_disponibles - 1 "
            "WHERE vuelo_id = %s AND asientos_disponibles > 0 RETURNING vuelo_id",
            (vuelo_id,),
        )
        if cur.fetchone() is None:
            conn.rollback()
            log.error(f"Vuelo {vuelo_id} sin cupo. Reserva abortada.")
            return "FALLO_VUELO_SIN_CUPO"
        log_evento(cur, "PASO1_VUELO_COMPRADO", f"vuelo_id={vuelo_id}")
        conn.commit()
        log.info(f"Paso 1 OK: vuelo {vuelo_id} comprado.")

        # Paso 2: hotel (con savepoint)
        cur = conn.cursor()
        cur.execute("SAVEPOINT sp_vuelo")
        cur.execute(
            "UPDATE hoteles SET habitaciones_disponibles = habitaciones_disponibles - 1 "
            "WHERE hotel_id = %s AND habitaciones_disponibles > 0 RETURNING hotel_id",
            (hotel_id,),
        )
        if cur.fetchone() is None:
            cur.execute("ROLLBACK TO SAVEPOINT sp_vuelo")
            log_evento(cur, "PASO2_HOTEL_SIN_CUPO_ROLLBACK_SAVEPOINT", f"hotel_id={hotel_id}")
            conn.commit()
            log.warning(f"Hotel {hotel_id} sin cupo. ROLLBACK TO SAVEPOINT ejecutado.")
            cancelar_vuelo(vuelo_id)
            return "FALLO_HOTEL_COMPENSADO"
        log_evento(cur, "PASO2_HOTEL_RESERVADO", f"hotel_id={hotel_id}")
        log.info(f"Paso 2 OK: hotel {hotel_id} reservado.")

        # Paso 3: transporte (con su propio savepoint)
        cur.execute("SAVEPOINT sp_hotel")
        cur.execute(
            "UPDATE transportes SET vehiculos_disponibles = vehiculos_disponibles - 1 "
            "WHERE transporte_id = %s AND vehiculos_disponibles > 0 RETURNING transporte_id",
            (transporte_id,),
        )
        if cur.fetchone() is None:
            cur.execute("ROLLBACK TO SAVEPOINT sp_vuelo")  # deshace hotel + transporte
            log_evento(cur, "PASO3_TRANSPORTE_SIN_CUPO_ROLLBACK_SAVEPOINT", f"transporte_id={transporte_id}")
            conn.commit()
            log.warning(f"Transporte {transporte_id} sin cupo. ROLLBACK TO SAVEPOINT ejecutado.")
            cancelar_vuelo(vuelo_id)
            return "FALLO_TRANSPORTE_COMPENSADO"
        log_evento(cur, "PASO3_TRANSPORTE_RESERVADO", f"transporte_id={transporte_id}")
        conn.commit()
        log.info(f"Paso 3 OK: transporte {transporte_id} reservado. RESERVA COMPLETA.")
        return "EXITO"
    except Exception as exc:
        conn.rollback()
        log.error(f"Error inesperado, ROLLBACK total: {exc}")
        return f"ERROR:{exc}"
    finally:
        conn.close()


def simular_deadlock():
    """Dos transacciones concurrentes bloquean vuelos/hoteles en orden inverso."""
    def transaccion_a():
        conn = conectar()
        try:
            cur = conn.cursor()
            cur.execute("UPDATE vuelos SET asientos_disponibles = asientos_disponibles - 1 WHERE vuelo_id = 1")
            log.info("[A] Lock sobre vuelo_id=1 adquirido. Esperando...")
            time.sleep(2)
            cur.execute("UPDATE hoteles SET habitaciones_disponibles = habitaciones_disponibles - 1 WHERE hotel_id = 1")
            conn.commit()
            log.info("[A] Transacción completada con éxito.")
        except psycopg2.errors.DeadlockDetected as exc:
            conn.rollback()
            log.error(f"[A] DEADLOCK DETECTADO, transacción abortada: {exc}")
        finally:
            conn.close()

    def transaccion_b():
        conn = conectar()
        try:
            cur = conn.cursor()
            cur.execute("UPDATE hoteles SET habitaciones_disponibles = habitaciones_disponibles - 1 WHERE hotel_id = 1")
            log.info("[B] Lock sobre hotel_id=1 adquirido. Esperando...")
            time.sleep(2)
            cur.execute("UPDATE vuelos SET asientos_disponibles = asientos_disponibles - 1 WHERE vuelo_id = 1")
            conn.commit()
            log.info("[B] Transacción completada con éxito.")
        except psycopg2.errors.DeadlockDetected as exc:
            conn.rollback()
            log.error(f"[B] DEADLOCK DETECTADO, transacción abortada: {exc}")
        finally:
            conn.close()

    log.info("=== Simulación de DEADLOCK ===")
    t1, t2 = threading.Thread(target=transaccion_a), threading.Thread(target=transaccion_b)
    t1.start(); t2.start(); t1.join(); t2.join()


def simular_timeout():
    """Cancela una sentencia lenta (statement_timeout) y una espera de lock (lock_timeout)."""
    log.info("=== Simulación de TIMEOUT (statement_timeout) ===")
    conn = conectar()
    try:
        cur = conn.cursor()
        cur.execute("SET statement_timeout = '2000'")
        cur.execute("SELECT pg_sleep(5)")  # tarda más que el timeout -> se cancela
        conn.commit()
    except psycopg2.errors.QueryCanceled as exc:
        conn.rollback()
        log.error(f"TIMEOUT: sentencia cancelada: {exc}")
    finally:
        conn.close()

    log.info("=== Simulación de TIMEOUT (lock_timeout) ===")
    conn_a, conn_b = conectar(), conectar()
    try:
        cur_a = conn_a.cursor()
        cur_a.execute("UPDATE vuelos SET asientos_disponibles = asientos_disponibles WHERE vuelo_id = 3")
        log.info("Conexión A tomó el lock y no hace commit todavía.")

        def esperar_lock():
            try:
                cur_b = conn_b.cursor()
                cur_b.execute("SET lock_timeout = '2000'")
                cur_b.execute("UPDATE vuelos SET asientos_disponibles = asientos_disponibles WHERE vuelo_id = 3")
                conn_b.commit()
            except psycopg2.errors.LockNotAvailable as exc:
                conn_b.rollback()
                log.error(f"TIMEOUT DE LOCK: conexión B canceló la espera: {exc}")

        hilo = threading.Thread(target=esperar_lock)
        hilo.start(); hilo.join()
        conn_a.commit()
    finally:
        conn_a.close(); conn_b.close()


def main():
    log.info("=== ESCENARIO 1: Reserva exitosa ===")
    log.info(reservar_paquete(vuelo_id=1, hotel_id=1, transporte_id=1))

    log.info("=== ESCENARIO 2: Hotel sin cupo (compensación) ===")
    log.info(reservar_paquete(vuelo_id=2, hotel_id=2, transporte_id=2))

    simular_deadlock()
    simular_timeout()


if __name__ == "__main__":
    main()
