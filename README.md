# Simulación de Transacciones: Sistema de Reservas Turísticas


## Tabla de contenidos

1. [Introducción teórica](#1-introducción-teórica)
2. [Explicación del escenario](#2-explicación-del-escenario)
3. [Requisitos previos](#3-requisitos-previos)
4. [Instalación y ejecución](#4-instalación-y-ejecución)
5. [Explicación del código](#5-explicación-del-código-paso-a-paso)
6. [Resultados obtenidos](#6-resultados-obtenidos)
7. [Preguntas de reflexión](#7-preguntas-de-reflexión)
8. [Conclusión](#8-conclusión)

---

## 1. Introducción teórica

### 1.1 Transacciones anidadas y savepoints

Una **transacción** es una unidad de trabajo que agrupa una o más
operaciones sobre la base de datos y que debe cumplir con las propiedades
**ACID** (Atomicidad, Consistencia, Aislamiento y Durabilidad). O se
ejecutan *todas* las operaciones, o no se ejecuta *ninguna*.

Un **SAVEPOINT** es un "punto de control" dentro de una transacción que
permite deshacer *parcialmente* el trabajo realizado sin necesidad de
abortar la transacción completa. Es decir, simulan una especie de
transacción anidada:

```sql
BEGIN;
UPDATE vuelos SET asientos_disponibles = asientos_disponibles - 1 WHERE vuelo_id = 1;
SAVEPOINT sp_after_vuelo;
UPDATE hoteles SET habitaciones_disponibles = habitaciones_disponibles - 1 WHERE hotel_id = 2;
-- Si esta última operación falla o no cumple una condición de negocio:
ROLLBACK TO SAVEPOINT sp_after_vuelo;  -- deshace SOLO el UPDATE de hoteles
COMMIT; -- la reserva del vuelo permanece intacta
```

Los savepoints son útiles cuando una transacción larga tiene varios pasos
y se quiere reintentar o descartar solo uno de ellos sin perder el trabajo
previo ya validado dentro de la misma transacción.

### 1.2 Transacciones de compensación

Los savepoints solo funcionan **dentro de una misma transacción que aún no
ha hecho COMMIT**. En sistemas distribuidos (o incluso en un mismo sistema
cuando un paso ya fue confirmado de forma independiente, como suele ocurrir
al integrar servicios de aerolíneas, hoteles y transporte de terceros), no
es posible hacer `ROLLBACK` de algo que ya fue confirmado (`COMMIT`).

* Los pasos **hotel** y **transporte** usan *savepoints* dentro de una
  misma transacción (porque, si fallan, todavía no se ha hecho commit).
* El paso **vuelo**, al confirmarse (`COMMIT`) antes de continuar, requiere
  una **transacción de compensación explícita** (`cancelar_vuelo()`) si
  algún paso posterior falla.

### 1.3 Deadlocks (interbloqueos)

Un **deadlock** ocurre cuando dos (o más) transacciones concurrentes se
bloquean mutuamente esperando un recurso (fila o tabla) que la otra
transacción tiene bloqueado, formando un ciclo de espera del que ninguna
puede salir por sí sola.

Ejemplo típico:

* Transacción A bloquea la fila `X` y luego intenta bloquear la fila `Y`.
* Transacción B bloquea la fila `Y` y luego intenta bloquear la fila `X`.
* A espera a B, B espera a A → **ciclo infinito**.

### 1.4 Timeouts

Un **timeout** es un límite de tiempo máximo que el sistema espera antes
de cancelar una operación que está tardando demasiado. 
Los timeouts son un mecanismo de protección: evitan que una transacción
bloqueada indefinidamente (por ejemplo, esperando un lock que nunca se va
a liberar) consuma recursos del sistema para siempre.

---

## 2. Explicación del escenario

El sistema simula la compra de un **paquete turístico** compuesto por tres
reservas encadenadas, todas dependientes entre sí:

1. **Vuelo**: se descuenta un asiento disponible.
2. **Hotel**: se descuenta una habitación disponible.
3. **Transporte**: se descuenta un vehículo disponible.

**Regla de negocio central:** si el hotel elegido no tiene cupo, la
reserva completa debe fallar y el asiento de avión ya comprado debe
liberarse (cancelación/compensación), para que el sistema quede
consistente: **o se reservan los tres servicios, o no se reserva
ninguno**.

Además, se simulan dos condiciones adicionales frecuentes en sistemas
transaccionales concurrentes:

* Un **deadlock** entre dos transacciones que intentan actualizar las
  mismas dos filas (`vuelos.vuelo_id = 1` y `hoteles.hotel_id = 1`) en
  orden inverso.
* Un **timeout**, tanto por sentencia lenta (`statement_timeout`) como por
  espera de un lock ya tomado por otra transacción (`lock_timeout`).

---

## 3. Requisitos previos

* Python 3.x instalado.
* PostgreSQL activo (local o en la nube).
* Instalar dependencias:

  ```bash
  pip install -r requirements.txt
  ```

* Variables de entorno (opcionales; si no se configuran, se usan valores
  por defecto de un entorno local — ver `config.py`):

  | Variable      | Descripción                  | Valor por defecto     |
  |---------------|-------------------------------|------------------------|
  | `DB_HOST`     | Host del servidor PostgreSQL   | `localhost`            |
  | `DB_PORT`     | Puerto del servidor            | `5432`                 |
  | `DB_NAME`     | Nombre de la base de datos     | `reservas_turisticas`  |
  | `DB_USER`     | Usuario                        | `postgres`             |
  | `DB_PASSWORD` | Contraseña                     | `postgres`             |

---

## 4. Instalación y ejecución

```bash
# 1. Clonar el repositorio
git clone <URL_DEL_REPOSITORIO>
cd reservas-turisticas

# 2. Crear entorno virtual (recomendado)
python3 -m venv venv
source venv/bin/activate   # En Windows: venv\Scripts\activate

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Crear la base de datos (una sola vez)
createdb reservas_turisticas

# 5. configurar variables de entorno
export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=reservas_turisticas
export DB_USER=postgres
export DB_PASSWORD=postgres

# 6. Ejecutar la simulación completa
python3 simulacion_transacciones.py
```

`schema.sql` crea las tablas `vuelos`, `hoteles`, `transportes` y
`auditoria_reservas`, e inserta 10 registros de prueba en cada una (el
hotel `hotel_id = 2` se deja intencionalmente **sin cupo** para disparar
el escenario de compensación). El script Python solo se conecta y ejecuta
la lógica de transacciones; ya no crea las tablas.

Al ejecutarlo, `simulacion_transacciones.py`:

1. Ejecuta una reserva exitosa.
2. Ejecuta una reserva que falla por falta de cupo en el hotel.
3. Simula un deadlock entre dos hilos/transacciones concurrentes.
4. Simula un timeout por sentencia lenta y un timeout por espera de lock.

Todos los eventos quedan registrados en consola y en `logs/simulacion.log`.

## 5. Explicación del código paso a paso

### `config.py`
Centraliza la configuración de conexión, leyendo credenciales desde
variables de entorno (con valores por defecto solo para pruebas locales).
Esto evita hardcodear contraseñas en el script principal.

### `schema.sql`
Contiene todo el DDL: crea las tablas `vuelos`, `hoteles`, `transportes`
(con columnas de disponibilidad restringidas a valores `>= 0` mediante
`CHECK`) y la tabla auxiliar `auditoria_reservas`, que registra cada paso
relevante de cada intento de reserva (usada para trazabilidad y para los
resultados de la sección 6). También inserta 10 registros de prueba por
tabla; el hotel `hotel_id = 2` se inserta con `habitaciones_disponibles =
0` a propósito, para reproducir el escenario de falla y compensación de
forma determinística. Se ejecuta una sola vez, antes de correr el script
de Python.

### `reservar_paquete(vuelo_id, hotel_id, transporte_id)`
Función central de la actividad. Implementa la lógica de savepoints y
compensación:

1. **Paso 1 (vuelo)**: `UPDATE ... WHERE asientos_disponibles > 0`. Si no
   hay filas afectadas (sin cupo), se aborta con `ROLLBACK` (no hay nada
   que compensar todavía). Si hay éxito, se hace **COMMIT** — el vuelo
   queda confirmado en la base de datos.
2. Se abre una nueva transacción y se crea `SAVEPOINT sp_vuelo`.
3. **Paso 2 (hotel)**: si no hay cupo, se ejecuta
   `ROLLBACK TO SAVEPOINT sp_vuelo` (deshace el intento de hotel) y,
   como el vuelo ya estaba confirmado (commit) en el paso 1, se invoca
   `cancelar_vuelo()` — la **transacción de compensación** — para liberar
   el asiento.
4. Si el hotel tiene cupo, se crea `SAVEPOINT sp_hotel` y se intenta
   el **Paso 3 (transporte)**. Si no hay disponibilidad, se regresa al
   savepoint **anterior al hotel** (`sp_vuelo`), lo que deshace
   automáticamente tanto el intento de transporte como la reserva de
   hotel (por estar dentro del alcance del savepoint), y luego se invoca
   igualmente `cancelar_vuelo()`.
5. Si los tres pasos tienen éxito, se hace `COMMIT` final.

Este diseño ilustra una idea clave: **el rollback a un savepoint solo
deshace cambios que aún no se han confirmado**; lo que ya fue confirmado
con `COMMIT` (el vuelo) necesita una compensación explícita.

### `cancelar_vuelo(vuelo_id)`
Transacción de compensación **totalmente independiente** (nueva conexión y
nueva transacción). Incrementa nuevamente `asientos_disponibles`, simulando
la cancelación del vuelo, y confirma con `COMMIT`.

### `simular_deadlock()`
Lanza dos hilos (funciones internas `transaccion_a` y `transaccion_b`),
cada uno con su propia conexión:

* **Transacción A**: bloquea `vuelo_id = 1`, espera 2 segundos, luego
  intenta bloquear `hotel_id = 1`.
* **Transacción B**: bloquea `hotel_id = 1`, espera 2 segundos, luego
  intenta bloquear `vuelo_id = 1`.

Al cruzarse las esperas, PostgreSQL detecta el ciclo y aborta una de las
dos transacciones con `psycopg2.errors.DeadlockDetected`, que se captura y
se registra en el log.

### `simular_timeout()`
Contiene dos sub-simulaciones:

* **`statement_timeout`**: se configura un límite de 2 segundos y se
  ejecuta `SELECT pg_sleep(5)` (una operación deliberadamente lenta).
  PostgreSQL cancela la sentencia y se captura
  `psycopg2.errors.QueryCanceled`.
* **`lock_timeout`**: una conexión "A" toma un lock sobre `vuelo_id = 3`
  sin hacer commit; una segunda conexión "B", con `lock_timeout = 2000ms`,
  intenta actualizar la misma fila y, al no poder obtener el lock a
  tiempo, se cancela con `psycopg2.errors.LockNotAvailable`.

### `main()`
Orquesta la ejecución completa de los cuatro escenarios en orden y deja
todo registrado en `logs/simulacion.log`.

---

## 6. Resultados obtenidos

> Los logs completos de una ejecución real se encuentran en
> `logs/simulacion.log` tras correr el script, y una copia de referencia
> se documenta a continuación. Las capturas de pantalla del entorno del
> estudiante deben agregarse en la carpeta `capturas/` y enlazarse aquí.

### Escenario 1 — Reserva exitosa

```
=== ESCENARIO 1: Reserva exitosa ===
Paso 1 OK: vuelo 1 comprado.
Paso 2 OK: hotel 1 reservado.
Paso 3 OK: transporte 1 reservado. RESERVA COMPLETA.
EXITO
```

### Escenario 2 — Hotel sin cupo → savepoint + compensación

```
=== ESCENARIO 2: Hotel sin cupo (compensación) ===
Paso 1 OK: vuelo 2 comprado.
Hotel 2 sin cupo. ROLLBACK TO SAVEPOINT ejecutado.
[COMPENSACIÓN] Vuelo 2 cancelado, asiento liberado.
FALLO_HOTEL_COMPENSADO
```

### Escenario 3 — Deadlock

```
=== Simulación de DEADLOCK ===
[A] Lock sobre vuelo_id=1 adquirido. Esperando...
[B] Lock sobre hotel_id=1 adquirido. Esperando...
[A] DEADLOCK DETECTADO, transacción abortada: deadlock detected
DETAIL:  Process 587 waits for ShareLock on transaction 853; blocked by process 588.
Process 588 waits for ShareLock on transaction 852; blocked by process 587.
HINT:  See server log for query details.
CONTEXT:  while updating tuple (0,11) in relation "hoteles"
[B] Transacción completada con éxito.
```

PostgreSQL detectó el ciclo de espera circular y abortó automáticamente la
transacción A (código de error `40P01`), permitiendo que B continuara.

### Escenario 4 — Timeouts

```
=== Simulación de TIMEOUT (statement_timeout) ===
TIMEOUT: sentencia cancelada: canceling statement due to statement timeout

=== Simulación de TIMEOUT (lock_timeout) ===
Conexión A tomó el lock y no hace commit todavía.
TIMEOUT DE LOCK: conexión B canceló la espera: canceling statement due to lock timeout
CONTEXT:  while updating tuple (0,3) in relation "vuelos"
```

### Verificación de consistencia de datos

Tras la ejecución completa, la consulta sobre `auditoria_reservas` confirma
la secuencia exacta de eventos:

| operacion                                | detalle          |
|-------------------------------------------|------------------|
| PASO1_VUELO_COMPRADO                      | vuelo_id=1       |
| PASO2_HOTEL_RESERVADO                     | hotel_id=1       |
| PASO3_TRANSPORTE_RESERVADO                | transporte_id=1  |
| PASO1_VUELO_COMPRADO                      | vuelo_id=2       |
| PASO2_HOTEL_SIN_CUPO_ROLLBACK_SAVEPOINT   | hotel_id=2       |
| COMPENSACION_CANCELAR_VUELO               | vuelo_id=2       |

Esto demuestra que, tras la falla del hotel 2, el vuelo 2 fue comprado y
luego correctamente compensado (su asiento volvió a su valor original),
mientras que la reserva del vuelo 1 + hotel 1 + transporte 1 permaneció
consumida (reserva exitosa y permanente).

---

## 7. Preguntas de reflexión

**1. ¿Por qué no basta con un simple `ROLLBACK` de toda la transacción
para deshacer la compra del vuelo cuando falla el hotel?**

Porque, en este diseño, el paso del vuelo se confirma (`COMMIT`) de forma
independiente antes de continuar con el hotel — tal como ocurriría si el
vuelo lo gestionara un servicio o proveedor externo. Una vez hecho el
`COMMIT`, ese cambio es permanente y un `ROLLBACK` posterior ya no tiene
ningún efecto sobre él. Por eso se necesita una **transacción de
compensación** independiente que revierta su efecto de forma explícita
(liberar el asiento), en lugar de depender de un rollback.

**2. ¿Qué diferencia hay entre un `ROLLBACK TO SAVEPOINT` y una
transacción de compensación?**

El `ROLLBACK TO SAVEPOINT` deshace cambios **dentro de la misma
transacción, que aún no ha sido confirmada**; es instantáneo, gratuito en
términos de lógica de negocio y garantizado por el motor de base de datos.
La transacción de compensación, en cambio, actúa sobre cambios **ya
confirmados** (posiblemente en otro sistema o servicio) y requiere lógica
de negocio explícita para "deshacer" su efecto — no es un mecanismo nativo
de rollback, sino una nueva operación que produce el efecto contrario.

**3. ¿Por qué se producen los deadlocks en el escenario simulado y cómo
los resuelve PostgreSQL?**

Se producen porque las transacciones A y B bloquean las mismas dos filas
(`vuelo_id = 1` y `hotel_id = 1`) **en orden inverso**: A toma primero el
vuelo y luego intenta el hotel, mientras B toma primero el hotel y luego
intenta el vuelo. Cuando ambas ya sostienen su primer lock y esperan el
segundo, se forma un ciclo de espera circular. PostgreSQL ejecuta
periódicamente un detector de ciclos en el grafo de espera de locks; al
encontrarlo, elige una transacción como "víctima", la aborta (error
`40P01`) y libera sus locks, permitiendo que la otra transacción continúe.

**4. ¿Cómo se podría evitar el deadlock del escenario, en lugar de solo
detectarlo y recuperarse de él?**

La forma más común es establecer un **orden global y consistente** para
adquirir los locks: si todas las transacciones del sistema siempre
bloquean primero `vuelos` y después `hoteles` (nunca al revés), el ciclo
de espera circular no puede formarse. Otras estrategias incluyen reducir
el tamaño/duración de las transacciones, usar niveles de aislamiento más
bajos cuando el negocio lo permita, o aplicar bloqueos optimistas
(verificar versión/`updated_at` en lugar de bloquear filas por adelantado).

**5. ¿Qué riesgos existen si se configuran timeouts demasiado cortos o
demasiado largos?**

Si el timeout es **demasiado corto**, operaciones legítimas pero un poco
lentas (por ejemplo, por carga momentánea del servidor) se cancelarán
innecesariamente, generando errores visibles para el usuario y posibles
reintentos en cascada que empeoran la carga del sistema. Si el timeout es
**demasiado largo** (o no existe), una transacción bloqueada
indefinidamente puede retener locks por mucho tiempo, bloqueando a otras
transacciones, agotando el pool de conexiones y degradando el rendimiento
general del sistema. El valor adecuado depende del comportamiento esperado
de cada operación y debe ajustarse con base en mediciones reales.

---

## 9. Conclusión

Esta actividad permitió llevar a la práctica varios conceptos de control
de transacciones que suelen quedar solo en la teoría:

* Los **savepoints** son una herramienta poderosa para manejar fallos
  parciales dentro de una transacción activa, evitando descartar todo el
  trabajo ya realizado.
* Cuando un paso **ya fue confirmado** de forma independiente (como
  ocurre en integraciones con servicios externos o arquitecturas de
  microservicios), un simple rollback no es suficiente: se requieren
  **transacciones de compensación**, propias del patrón Saga, que
  deshacen semánticamente el efecto de una operación ya persistida.
* Los **deadlocks** son una consecuencia natural de la concurrencia y del
  acceso a recursos compartidos en órdenes distintos; PostgreSQL los
  detecta automáticamente y aborta una transacción para romper el ciclo,
  pero el diseño de la aplicación (orden consistente de acceso a los
  recursos) es la mejor forma de prevenirlos.
* Los **timeouts** son un mecanismo de defensa esencial para evitar que
  transacciones lentas o bloqueadas degraden el sistema completo, aunque
  su configuración debe balancear la tolerancia a la lentitud legítima
  contra el riesgo de bloqueos prolongados.

En conjunto, el ejercicio muestra que diseñar sistemas transaccionales
robustos no se limita a "usar transacciones", sino a anticipar
explícitamente los escenarios de falla, concurrencia y latencia, y a
elegir la herramienta correcta (savepoint, compensación, detección de
deadlock o timeout) para cada uno de ellos.
#   s i m u l a c i o n _ t r a n s a c c i o n e s  
 