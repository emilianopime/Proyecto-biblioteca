-- Este archivo se ejecuta automáticamente la primera vez que
-- el contenedor de PostgreSQL arranca (directorio initdb.d).

CREATE TABLE IF NOT EXISTS computadoras (
    id             TEXT PRIMARY KEY,
    name           TEXT,
    ip             TEXT,
    last_heartbeat TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS alumnos (
    cardnumber BIGINT PRIMARY KEY,
    surname    TEXT,
    firstname  TEXT,
    sort1      TEXT
);

CREATE TABLE IF NOT EXISTS bitacora_uso (
    id          SERIAL PRIMARY KEY,
    computer_id TEXT,
    matricula   BIGINT,
    evento      TEXT,
    timestamp   TIMESTAMP DEFAULT NOW()
);
