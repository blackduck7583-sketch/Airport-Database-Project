import sqlite3
from pathlib import Path


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS airlines (
    id INTEGER PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS aircraft_types (
    id INTEGER PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    turnaround_minutes INTEGER NOT NULL DEFAULT 45 CHECK (turnaround_minutes BETWEEN 0 AND 240)
);

CREATE TABLE IF NOT EXISTS gates (
    id INTEGER PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    terminal TEXT NOT NULL,
    gate_type TEXT NOT NULL CHECK (gate_type IN ('CONTACT', 'REMOTE')),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1))
);

CREATE TABLE IF NOT EXISTS flights (
    id INTEGER PRIMARY KEY,
    flight_no TEXT NOT NULL,
    airline_id INTEGER NOT NULL REFERENCES airlines(id),
    aircraft_type_id INTEGER NOT NULL REFERENCES aircraft_types(id),
    direction TEXT NOT NULL CHECK (direction IN ('ARRIVAL', 'DEPARTURE')),
    origin_destination TEXT NOT NULL,
    scheduled_time TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'SCHEDULED'
      CHECK (status IN ('SCHEDULED', 'DELAYED', 'BOARDING', 'DEPARTED', 'ARRIVED', 'CANCELLED')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (flight_no, scheduled_time, direction)
);

CREATE TABLE IF NOT EXISTS gate_assignments (
    id INTEGER PRIMARY KEY,
    flight_id INTEGER NOT NULL UNIQUE REFERENCES flights(id) ON DELETE CASCADE,
    gate_id INTEGER NOT NULL REFERENCES gates(id),
    occupied_from TEXT NOT NULL,
    occupied_until TEXT NOT NULL,
    assigned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (occupied_until > occupied_from)
);

CREATE TABLE IF NOT EXISTS delay_records (
    id INTEGER PRIMARY KEY,
    flight_id INTEGER NOT NULL REFERENCES flights(id) ON DELETE CASCADE,
    delay_minutes INTEGER NOT NULL CHECK (delay_minutes > 0),
    reason TEXT NOT NULL,
    recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_flights_scheduled_time ON flights(scheduled_time);
CREATE INDEX IF NOT EXISTS idx_flights_status_time ON flights(status, scheduled_time);
CREATE INDEX IF NOT EXISTS idx_flights_airline_time ON flights(airline_id, scheduled_time);
CREATE INDEX IF NOT EXISTS idx_assignments_gate_window ON gate_assignments(gate_id, occupied_from, occupied_until);
CREATE INDEX IF NOT EXISTS idx_delays_flight_recorded ON delay_records(flight_id, recorded_at);
"""


SEED = """
INSERT OR IGNORE INTO airlines(code, name) VALUES
 ('CA', '中国国际航空'), ('MU', '中国东方航空'), ('CZ', '中国南方航空'),
 ('HU', '海南航空'), ('9C', '春秋航空');

INSERT OR IGNORE INTO aircraft_types(code, name, turnaround_minutes) VALUES
 ('A320', 'Airbus A320', 45), ('A321', 'Airbus A321', 50),
 ('B738', 'Boeing 737-800', 45), ('B789', 'Boeing 787-9', 75);

INSERT OR IGNORE INTO gates(code, terminal, gate_type) VALUES
 ('T1-01', 'T1', 'CONTACT'), ('T1-02', 'T1', 'CONTACT'),
 ('T1-03', 'T1', 'REMOTE'), ('T2-01', 'T2', 'CONTACT'),
 ('T2-02', 'T2', 'CONTACT'), ('T2-03', 'T2', 'REMOTE');
"""


def connect(database):
    Path(database).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 10000")
    return connection


def init_db(database):
    with connect(database) as connection:
        connection.executescript(SCHEMA)
        connection.executescript(SEED)

