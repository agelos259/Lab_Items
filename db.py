"""
Database connection and schema for the Lab Inventory app.
Uses PostgreSQL via psycopg2 (e.g. Supabase).
Connection string is read from st.secrets["DATABASE_URL"].
"""

import psycopg2
import psycopg2.extras
import psycopg2.errors
import streamlit as st


# ── Schema ────────────────────────────────────────────────────────────────────

_SCHEMA_STATEMENTS = [
    """CREATE TABLE IF NOT EXISTS locations (
        location_id   SERIAL PRIMARY KEY,
        location_name TEXT   NOT NULL UNIQUE
    )""",
    """CREATE TABLE IF NOT EXISTS users (
        user_id SERIAL PRIMARY KEY,
        name    TEXT   NOT NULL,
        role    TEXT   NOT NULL,
        email   TEXT   NOT NULL UNIQUE
    )""",
    """CREATE TABLE IF NOT EXISTS projects (
        project_id   SERIAL PRIMARY KEY,
        project_name TEXT   NOT NULL,
        grant_code   TEXT,
        status       TEXT   NOT NULL CHECK(status IN ('Active', 'Completed'))
    )""",
    """CREATE TABLE IF NOT EXISTS categories (
        category_id   SERIAL PRIMARY KEY,
        category_name TEXT   NOT NULL UNIQUE
    )""",
    """CREATE TABLE IF NOT EXISTS login_accounts (
        account_id    SERIAL PRIMARY KEY,
        username      TEXT   NOT NULL UNIQUE,
        password_hash TEXT   NOT NULL,
        salt          TEXT   NOT NULL,
        role          TEXT   NOT NULL DEFAULT 'viewer'
                      CHECK(role IN ('admin', 'viewer'))
    )""",
    """CREATE TABLE IF NOT EXISTS items (
        internal_id          TEXT    PRIMARY KEY,
        item_name            TEXT    NOT NULL,
        category             TEXT,
        category_id          INTEGER REFERENCES categories(category_id),
        model                TEXT,
        manufacturer_sn      TEXT,
        quantity             INTEGER DEFAULT 1,
        condition            TEXT    NOT NULL,
        received             TEXT,
        unit_price_ex_vat    REAL,
        unit_price_inc_vat   REAL,
        total_price_ex_vat   REAL,
        total_price_inc_vat  REAL,
        expected_return_date TEXT,
        project_id           INTEGER REFERENCES projects(project_id),
        user_id              INTEGER REFERENCES users(user_id),
        location_id          INTEGER NOT NULL REFERENCES locations(location_id)
    )""",
]

_SEED_STATEMENTS = [
    """INSERT INTO locations (location_name) VALUES
        ('Main Lab - Room 101'),('Storage Room B'),
        ('Minus 80 Freezer'),('Off-Site / Home'),('Server Room')
    ON CONFLICT DO NOTHING""",
    """INSERT INTO users (name, role, email) VALUES
        ('Dr. Alice Nguyen','Principal Investigator','alice.nguyen@lab.edu'),
        ('Bob Martinez','Research Assistant','bob.martinez@lab.edu'),
        ('Carol Smith','Lab Manager','carol.smith@lab.edu'),
        ('David Chen','PhD Student','david.chen@lab.edu')
    ON CONFLICT DO NOTHING""",
    """INSERT INTO categories (category_name) VALUES
        ('Capital Equipment'),('Electronics/Sensors'),
        ('IT/Computing'),('Tools/Hardware'),('Consumables')
    ON CONFLICT DO NOTHING""",
]


# ── Connection wrapper ────────────────────────────────────────────────────────

class DBConn:
    """
    Thin psycopg2 wrapper with a sqlite3-compatible API.
    - execute()  → uses RealDictCursor (row["col"] access)
    - scalar()   → returns a single value (for COUNT queries)
    - commit() / rollback() / close()
    - raw        → underlying psycopg2 connection (for pandas)
    - ? placeholders are auto-converted to %s
    """

    def __init__(self, dsn: str):
        self._conn = psycopg2.connect(dsn)
        self._conn.autocommit = False

    def execute(self, sql: str, params=()):
        cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql.replace("?", "%s"), params or None)
        return cur

    def scalar(self, sql: str, params=()):
        """Execute and return the first column of the first row."""
        cur = self._conn.cursor()
        cur.execute(sql.replace("?", "%s"), params or None)
        row = cur.fetchone()
        return row[0] if row else None

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    @property
    def raw(self):
        """Underlying psycopg2 connection (e.g. for pandas read_sql_query)."""
        return self._conn


def get_connection() -> DBConn:
    return DBConn(st.secrets["DATABASE_URL"])


# ── Bootstrap ─────────────────────────────────────────────────────────────────

def initialize_db() -> None:
    """Create tables if they don't exist and seed lookup data on first run."""
    conn = get_connection()
    cur = conn.raw.cursor()
    for stmt in _SCHEMA_STATEMENTS:
        cur.execute(stmt)
    conn.commit()

    if conn.scalar("SELECT COUNT(*) FROM locations") == 0:
        for stmt in _SEED_STATEMENTS:
            conn.raw.cursor().execute(stmt)
        conn.commit()

    conn.close()
