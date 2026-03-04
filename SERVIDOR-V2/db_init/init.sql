CREATE TABLE IF NOT EXISTS alumnos (
    cardnumber BIGINT PRIMARY KEY,
    surname    TEXT,
    firstname  TEXT,
    sort1      TEXT
);

CREATE TABLE bitacora_uso (
    id          SERIAL PRIMARY KEY,
    computer_id TEXT,
    matricula   BIGINT,
    evento      TEXT,
    timestamp   TIMESTAMP DEFAULT NOW()
);

CREATE TABLE computadoras (
    id             TEXT PRIMARY KEY,
    name           TEXT,
    ip             TEXT,
    last_heartbeat TIMESTAMP WITHOUT TIME ZONE
);