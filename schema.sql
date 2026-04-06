-- ============================================================
--  LAB INVENTORY MANAGEMENT SYSTEM — SQLite Schema
--  Run automatically by lab_inventory.py on first launch.
-- ============================================================

PRAGMA foreign_keys = ON;

-- ----------------------------------------------------------
-- Table 1: Locations
-- ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS locations (
    location_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    location_name TEXT    NOT NULL UNIQUE
);

-- ----------------------------------------------------------
-- Table 2: Users
-- ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name    TEXT    NOT NULL,
    role    TEXT    NOT NULL,
    email   TEXT    NOT NULL UNIQUE
);

-- ----------------------------------------------------------
-- Table 3: Projects
-- ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS projects (
    project_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    project_name TEXT    NOT NULL,
    grant_code   TEXT,
    status       TEXT    NOT NULL CHECK(status IN ('Active', 'Completed'))
);

-- ----------------------------------------------------------
-- Table 4: Items  (main hub)
-- internal_id is a custom-formatted string: LAB-001, LAB-002 …
-- The next ID is computed in Python (get_next_lab_id).
-- ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS items (
    internal_id          TEXT    PRIMARY KEY,
    item_name            TEXT    NOT NULL,
    category             TEXT    NOT NULL CHECK(category IN (
                             'Capital Equipment',
                             'Electronics/Sensors',
                             'IT/Computing',
                             'Tools/Hardware',
                             'Consumables'
                         )),
    manufacturer_sn      TEXT,
    condition            TEXT    NOT NULL CHECK(condition IN (
                             'Available',
                             'In Use',
                             'Broken',
                             'Needs Repair'
                         )),
    expected_return_date TEXT,                         -- ISO date string, nullable
    project_id           INTEGER,
    user_id              INTEGER,                      -- nullable (no user when Available)
    location_id          INTEGER NOT NULL,
    FOREIGN KEY (project_id)  REFERENCES projects(project_id),
    FOREIGN KEY (user_id)     REFERENCES users(user_id),
    FOREIGN KEY (location_id) REFERENCES locations(location_id)
);
