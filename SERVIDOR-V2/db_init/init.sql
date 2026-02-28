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
    fecha_hora  TIMESTAMP DEFAULT NOW()
);


CREATE TABLE computadoras (
    id             TEXT PRIMARY KEY,
    nombre         TEXT,
    ip_ultima      TEXT,
    fecha_registro TIMESTAMP DEFAULT NOW()
);