CREATE TABLE IF NOT EXISTS alumnos (
    cardnumber BIGINT PRIMARY KEY,
    surname    TEXT,
    firstname  TEXT,
    sort1      TEXT
);

-- Copia del padron anterior y de donde salio cada uno, para poder restaurarlo
CREATE TABLE IF NOT EXISTS alumnos_anterior (LIKE alumnos INCLUDING ALL);
CREATE TABLE IF NOT EXISTS padron_meta (
    id                   SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    cargado_en           TIMESTAMP,
    archivo              TEXT,
    anterior_cargado_en  TIMESTAMP,
    anterior_archivo     TEXT,
    hay_anterior         BOOLEAN NOT NULL DEFAULT FALSE
);
INSERT INTO padron_meta (id) VALUES (1) ON CONFLICT (id) DO NOTHING;

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