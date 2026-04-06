"""
Lab Inventory Management System
================================
A Streamlit web app backed by a local SQLite database.
Run with:  python -m streamlit run lab_inventory.py
"""

import sqlite3
import io
import os
import hashlib
import secrets
import base64
import requests
from datetime import date

import pandas as pd
import streamlit as st

# ── Constants ────────────────────────────────────────────────────────────────

DB_PATH = os.path.join(os.path.dirname(__file__), "lab_inventory.db")

CATEGORIES = [
    "Capital Equipment",
    "Electronics/Sensors",
    "IT/Computing",
    "Tools/Hardware",
    "Consumables",
]

CONDITIONS       = ["Available", "In Use", "Broken", "Needs Repair"]
PROJECT_STATUSES = ["Active", "Completed"]

# Maps Excel Greek column headers → internal field names
EXCEL_COL_MAP = {
    "A/A":                              "row_num",
    "ΕΙΔΟΣ":                            "excel_category",   # col 2 → category
    "ΜΟΝΤΕΛΟ":                          "item_name",        # col 3 → product name
    "ΤΕΜΑΧΙΑ":                          "quantity",         # col 4 → N instances
    "S/N":                              "manufacturer_sn",
    "ΤΙΜΗ ΤΕΜΑΧΙΟΥ ΧΩΡΙΣ ΦΠΑ":        "unit_price_ex_vat",
    "ΤΙΜΗ ΤΕΜΑΧΙΟΥ ΜΕ ΦΠΑ":           "unit_price_inc_vat",
    "ΤΙΜΗ ΠΟΣΟΤΗΤΑΣ ΧΩΡΙΣ ΦΠΑ":       "total_price_ex_vat",
    "ΤΙΜΗ ΠΟΣΟΤΗΤΑΣ ΜΕ ΦΠΑ":          "total_price_inc_vat",
    "ΠΑΡΑΛΑΒΗ (ΝΑΙ/ ΟΧΙ)":            "received",
    "ΠΑΡΑΛΑΒΗ (ΝΑΙ/ΟΧΙ)":             "received",
    "ΤΟΠΟΘΕΣΙΑ":                        "location_name",
}

# ── Database bootstrap ────────────────────────────────────────────────────────

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS locations (
    location_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    location_name TEXT    NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name    TEXT    NOT NULL,
    role    TEXT    NOT NULL,
    email   TEXT    NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS projects (
    project_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    project_name TEXT    NOT NULL,
    grant_code   TEXT,
    status       TEXT    NOT NULL CHECK(status IN ('Active', 'Completed'))
);

CREATE TABLE IF NOT EXISTS categories (
    category_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    category_name TEXT    NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS login_accounts (
    account_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL,
    salt          TEXT    NOT NULL,
    role          TEXT    NOT NULL DEFAULT 'viewer' CHECK(role IN ('admin', 'viewer'))
);

CREATE TABLE IF NOT EXISTS items (
    internal_id          TEXT    PRIMARY KEY,
    item_name            TEXT    NOT NULL,
    category             TEXT,
    category_id          INTEGER,
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
    project_id           INTEGER,
    user_id              INTEGER,
    location_id          INTEGER NOT NULL,
    FOREIGN KEY (category_id) REFERENCES categories(category_id),
    FOREIGN KEY (project_id)  REFERENCES projects(project_id),
    FOREIGN KEY (user_id)     REFERENCES users(user_id),
    FOREIGN KEY (location_id) REFERENCES locations(location_id)
);
"""

SEED_SQL = """
INSERT OR IGNORE INTO locations (location_name) VALUES
    ('Main Lab - Room 101'),
    ('Storage Room B'),
    ('Minus 80 Freezer'),
    ('Off-Site / Home'),
    ('Server Room');

INSERT OR IGNORE INTO users (name, role, email) VALUES
    ('Dr. Alice Nguyen',  'Principal Investigator', 'alice.nguyen@lab.edu'),
    ('Bob Martinez',      'Research Assistant',     'bob.martinez@lab.edu'),
    ('Carol Smith',       'Lab Manager',            'carol.smith@lab.edu'),
    ('David Chen',        'PhD Student',            'david.chen@lab.edu');

INSERT OR IGNORE INTO projects (project_name, grant_code, status) VALUES
    ('Climate Sensor Array',   'NSF-2024-001',  'Active'),
    ('Soil Microbiome Study',  'NIH-2023-445',  'Active'),
    ('Water Quality Monitor',  'EPA-2022-112',  'Completed'),
    ('General Lab Operations', 'INTERNAL-OPS',  'Active');

INSERT OR IGNORE INTO categories (category_name) VALUES
    ('Capital Equipment'),
    ('Electronics/Sensors'),
    ('IT/Computing'),
    ('Tools/Hardware'),
    ('Consumables');
"""



def _get_github_config():
    """Return (token, repo, filepath) from st.secrets, or None if not configured."""
    try:
        token = st.secrets["GITHUB_TOKEN"]
        repo  = st.secrets["GITHUB_REPO"]        # e.g. "agelos259/Lab_Items"
        path  = st.secrets.get("GITHUB_DB_PATH", "lab_inventory.db")
        return token, repo, path
    except Exception:
        return None



def _push_db_to_github() -> None:
    """Push the current DB file to GitHub. Always fetches the current SHA first."""
    cfg = _get_github_config()
    if not cfg:
        return
    token, repo, gh_path = cfg
    api_url = f"https://api.github.com/repos/{repo}/contents/{gh_path}"
    headers = {"Authorization": f"token {token}"}
    try:
        # Step 1: get current SHA (required by GitHub API to update an existing file)
        sha = None
        r = requests.get(api_url, headers=headers, timeout=10)
        if r.status_code == 200:
            sha = r.json()["sha"]

        # Step 2: push the updated DB
        with open(DB_PATH, "rb") as f:
            content = base64.b64encode(f.read()).decode()
        payload = {"message": "chore: sync database", "content": content}
        if sha:
            payload["sha"] = sha
        requests.put(api_url, headers=headers, json=payload, timeout=15)
    except Exception:
        pass  # never let a sync failure break the app


class _SyncedConnection(sqlite3.Connection):
    """sqlite3.Connection subclass that pushes the DB to GitHub on every commit."""
    def commit(self):
        super().commit()
        _push_db_to_github()


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, factory=_SyncedConnection)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def migrate_db() -> None:
    """Add missing columns, remove CHECK constraints, create categories table and FK."""
    conn = get_connection()

    # ── 1. Add any missing plain columns to items ──────────────────────────
    new_cols = [
        ("model",               "TEXT"),
        ("quantity",            "INTEGER DEFAULT 1"),
        ("received",            "TEXT"),
        ("unit_price_ex_vat",   "REAL"),
        ("unit_price_inc_vat",  "REAL"),
        ("total_price_ex_vat",  "REAL"),
        ("total_price_inc_vat", "REAL"),
        ("category_id",         "INTEGER"),
    ]
    existing = {row[1] for row in conn.execute("PRAGMA table_info(items)").fetchall()}
    for col_name, col_def in new_cols:
        if col_name not in existing:
            conn.execute(f"ALTER TABLE items ADD COLUMN {col_name} {col_def}")
    conn.commit()

    # ── 2. Create categories table if missing ─────────────────────────────
    has_cat_table = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='categories'"
    ).fetchone()[0]
    if not has_cat_table:
        conn.execute(
            "CREATE TABLE categories "
            "(category_id INTEGER PRIMARY KEY AUTOINCREMENT, category_name TEXT NOT NULL UNIQUE)"
        )
        for cat in CATEGORIES:
            conn.execute("INSERT OR IGNORE INTO categories (category_name) VALUES (?)", (cat,))
        conn.commit()

    # ── 3. Populate categories from existing items.category text ──────────
    existing_text_cats = conn.execute(
        "SELECT DISTINCT category FROM items WHERE category IS NOT NULL AND category != ''"
    ).fetchall()
    for row in existing_text_cats:
        conn.execute(
            "INSERT OR IGNORE INTO categories (category_name) VALUES (?)", (row[0],)
        )
    conn.commit()

    # ── 4. Back-fill category_id for items that have category text but no id
    conn.execute("""
        UPDATE items SET category_id = (
            SELECT category_id FROM categories WHERE category_name = items.category
        )
        WHERE category_id IS NULL AND category IS NOT NULL
    """)
    conn.commit()

    # ── 5. Remove CHECK constraints if still present (recreate table) ─────
    schema_row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='items'"
    ).fetchone()
    if schema_row and "CHECK" in schema_row[0]:
        conn.executescript("""
            PRAGMA foreign_keys = OFF;
            BEGIN;
            CREATE TABLE items_new (
                internal_id          TEXT    PRIMARY KEY,
                item_name            TEXT    NOT NULL,
                category             TEXT,
                category_id          INTEGER,
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
                project_id           INTEGER,
                user_id              INTEGER,
                location_id          INTEGER NOT NULL,
                FOREIGN KEY (category_id) REFERENCES categories(category_id),
                FOREIGN KEY (project_id)  REFERENCES projects(project_id),
                FOREIGN KEY (user_id)     REFERENCES users(user_id),
                FOREIGN KEY (location_id) REFERENCES locations(location_id)
            );
            INSERT INTO items_new SELECT
                internal_id, item_name, category, category_id, model, manufacturer_sn,
                quantity, condition, received, unit_price_ex_vat, unit_price_inc_vat,
                total_price_ex_vat, total_price_inc_vat, expected_return_date,
                project_id, user_id, location_id
            FROM items;
            DROP TABLE items;
            ALTER TABLE items_new RENAME TO items;
            COMMIT;
            PRAGMA foreign_keys = ON;
        """)

    # ── 3. Create login_accounts table if missing ─────────────────────────
    conn.execute("""
        CREATE TABLE IF NOT EXISTS login_accounts (
            account_id    INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT    NOT NULL UNIQUE,
            password_hash TEXT    NOT NULL,
            salt          TEXT    NOT NULL,
            role          TEXT    NOT NULL DEFAULT 'viewer'
                          CHECK(role IN ('admin', 'viewer'))
        )
    """)
    conn.commit()
    conn.close()


def initialize_db() -> None:
    conn = get_connection()
    conn.executescript(SCHEMA_SQL)

    # Only seed lookup tables when the database is brand new
    is_fresh = conn.execute("SELECT COUNT(*) FROM locations").fetchone()[0] == 0
    if is_fresh:
        conn.executescript(SEED_SQL)

    conn.commit()
    conn.close()
    migrate_db()
    _seed_admin_account()


# ── Auth helpers ─────────────────────────────────────────────────────────────

def _hash_password(password: str, salt: str) -> str:
    """Return a hex PBKDF2-SHA256 hash of password+salt."""
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt.encode(), 260_000
    ).hex()


def _verify_password(password: str, salt: str, stored_hash: str) -> bool:
    return secrets.compare_digest(_hash_password(password, salt), stored_hash)


def _seed_admin_account() -> None:
    """Insert a default admin account if no accounts exist yet."""
    conn = get_connection()
    count = conn.execute("SELECT COUNT(*) FROM login_accounts").fetchone()[0]
    if count == 0:
        salt = secrets.token_hex(16)
        pw_hash = _hash_password("admin", salt)
        conn.execute(
            "INSERT INTO login_accounts (username, password_hash, salt, role) VALUES (?,?,?,?)",
            ("admin", pw_hash, salt, "admin"),
        )
        conn.commit()
    conn.close()


def _get_account(username: str):
    """Return the login_accounts row for username, or None."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM login_accounts WHERE username=?", (username,)
    ).fetchone()
    conn.close()
    return row


# ── ID generation ─────────────────────────────────────────────────────────────

def get_next_lab_id(conn: sqlite3.Connection) -> str:
    cur = conn.execute(
        "SELECT internal_id FROM items "
        "ORDER BY CAST(SUBSTR(internal_id,5) AS INTEGER) DESC LIMIT 1"
    )
    row = cur.fetchone()
    if not row:
        return "LAB-001"
    last_num = int(row["internal_id"].split("-")[1])
    return f"LAB-{last_num + 1:03d}"


# ── Helper queries ────────────────────────────────────────────────────────────

def fetch_df(query: str, params: tuple = ()) -> pd.DataFrame:
    conn = get_connection()
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df


def fetch_lookup(table: str, id_col: str, label_col: str) -> dict:
    """Return {id: label} dict for a lookup table."""
    df = fetch_df(f"SELECT {id_col}, {label_col} FROM {table} ORDER BY {label_col}")
    return dict(zip(df[id_col], df[label_col]))


def get_or_create_location(conn: sqlite3.Connection, name: str) -> int:
    """Return location_id for name, inserting a new row if needed."""
    name = name.strip()
    row = conn.execute(
        "SELECT location_id FROM locations WHERE location_name=?", (name,)
    ).fetchone()
    if row:
        return row["location_id"]
    cur = conn.execute("INSERT INTO locations (location_name) VALUES (?)", (name,))
    return cur.lastrowid


def get_or_create_category(conn: sqlite3.Connection, name: str) -> int:
    """Return category_id for name, inserting into categories table if needed."""
    name = name.strip()
    row = conn.execute(
        "SELECT category_id FROM categories WHERE category_name=?", (name,)
    ).fetchone()
    if row:
        return row["category_id"]
    cur = conn.execute("INSERT INTO categories (category_name) VALUES (?)", (name,))
    return cur.lastrowid


ITEMS_FULL_QUERY = """
SELECT
    i.internal_id                                        AS "ID",
    i.item_name                                          AS "Item Name",
    i.model                                              AS "Model",
    COALESCE(cat.category_name, i.category, '—')        AS "Category",
    i.manufacturer_sn                                    AS "S/N",
    i.quantity                                           AS "Qty",
    i.condition                                          AS "Condition",
    COALESCE(i.received, '—')                            AS "Received",
    COALESCE(u.name, '—')                                AS "Assigned To",
    COALESCE(p.project_name, '—')                        AS "Project",
    l.location_name                                      AS "Location",
    COALESCE(CAST(i.unit_price_ex_vat  AS TEXT), '—')   AS "Unit (ex VAT)",
    COALESCE(CAST(i.unit_price_inc_vat AS TEXT), '—')   AS "Unit (inc VAT)",
    COALESCE(CAST(i.total_price_ex_vat  AS TEXT), '—')  AS "Total (ex VAT)",
    COALESCE(CAST(i.total_price_inc_vat AS TEXT), '—')  AS "Total (inc VAT)",
    COALESCE(i.expected_return_date, '—')                AS "Return Date"
FROM items i
LEFT JOIN categories cat ON i.category_id = cat.category_id
LEFT JOIN users      u   ON i.user_id     = u.user_id
LEFT JOIN projects   p   ON i.project_id  = p.project_id
LEFT JOIN locations  l   ON i.location_id = l.location_id
"""


# ── Streamlit pages ──────────────────────────────────────────────────────────

def page_dashboard() -> None:
    st.title("Lab Inventory — Dashboard")

    conn = get_connection()
    total      = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    available  = conn.execute("SELECT COUNT(*) FROM items WHERE condition='Available'").fetchone()[0]
    in_use     = conn.execute("SELECT COUNT(*) FROM items WHERE condition='In Use'").fetchone()[0]
    needs_attn = conn.execute(
        "SELECT COUNT(*) FROM items WHERE condition IN ('Broken','Needs Repair')"
    ).fetchone()[0]
    offsite = conn.execute(
        "SELECT COUNT(*) FROM items WHERE location_id = "
        "(SELECT location_id FROM locations WHERE location_name='Off-Site / Home')"
    ).fetchone()[0]
    conn.close()

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total Items",     total)
    c2.metric("Available",       available)
    c3.metric("In Use",          in_use)
    c4.metric("Needs Attention", needs_attn, delta_color="inverse")
    c5.metric("Off-Site",        offsite)

    st.divider()
    st.subheader("Items Needing Attention")
    df_attn = fetch_df(ITEMS_FULL_QUERY + " WHERE i.condition IN ('Broken','Needs Repair')")
    if df_attn.empty:
        st.success("No items need attention.")
    else:
        st.dataframe(df_attn, use_container_width=True, hide_index=True)

    st.subheader("Currently Off-Site")
    df_off = fetch_df(ITEMS_FULL_QUERY + " WHERE l.location_name = 'Off-Site / Home'")
    if df_off.empty:
        st.info("No items off-site.")
    else:
        st.dataframe(df_off, use_container_width=True, hide_index=True)


def page_all_items() -> None:
    st.title("All Items")

    projs    = fetch_lookup("projects",   "project_id",  "project_name")
    cats_df  = fetch_df("SELECT category_name FROM categories ORDER BY category_name")
    cat_list = cats_df["category_name"].tolist()
    locs     = fetch_lookup("locations", "location_id", "location_name")
    users    = fetch_lookup("users",     "user_id",     "name")

    c1, c2, c3, c4 = st.columns([3, 2, 2, 2])
    search      = c1.text_input("Search by name, model or ID", "")
    proj_filter = c2.selectbox("Filter by project",   ["All"] + list(projs.values()))
    cond_filter = c3.selectbox("Filter by condition", ["All"] + CONDITIONS)
    cat_filter  = c4.selectbox("Filter by category",  ["All"] + cat_list)

    query  = ITEMS_FULL_QUERY + " WHERE 1=1"
    params: list = []
    if search:
        query += " AND (i.item_name LIKE ? OR i.internal_id LIKE ? OR i.model LIKE ?)"
        params += [f"%{search}%", f"%{search}%", f"%{search}%"]
    if proj_filter != "All":
        proj_id_f = [k for k, v in projs.items() if v == proj_filter][0]
        query    += " AND i.project_id = ?"
        params.append(proj_id_f)
    if cond_filter != "All":
        query += " AND i.condition = ?"
        params.append(cond_filter)
    if cat_filter != "All":
        query += " AND COALESCE(cat.category_name, i.category) = ?"
        params.append(cat_filter)
    query += " ORDER BY CAST(SUBSTR(i.internal_id,5) AS INTEGER)"

    df = fetch_df(query, tuple(params))

    # Drop columns the user doesn't want to see
    df = df.drop(columns=["Model", "Received", "Return Date"], errors="ignore")

    # Convert price columns from '—' strings to proper floats for the editor
    for price_col in ("Unit (ex VAT)", "Unit (inc VAT)"):
        if price_col in df.columns:
            df[price_col] = pd.to_numeric(df[price_col].replace("—", None), errors="coerce")

    st.caption(
        f"{len(df)} item(s) — "
        "edit **Assigned To**, **Location**, **Unit (ex VAT)** or **Unit (inc VAT)** directly in the table."
    )

    user_options = ["— Unassigned —"] + list(users.values())
    loc_options  = list(locs.values())

    EDITABLE = {"Assigned To", "Location", "Unit (ex VAT)", "Unit (inc VAT)"}
    readonly_cols = {c: st.column_config.TextColumn(c, disabled=True)
                     for c in df.columns if c not in EDITABLE}

    edited = st.data_editor(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            **readonly_cols,
            "Assigned To": st.column_config.SelectboxColumn(
                "Assigned To", options=user_options, required=False
            ),
            "Location": st.column_config.SelectboxColumn(
                "Location", options=loc_options, required=True
            ),
            "Unit (ex VAT)":  st.column_config.NumberColumn("Unit (ex VAT)",  min_value=0.0, format="%.2f"),
            "Unit (inc VAT)": st.column_config.NumberColumn("Unit (inc VAT)", min_value=0.0, format="%.2f"),
        },
        key="all_items_editor",
    )

    # Detect changed rows and persist
    changed = df.compare(edited, keep_shape=False, keep_equal=False)
    if not changed.empty:
        changed_ids = changed.index.tolist()
        conn = get_connection()
        saved = 0
        try:
            for idx in changed_ids:
                row_new  = edited.iloc[idx]
                item_id  = row_new["ID"]
                new_user = row_new["Assigned To"]
                new_loc  = row_new["Location"]

                user_id   = None if new_user == "— Unassigned —" \
                            else [k for k, v in users.items() if v == new_user][0]
                loc_id    = [k for k, v in locs.items() if v == new_loc][0]
                condition = "Available" if user_id is None else "In Use"

                unit_ex  = row_new.get("Unit (ex VAT)")
                unit_inc = row_new.get("Unit (inc VAT)")
                unit_ex  = float(unit_ex)  if pd.notna(unit_ex)  else None
                unit_inc = float(unit_inc) if pd.notna(unit_inc) else None

                conn.execute(
                    """UPDATE items SET user_id=?, location_id=?, condition=?,
                       unit_price_ex_vat=?, unit_price_inc_vat=?
                       WHERE internal_id=?""",
                    (user_id, loc_id, condition, unit_ex, unit_inc, item_id),
                )
                saved += 1
            conn.commit()
        except sqlite3.Error as e:
            st.error(f"Database error: {e}")
        finally:
            conn.close()

        if saved:
            st.success(f"Saved changes to {saved} item(s).")
            st.rerun()


def page_add_item() -> None:
    st.title("Add New Item")

    conn    = get_connection()
    next_id = get_next_lab_id(conn)
    locs    = fetch_lookup("locations", "location_id", "location_name")
    users   = fetch_lookup("users",     "user_id",     "name")
    projs   = fetch_lookup("projects",  "project_id",  "project_name")
    cats    = fetch_lookup("categories","category_id", "category_name")
    conn.close()

    st.info(f"Next available ID: **{next_id}**")

    with st.form("add_item_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        item_name = c1.text_input("Item Name *")
        model     = c2.text_input("Model")

        c3, c4, c5 = st.columns(3)
        cat_names  = list(cats.values())
        cat_label  = c3.selectbox("Category *", cat_names)
        cat_id     = [k for k, v in cats.items() if v == cat_label][0]
        condition  = c4.selectbox("Condition *", CONDITIONS)
        received   = c5.selectbox("Received", ["—", "ΝΑΙ", "ΟΧΙ"])

        c6, c7 = st.columns(2)
        sn  = c6.text_input("Serial Number / S/N (optional)")
        qty = c7.number_input("Quantity", min_value=1, value=1, step=1)

        st.markdown("**Pricing** (optional)")
        p1, p2, p3, p4 = st.columns(4)
        unit_ex  = p1.number_input("Unit Price ex VAT",  min_value=0.0, value=0.0, step=0.01, format="%.2f")
        unit_inc = p2.number_input("Unit Price inc VAT", min_value=0.0, value=0.0, step=0.01, format="%.2f")
        tot_ex   = p3.number_input("Total Price ex VAT", min_value=0.0, value=0.0, step=0.01, format="%.2f")
        tot_inc  = p4.number_input("Total Price inc VAT",min_value=0.0, value=0.0, step=0.01, format="%.2f")

        loc_label = st.selectbox("Location *", list(locs.values()))
        loc_id    = [k for k, v in locs.items() if v == loc_label][0]

        proj_options = ["— None —"] + list(projs.values())
        proj_label   = st.selectbox("Project", proj_options)
        proj_id      = None if proj_label == "— None —" \
                       else [k for k, v in projs.items() if v == proj_label][0]

        user_options = ["— Unassigned —"] + list(users.values())
        user_label   = st.selectbox("Assigned To", user_options)
        user_id      = None if user_label == "— Unassigned —" \
                       else [k for k, v in users.items() if v == user_label][0]

        ret_date  = st.date_input("Expected Return Date (optional)", value=None)
        submitted = st.form_submit_button("Add Item", type="primary")

    if submitted:
        if not item_name.strip():
            st.error("Item Name is required.")
            return
        conn   = get_connection()
        new_id = get_next_lab_id(conn)
        try:
            conn.execute(
                """INSERT INTO items
                   (internal_id, item_name, category, category_id, model, manufacturer_sn,
                    quantity, condition, received,
                    unit_price_ex_vat, unit_price_inc_vat,
                    total_price_ex_vat, total_price_inc_vat,
                    expected_return_date, project_id, user_id, location_id)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (new_id, item_name.strip(), cat_label, cat_id,
                 model.strip() or None, sn.strip() or None, qty,
                 condition, None if received == "—" else received,
                 unit_ex or None, unit_inc or None, tot_ex or None, tot_inc or None,
                 ret_date.isoformat() if ret_date else None,
                 proj_id, user_id, loc_id),
            )
            conn.commit()
            st.success(f"Item added with ID **{new_id}**.")
        except sqlite3.Error as e:
            st.error(f"Database error: {e}")
        finally:
            conn.close()


def page_edit_item() -> None:
    st.title("Edit Item")

    all_ids = fetch_df(
        "SELECT internal_id, item_name FROM items "
        "ORDER BY CAST(SUBSTR(internal_id,5) AS INTEGER)"
    )
    if all_ids.empty:
        st.info("No items in database.")
        return

    id_labels = [f"{r['internal_id']} — {r['item_name']}" for _, r in all_ids.iterrows()]
    choice    = st.selectbox("Select item to edit", id_labels)
    chosen_id = choice.split(" — ")[0]

    conn  = get_connection()
    row   = conn.execute("SELECT * FROM items WHERE internal_id=?", (chosen_id,)).fetchone()
    locs  = fetch_lookup("locations", "location_id", "location_name")
    users = fetch_lookup("users",     "user_id",     "name")
    projs = fetch_lookup("projects",  "project_id",  "project_name")
    cats  = fetch_lookup("categories","category_id", "category_name")
    conn.close()

    if not row:
        st.error("Item not found.")
        return

    # Resolve current category: prefer category_id FK, fall back to text column
    cat_names   = list(cats.values())
    cur_cat_name = cats.get(row["category_id"], row["category"] or cat_names[0])
    cur_cat_idx  = cat_names.index(cur_cat_name) if cur_cat_name in cat_names else 0

    with st.form("edit_item_form"):
        c1, c2 = st.columns(2)
        item_name = c1.text_input("Item Name *", value=row["item_name"])
        model     = c2.text_input("Model", value=row["model"] or "")

        c3, c4, c5 = st.columns(3)
        cat_label  = c3.selectbox("Category *", cat_names, index=cur_cat_idx)
        cat_id     = [k for k, v in cats.items() if v == cat_label][0]
        condition  = c4.selectbox("Condition *", CONDITIONS,
                                   index=CONDITIONS.index(row["condition"]))
        recv_opts  = ["—", "ΝΑΙ", "ΟΧΙ"]
        cur_recv   = row["received"] if row["received"] in recv_opts else "—"
        received   = c5.selectbox("Received", recv_opts, index=recv_opts.index(cur_recv))

        c6, c7 = st.columns(2)
        sn  = c6.text_input("Serial Number / S/N", value=row["manufacturer_sn"] or "")
        qty = c7.number_input("Quantity", min_value=1, value=int(row["quantity"] or 1), step=1)

        st.markdown("**Pricing** (optional)")
        p1, p2, p3, p4 = st.columns(4)
        unit_ex  = p1.number_input("Unit Price ex VAT",  min_value=0.0,
                                    value=float(row["unit_price_ex_vat"]  or 0), step=0.01, format="%.2f")
        unit_inc = p2.number_input("Unit Price inc VAT", min_value=0.0,
                                    value=float(row["unit_price_inc_vat"] or 0), step=0.01, format="%.2f")
        tot_ex   = p3.number_input("Total Price ex VAT", min_value=0.0,
                                    value=float(row["total_price_ex_vat"]  or 0), step=0.01, format="%.2f")
        tot_inc  = p4.number_input("Total Price inc VAT",min_value=0.0,
                                    value=float(row["total_price_inc_vat"] or 0), step=0.01, format="%.2f")

        loc_names   = list(locs.values())
        loc_ids     = list(locs.keys())
        cur_loc_idx = loc_ids.index(row["location_id"]) if row["location_id"] in loc_ids else 0
        loc_label   = st.selectbox("Location *", loc_names, index=cur_loc_idx)
        loc_id      = [k for k, v in locs.items() if v == loc_label][0]

        proj_options = ["— None —"] + list(projs.values())
        cur_proj     = projs.get(row["project_id"], "— None —")
        proj_label   = st.selectbox("Project", proj_options,
                                     index=proj_options.index(cur_proj) if cur_proj in proj_options else 0)
        proj_id      = None if proj_label == "— None —" \
                       else [k for k, v in projs.items() if v == proj_label][0]

        user_options = ["— Unassigned —"] + list(users.values())
        cur_user     = users.get(row["user_id"], "— Unassigned —")
        user_label   = st.selectbox("Assigned To", user_options,
                                     index=user_options.index(cur_user) if cur_user in user_options else 0)
        user_id      = None if user_label == "— Unassigned —" \
                       else [k for k, v in users.items() if v == user_label][0]

        cur_ret  = None
        if row["expected_return_date"]:
            try:
                cur_ret = date.fromisoformat(row["expected_return_date"])
            except ValueError:
                pass
        ret_date  = st.date_input("Expected Return Date (optional)", value=cur_ret)
        submitted = st.form_submit_button("Save Changes", type="primary")

    if submitted:
        if not item_name.strip():
            st.error("Item Name is required.")
            return
        conn = get_connection()
        try:
            conn.execute(
                """UPDATE items SET
                   item_name=?, category=?, category_id=?, model=?, manufacturer_sn=?,
                   quantity=?, condition=?, received=?,
                   unit_price_ex_vat=?, unit_price_inc_vat=?,
                   total_price_ex_vat=?, total_price_inc_vat=?,
                   expected_return_date=?, project_id=?, user_id=?, location_id=?
                   WHERE internal_id=?""",
                (item_name.strip(), cat_label, cat_id,
                 model.strip() or None, sn.strip() or None, qty,
                 condition, None if received == "—" else received,
                 unit_ex or None, unit_inc or None, tot_ex or None, tot_inc or None,
                 ret_date.isoformat() if ret_date else None,
                 proj_id, user_id, loc_id, chosen_id),
            )
            conn.commit()
            st.success(f"Item **{chosen_id}** updated.")
        except sqlite3.Error as e:
            st.error(f"Database error: {e}")
        finally:
            conn.close()

    # ── Delete ─────────────────────────────────────────────────────────────
    st.divider()
    st.subheader("Delete Item")
    confirm_del = st.checkbox(f"I confirm I want to permanently delete **{chosen_id}**")
    if st.button("Delete Item", type="primary", disabled=not confirm_del):
        conn = get_connection()
        try:
            conn.execute("DELETE FROM items WHERE internal_id=?", (chosen_id,))
            conn.commit()
            st.success(f"Item **{chosen_id}** deleted.")
            st.rerun()
        except sqlite3.Error as e:
            st.error(f"Database error: {e}")
        finally:
            conn.close()


def page_checkout() -> None:
    st.title("Check-Out / Check-In Item")

    all_items = fetch_df(
        "SELECT internal_id, item_name, condition FROM items "
        "ORDER BY CAST(SUBSTR(internal_id,5) AS INTEGER)"
    )
    if all_items.empty:
        st.info("No items in database.")
        return

    id_labels = [f"{r['internal_id']} — {r['item_name']} [{r['condition']}]"
                 for _, r in all_items.iterrows()]
    choice    = st.selectbox("Select Item", id_labels)
    chosen_id = choice.split(" — ")[0]

    locs  = fetch_lookup("locations", "location_id", "location_name")
    users = fetch_lookup("users",     "user_id",     "name")

    tab_out, tab_in = st.tabs(["Check-Out", "Check-In / Return"])

    with tab_out:
        with st.form("checkout_form"):
            st.subheader(f"Check Out: {chosen_id}")
            user_label = st.selectbox("Assign To *", ["— Select user —"] + list(users.values()))
            user_id    = None if user_label == "— Select user —" \
                         else [k for k, v in users.items() if v == user_label][0]

            offsite_default = next(
                (i for i, n in enumerate(locs.values()) if "Off-Site" in n), 0
            )
            loc_label    = st.selectbox("New Location *", list(locs.values()), index=offsite_default)
            loc_id       = [k for k, v in locs.items() if v == loc_label][0]
            co_submitted = st.form_submit_button("Confirm Check-Out", type="primary")

        if co_submitted:
            if not user_id:
                st.error("Please select a user.")
            else:
                conn = get_connection()
                try:
                    conn.execute(
                        "UPDATE items SET condition='In Use', user_id=?, location_id=? "
                        "WHERE internal_id=?",
                        (user_id, loc_id, chosen_id),
                    )
                    conn.commit()
                    st.success(f"**{chosen_id}** checked out to **{user_label}** — Location: {loc_label}")
                except sqlite3.Error as e:
                    st.error(f"Database error: {e}")
                finally:
                    conn.close()

    with tab_in:
        with st.form("checkin_form"):
            st.subheader(f"Return / Check In: {chosen_id}")
            default_ci   = next(
                (i for i, n in enumerate(locs.values()) if "Off-Site" not in n), 0
            )
            loc_label_ci = st.selectbox("Return To Location *", list(locs.values()), index=default_ci)
            loc_id_ci    = [k for k, v in locs.items() if v == loc_label_ci][0]
            new_condition = st.selectbox("Set Condition", CONDITIONS)
            ci_submitted  = st.form_submit_button("Confirm Check-In", type="primary")

        if ci_submitted:
            conn = get_connection()
            try:
                conn.execute(
                    "UPDATE items SET condition=?, user_id=NULL, location_id=? "
                    "WHERE internal_id=?",
                    (new_condition, loc_id_ci, chosen_id),
                )
                conn.commit()
                st.success(f"**{chosen_id}** returned — Location: {loc_label_ci} | Condition: {new_condition}")
            except sqlite3.Error as e:
                st.error(f"Database error: {e}")
            finally:
                conn.close()


def page_import_excel() -> None:
    st.title("Import from Excel")

    # ── Step 1: Select project (required) ─────────────────────────────────
    st.subheader("Step 1 — Select Project")
    projs = fetch_lookup("projects", "project_id", "project_name")

    if not projs:
        st.error("No projects found. Please add a project first via Manage Lookups.")
        return

    proj_options = ["— Select a project —"] + list(projs.values())
    proj_label   = st.selectbox("Project this equipment belongs to *", proj_options)

    if proj_label == "— Select a project —":
        st.info("Select a project above to continue.")
        return

    proj_id = [k for k, v in projs.items() if v == proj_label][0]
    st.success(f"Project: **{proj_label}**")

    st.divider()

    # ── Step 2: Upload file ────────────────────────────────────────────────
    st.subheader("Step 2 — Upload Excel File")
    st.caption(
        "Expected columns (Greek headers): "
        "**A/A · ΕΙΔΟΣ · ΜΟΝΤΕΛΟ · ΤΕΜΑΧΙΑ · S/N · "
        "ΤΙΜΗ ΤΕΜΑΧΙΟΥ ΧΩΡΙΣ ΦΠΑ · ΤΙΜΗ ΤΕΜΑΧΙΟΥ ΜΕ ΦΠΑ · "
        "ΤΙΜΗ ΠΟΣΟΤΗΤΑΣ ΧΩΡΙΣ ΦΠΑ · ΤΙΜΗ ΠΟΣΟΤΗΤΑΣ ΜΕ ΦΠΑ · "
        "ΠΑΡΑΛΑΒΗ (ΝΑΙ/ ΟΧΙ) · ΤΟΠΟΘΕΣΙΑ**"
    )

    with st.expander("Advanced parse options", expanded=False):
        header_row = st.number_input(
            "Header row (0 = first row, 1 = second row, etc.)",
            min_value=0, max_value=10, value=0, step=1,
        )
        sheet_name = st.text_input("Sheet name (leave blank for first sheet)", value="")

    uploaded = st.file_uploader("Choose an .xlsx or .xls file", type=["xlsx", "xls"])
    if not uploaded:
        return

    # ── Read file ──────────────────────────────────────────────────────────
    try:
        sheet = sheet_name.strip() if sheet_name.strip() else 0
        raw   = pd.read_excel(
            io.BytesIO(uploaded.read()),
            sheet_name=sheet,
            header=int(header_row),
            dtype=str,
        )
    except Exception as e:
        st.error(f"Could not read file: {e}")
        return

    raw.columns = [str(c).strip() for c in raw.columns]

    rename_map = {orig: mapped for orig, mapped in EXCEL_COL_MAP.items() if orig in raw.columns}
    df = raw.rename(columns=rename_map)

    # ΜΟΝΤΕΛΟ (col 3) is now item_name; ΕΙΔΟΣ (col 2) is category
    if "item_name" not in df.columns:
        st.error(
            "Column **ΜΟΝΤΕΛΟ** (product name) not found. "
            f"Detected columns: {', '.join(raw.columns.tolist())}"
        )
        return

    df = df[df["item_name"].notna() & (df["item_name"].astype(str).str.strip() != "")]
    df = df[df["item_name"].astype(str).str.strip() != "nan"]

    if df.empty:
        st.warning("No data rows found after filtering empty product names (ΜΟΝΤΕΛΟ).")
        return

    # Count total instances that will be created
    def _parse_qty(val):
        try:
            n = int(float(str(val).strip()))
            return max(n, 1)
        except (ValueError, TypeError):
            return 1

    total_instances = sum(_parse_qty(r.get("quantity", 1)) for _, r in df.iterrows())
    st.success(f"Parsed **{len(df)} rows** → will create **{total_instances} individual items**.")
    st.divider()

    # ── Step 3: Default condition (category comes from ΕΙΔΟΣ column) ──────
    st.subheader("Step 3 — Set Defaults")
    st.caption(
        "Category is read from the **ΕΙΔΟΣ** column. "
        "The fallback below is used only when that column is empty."
    )
    col_b, col_c = st.columns(2)
    default_cat  = col_b.selectbox("Fallback Category", CATEGORIES)
    default_cond = col_c.selectbox("Default Condition *", CONDITIONS, index=0)

    st.divider()

    # ── Step 4: Preview ────────────────────────────────────────────────────
    st.subheader("Step 4 — Preview")
    preview_cols = [c for c in [
        "excel_category", "item_name", "quantity", "manufacturer_sn",
        "received", "location_name",
        "unit_price_ex_vat", "unit_price_inc_vat",
        "total_price_ex_vat", "total_price_inc_vat",
    ] if c in df.columns]
    rename_preview = {"excel_category": "Category (ΕΙΔΟΣ)", "item_name": "Product Name (ΜΟΝΤΕΛΟ)"}
    st.dataframe(
        df[preview_cols].rename(columns=rename_preview).head(20),
        use_container_width=True, hide_index=True,
    )
    if len(df) > 20:
        st.caption(f"Showing 20 of {len(df)} rows.")

    st.divider()

    # ── Step 5: Confirm import ─────────────────────────────────────────────
    st.subheader("Step 5 — Import")
    st.markdown(
        f"Ready to create **{total_instances} individual items** "
        f"({len(df)} rows × quantity) into project **{proj_label}**."
    )

    if st.button("Import All Rows into Database", type="primary"):
        conn     = get_connection()
        inserted = 0
        skipped  = 0
        new_locs: list[str] = []

        def to_float(val):
            try:
                return float(str(val).replace(",", ".").strip())
            except (ValueError, TypeError):
                return None

        try:
            for _, r in df.iterrows():
                name = str(r.get("item_name", "")).strip()
                if not name or name == "nan":
                    skipped += 1
                    continue

                # Category: use ΕΙΔΟΣ column if present, else fallback; always get/create FK
                cat_raw  = str(r.get("excel_category", "")).strip()
                category = cat_raw if (cat_raw and cat_raw != "nan") else default_cat
                cat_id   = get_or_create_category(conn, category)

                # Location
                loc_raw = str(r.get("location_name", "")).strip()
                if loc_raw and loc_raw != "nan":
                    loc_id = get_or_create_location(conn, loc_raw)
                    new_locs.append(loc_raw)
                else:
                    loc_id = conn.execute(
                        "SELECT location_id FROM locations LIMIT 1"
                    ).fetchone()["location_id"]

                sn       = str(r.get("manufacturer_sn", "")).strip() or None
                received = str(r.get("received", "")).strip() or None
                qty      = _parse_qty(r.get("quantity", 1))

                # Create qty separate items, each with its own LAB-XXX id
                for _ in range(qty):
                    new_id = get_next_lab_id(conn)
                    conn.execute(
                        """INSERT INTO items
                           (internal_id, item_name, category, category_id, manufacturer_sn,
                            quantity, condition, received,
                            unit_price_ex_vat, unit_price_inc_vat,
                            total_price_ex_vat, total_price_inc_vat,
                            project_id, location_id)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            new_id, name, category, cat_id, sn,
                            1, default_cond, received,
                            to_float(r.get("unit_price_ex_vat")),
                            to_float(r.get("unit_price_inc_vat")),
                            to_float(r.get("total_price_ex_vat")),
                            to_float(r.get("total_price_inc_vat")),
                            proj_id, loc_id,
                        ),
                    )
                    inserted += 1

            conn.commit()
            st.success(
                f"Import complete: **{inserted} items created** in *{proj_label}*, "
                f"{skipped} rows skipped."
            )
            created = list(set(new_locs))
            if created:
                st.info(f"New locations auto-created: {', '.join(created)}")

        except sqlite3.Error as e:
            conn.rollback()
            st.error(f"Database error (rolled back): {e}")
        finally:
            conn.close()


def _bulk_delete_panel(
    df: pd.DataFrame,
    id_col: str,
    label_col: str,
    table: str,
    editor_key: str,
    label_singular: str,
    db_id_col: str | None = None,   # real DB column name; defaults to id_col
) -> None:
    """Read-only table + multiselect picker + confirm-and-delete."""
    if df.empty:
        st.info(f"No {label_singular.lower()}s found.")
        return

    df = df.copy().reset_index(drop=True)

    # Read-only display table
    st.dataframe(df, use_container_width=True, hide_index=True)

    # Build option strings: "ID — Label"  (unique even if labels repeat)
    option_map: dict[str, str] = {
        str(row[id_col]): f"{row[id_col]} — {row[label_col]}"
        for _, row in df.iterrows()
    }
    all_ids    = list(option_map.keys())
    all_labels = list(option_map.values())

    ms_key = f"{editor_key}_ms"

    # Select All / Clear All
    b1, b2, _ = st.columns([1, 1, 6])
    if b1.button("Select All", key=f"{editor_key}_sel_all"):
        st.session_state[ms_key] = all_labels
    if b2.button("Clear All", key=f"{editor_key}_clr_all"):
        st.session_state[ms_key] = []

    selected_labels = st.multiselect(
        f"Choose {label_singular.lower()}(s) to delete",
        options=all_labels,
        default=st.session_state.get(ms_key, []),
        key=ms_key,
    )

    # Map chosen labels back to IDs
    label_to_id = {v: k for k, v in option_map.items()}
    selected_ids = [label_to_id[lbl] for lbl in selected_labels]
    n = len(selected_ids)

    st.caption(f"{n} of {len(df)} {label_singular.lower()}(s) selected")

    if n == 0:
        return

    st.warning(
        f"About to permanently delete **{n} {label_singular.lower()}(s)**: "
        + ", ".join(f"`{lbl.split(' — ', 1)[-1]}`" for lbl in selected_labels)
    )
    confirm = st.checkbox(
        f"Yes, delete these {n} {label_singular.lower()}(s)",
        key=f"{editor_key}_chk",
    )

    if st.button(
        f"Delete {n} Selected {label_singular}(s)",
        type="primary",
        disabled=not confirm,
        key=f"{editor_key}_btn",
    ):
        real_id_col = db_id_col if db_id_col else id_col
        conn = get_connection()
        deleted, failed = [], []
        try:
            for rid, lbl in zip(selected_ids, selected_labels):
                display = lbl.split(" — ", 1)[-1]
                try:
                    conn.execute(f"DELETE FROM {table} WHERE {real_id_col} = ?", (rid,))
                    conn.commit()
                    deleted.append(display)
                except sqlite3.Error:
                    conn.rollback()
                    failed.append(display)
        finally:
            conn.close()

        if deleted:
            st.success(f"Deleted {len(deleted)}: {', '.join(deleted)}")
            st.session_state.pop(ms_key, None)   # reset multiselect after deletion
        if failed:
            st.error(
                f"Could not delete {len(failed)} (still referenced by items): "
                + ", ".join(failed)
            )
        if deleted:
            st.rerun()


def page_bulk_delete() -> None:
    st.title("Bulk Delete")
    st.markdown(
        "Tick the **Select** checkbox on the rows you want to remove, "
        "then confirm and click the delete button."
    )

    tab_items, tab_cats, tab_locs, tab_users, tab_projs = st.tabs(
        ["Items", "Categories", "Locations", "Users", "Projects"]
    )

    # ── Items ──────────────────────────────────────────────────────────────
    with tab_items:
        c1, c2, c3 = st.columns([3, 2, 2])
        search      = c1.text_input("Search name / model / ID", "", key="bd_search")
        cond_filter = c2.selectbox("Condition", ["All"] + CONDITIONS, key="bd_cond")
        cat_filter  = c3.selectbox("Category",  ["All"] + CATEGORIES, key="bd_cat")

        query  = ITEMS_FULL_QUERY + " WHERE 1=1"
        params: list = []
        if search:
            query  += " AND (i.item_name LIKE ? OR i.internal_id LIKE ? OR i.model LIKE ?)"
            params += [f"%{search}%", f"%{search}%", f"%{search}%"]
        if cond_filter != "All":
            query  += " AND i.condition = ?"
            params.append(cond_filter)
        if cat_filter != "All":
            query  += " AND i.category = ?"
            params.append(cat_filter)
        query += " ORDER BY CAST(SUBSTR(i.internal_id,5) AS INTEGER)"

        df_items = fetch_df(query, tuple(params))
        _bulk_delete_panel(df_items, "ID", "Item Name", "items",
                           "bd_items", "Item", db_id_col="internal_id")

    # ── Categories ─────────────────────────────────────────────────────────
    with tab_cats:
        df_cats = fetch_df(
            """SELECT c.category_id AS category_id,
                      c.category_name AS 'Category Name',
                      COUNT(i.internal_id) AS 'Items Linked'
               FROM categories c
               LEFT JOIN items i ON i.category_id = c.category_id
               GROUP BY c.category_id
               ORDER BY c.category_name"""
        )
        blocked = df_cats[df_cats["Items Linked"] > 0]
        if not blocked.empty:
            st.warning(
                "Categories with items linked **cannot** be deleted: "
                + ", ".join(f"**{r}**" for r in blocked["Category Name"].tolist())
            )
        _bulk_delete_panel(df_cats, "category_id", "Category Name", "categories",
                           "bd_cats", "Category")

    # ── Locations ──────────────────────────────────────────────────────────
    with tab_locs:
        df_locs = fetch_df(
            """SELECT l.location_id AS location_id,
                      l.location_name AS 'Location Name',
                      COUNT(i.internal_id) AS 'Items Assigned'
               FROM locations l
               LEFT JOIN items i ON i.location_id = l.location_id
               GROUP BY l.location_id
               ORDER BY l.location_name"""
        )
        blocked = df_locs[df_locs["Items Assigned"] > 0]
        if not blocked.empty:
            st.warning(
                "The following locations have items and **cannot** be deleted until "
                "those items are removed first: "
                + ", ".join(f"**{r}**" for r in blocked["Location Name"].tolist())
            )
        _bulk_delete_panel(df_locs, "location_id", "Location Name", "locations",
                           "bd_locs", "Location")

    # ── Users ──────────────────────────────────────────────────────────────
    with tab_users:
        df_users = fetch_df(
            """SELECT u.user_id AS user_id,
                      u.name AS Name,
                      u.role AS Role,
                      u.email AS Email,
                      COUNT(i.internal_id) AS 'Items Assigned'
               FROM users u
               LEFT JOIN items i ON i.user_id = u.user_id
               GROUP BY u.user_id
               ORDER BY u.name"""
        )
        blocked = df_users[df_users["Items Assigned"] > 0]
        if not blocked.empty:
            st.warning(
                "The following users have items assigned and **cannot** be deleted: "
                + ", ".join(f"**{r}**" for r in blocked["Name"].tolist())
            )
        _bulk_delete_panel(df_users, "user_id", "Name", "users",
                           "bd_users", "User")

    # ── Projects ───────────────────────────────────────────────────────────
    with tab_projs:
        df_projs = fetch_df(
            """SELECT p.project_id AS project_id,
                      p.project_name AS 'Project Name',
                      p.grant_code AS 'Grant Code',
                      p.status AS Status,
                      COUNT(i.internal_id) AS 'Items Linked'
               FROM projects p
               LEFT JOIN items i ON i.project_id = p.project_id
               GROUP BY p.project_id
               ORDER BY p.project_name"""
        )
        blocked = df_projs[df_projs["Items Linked"] > 0]
        if not blocked.empty:
            st.warning(
                "The following projects have items linked and **cannot** be deleted: "
                + ", ".join(f"**{r}**" for r in blocked["Project Name"].tolist())
            )
        _bulk_delete_panel(df_projs, "project_id", "Project Name", "projects",
                           "bd_projs", "Project")



def page_manage() -> None:
    st.title("Manage Lookups")
    tab_cat, tab_loc, tab_usr, tab_proj = st.tabs(["Categories", "Locations", "Users", "Projects"])

    # ══════════════════════════════════════════════════════════════════════
    # CATEGORIES
    # ══════════════════════════════════════════════════════════════════════
    with tab_cat:
        st.subheader("All Categories")
        st.dataframe(fetch_df("SELECT category_id AS ID, category_name AS Name FROM categories ORDER BY category_name"),
                     use_container_width=True, hide_index=True)
        st.divider()

        st.markdown("##### Add New Category")
        with st.form("add_category"):
            new_cat = st.text_input("Category Name *")
            if st.form_submit_button("Add Category"):
                if new_cat.strip():
                    conn = get_connection()
                    try:
                        conn.execute("INSERT INTO categories (category_name) VALUES (?)", (new_cat.strip(),))
                        conn.commit()
                        st.success(f"Category '{new_cat.strip()}' added.")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("A category with that name already exists.")
                    finally:
                        conn.close()
                else:
                    st.error("Name cannot be blank.")

        st.divider()

        st.markdown("##### Edit or Delete a Category")
        cats_df = fetch_df("SELECT category_id, category_name FROM categories ORDER BY category_name")
        if not cats_df.empty:
            sel_cat_name = st.selectbox("Select category", cats_df["category_name"].tolist(), key="sel_cat_edit")
            sel_cat_id   = int(cats_df.loc[cats_df["category_name"] == sel_cat_name, "category_id"].iloc[0])

            with st.form("edit_category"):
                edited_cat = st.text_input("New Name *", value=sel_cat_name)
                if st.form_submit_button("Save Changes"):
                    if edited_cat.strip():
                        conn = get_connection()
                        try:
                            conn.execute("UPDATE categories SET category_name=? WHERE category_id=?",
                                         (edited_cat.strip(), sel_cat_id))
                            # Keep category text column in sync
                            conn.execute("UPDATE items SET category=? WHERE category_id=?",
                                         (edited_cat.strip(), sel_cat_id))
                            conn.commit()
                            st.success("Category updated.")
                            st.rerun()
                        except sqlite3.IntegrityError:
                            st.error("That name already exists.")
                        finally:
                            conn.close()
                    else:
                        st.error("Name cannot be blank.")

            confirm_cat = st.checkbox(f"Confirm deletion of **{sel_cat_name}**", key="del_cat_chk")
            if st.button("Delete Category", type="primary", disabled=not confirm_cat, key="del_cat_btn"):
                conn = get_connection()
                try:
                    conn.execute("DELETE FROM categories WHERE category_id=?", (sel_cat_id,))
                    conn.commit()
                    st.success(f"Category '{sel_cat_name}' deleted.")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("Cannot delete: items are still linked to this category.")
                finally:
                    conn.close()

    # ══════════════════════════════════════════════════════════════════════
    # LOCATIONS
    # ══════════════════════════════════════════════════════════════════════
    with tab_loc:
        st.subheader("All Locations")
        st.dataframe(fetch_df("SELECT location_id AS ID, location_name AS Name FROM locations ORDER BY location_name"),
                     use_container_width=True, hide_index=True)
        st.divider()

        # ── Add ──────────────────────────────────────────────────────────
        st.markdown("##### Add New Location")
        with st.form("add_location"):
            new_loc = st.text_input("Location Name *")
            if st.form_submit_button("Add Location"):
                if new_loc.strip():
                    conn = get_connection()
                    try:
                        conn.execute("INSERT INTO locations (location_name) VALUES (?)", (new_loc.strip(),))
                        conn.commit()
                        st.success(f"Location '{new_loc.strip()}' added.")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("A location with that name already exists.")
                    finally:
                        conn.close()
                else:
                    st.error("Name cannot be blank.")

        st.divider()

        # ── Edit / Delete ─────────────────────────────────────────────────
        st.markdown("##### Edit or Delete a Location")
        locs_df = fetch_df("SELECT location_id, location_name FROM locations ORDER BY location_name")
        if not locs_df.empty:
            loc_labels  = locs_df["location_name"].tolist()
            sel_loc_name = st.selectbox("Select location", loc_labels, key="sel_loc_edit")
            sel_loc_id   = int(locs_df.loc[locs_df["location_name"] == sel_loc_name, "location_id"].iloc[0])

            with st.form("edit_location"):
                edited_name = st.text_input("New Name *", value=sel_loc_name)
                if st.form_submit_button("Save Changes"):
                    if edited_name.strip():
                        conn = get_connection()
                        try:
                            conn.execute("UPDATE locations SET location_name=? WHERE location_id=?",
                                         (edited_name.strip(), sel_loc_id))
                            conn.commit()
                            st.success("Location updated.")
                            st.rerun()
                        except sqlite3.IntegrityError:
                            st.error("That name already exists.")
                        finally:
                            conn.close()
                    else:
                        st.error("Name cannot be blank.")

            confirm_loc = st.checkbox(f"Confirm deletion of **{sel_loc_name}**", key="del_loc_chk")
            if st.button("Delete Location", type="primary", disabled=not confirm_loc, key="del_loc_btn"):
                conn = get_connection()
                try:
                    conn.execute("DELETE FROM locations WHERE location_id=?", (sel_loc_id,))
                    conn.commit()
                    st.success(f"Location '{sel_loc_name}' deleted.")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("Cannot delete: items are still assigned to this location.")
                finally:
                    conn.close()

    # ══════════════════════════════════════════════════════════════════════
    # USERS
    # ══════════════════════════════════════════════════════════════════════
    with tab_usr:
        st.subheader("All Users")
        st.dataframe(fetch_df("SELECT user_id AS ID, name AS Name, role AS Role, email AS Email FROM users ORDER BY name"),
                     use_container_width=True, hide_index=True)
        st.divider()

        # ── Add ──────────────────────────────────────────────────────────
        st.markdown("##### Add New User")
        with st.form("add_user"):
            c1, c2 = st.columns(2)
            u_name  = c1.text_input("Full Name *")
            u_role  = c2.text_input("Role *")
            u_email = st.text_input("Email *")
            if st.form_submit_button("Add User"):
                if u_name.strip() and u_role.strip() and u_email.strip():
                    conn = get_connection()
                    try:
                        conn.execute("INSERT INTO users (name, role, email) VALUES (?,?,?)",
                                     (u_name.strip(), u_role.strip(), u_email.strip()))
                        conn.commit()
                        st.success(f"User '{u_name.strip()}' added.")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("A user with that email already exists.")
                    finally:
                        conn.close()
                else:
                    st.error("All fields are required.")

        st.divider()

        # ── Edit / Delete ─────────────────────────────────────────────────
        st.markdown("##### Edit or Delete a User")
        users_df = fetch_df("SELECT user_id, name, role, email FROM users ORDER BY name")
        if not users_df.empty:
            user_labels  = users_df["name"].tolist()
            sel_user_name = st.selectbox("Select user", user_labels, key="sel_usr_edit")
            sel_user_row  = users_df[users_df["name"] == sel_user_name].iloc[0]
            sel_user_id   = int(sel_user_row["user_id"])

            with st.form("edit_user"):
                c1, c2 = st.columns(2)
                e_name  = c1.text_input("Full Name *", value=sel_user_row["name"])
                e_role  = c2.text_input("Role *",      value=sel_user_row["role"])
                e_email = st.text_input("Email *",     value=sel_user_row["email"])
                if st.form_submit_button("Save Changes"):
                    if e_name.strip() and e_role.strip() and e_email.strip():
                        conn = get_connection()
                        try:
                            conn.execute("UPDATE users SET name=?, role=?, email=? WHERE user_id=?",
                                         (e_name.strip(), e_role.strip(), e_email.strip(), sel_user_id))
                            conn.commit()
                            st.success("User updated.")
                            st.rerun()
                        except sqlite3.IntegrityError:
                            st.error("That email is already used by another user.")
                        finally:
                            conn.close()
                    else:
                        st.error("All fields are required.")

            confirm_usr = st.checkbox(f"Confirm deletion of **{sel_user_name}**", key="del_usr_chk")
            if st.button("Delete User", type="primary", disabled=not confirm_usr, key="del_usr_btn"):
                conn = get_connection()
                try:
                    conn.execute("DELETE FROM users WHERE user_id=?", (sel_user_id,))
                    conn.commit()
                    st.success(f"User '{sel_user_name}' deleted.")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("Cannot delete: items are still assigned to this user.")
                finally:
                    conn.close()

    # ══════════════════════════════════════════════════════════════════════
    # PROJECTS
    # ══════════════════════════════════════════════════════════════════════
    with tab_proj:
        st.subheader("All Projects")
        st.dataframe(fetch_df("SELECT project_id AS ID, project_name AS Project, grant_code AS 'Grant Code', status AS Status FROM projects ORDER BY project_name"),
                     use_container_width=True, hide_index=True)
        st.divider()

        # ── Add ──────────────────────────────────────────────────────────
        st.markdown("##### Add New Project")
        with st.form("add_project"):
            c1, c2, c3 = st.columns(3)
            p_name   = c1.text_input("Project Name *")
            p_grant  = c2.text_input("Grant Code")
            p_status = c3.selectbox("Status", PROJECT_STATUSES)
            if st.form_submit_button("Add Project"):
                if p_name.strip():
                    conn = get_connection()
                    try:
                        conn.execute("INSERT INTO projects (project_name, grant_code, status) VALUES (?,?,?)",
                                     (p_name.strip(), p_grant.strip() or None, p_status))
                        conn.commit()
                        st.success(f"Project '{p_name.strip()}' added.")
                        st.rerun()
                    except sqlite3.Error as e:
                        st.error(f"Database error: {e}")
                    finally:
                        conn.close()
                else:
                    st.error("Project Name is required.")

        st.divider()

        # ── Edit / Delete ─────────────────────────────────────────────────
        st.markdown("##### Edit or Delete a Project")
        projs_df = fetch_df("SELECT project_id, project_name, grant_code, status FROM projects ORDER BY project_name")
        if not projs_df.empty:
            proj_labels   = projs_df["project_name"].tolist()
            sel_proj_name = st.selectbox("Select project", proj_labels, key="sel_proj_edit")
            sel_proj_row  = projs_df[projs_df["project_name"] == sel_proj_name].iloc[0]
            sel_proj_id   = int(sel_proj_row["project_id"])

            with st.form("edit_project"):
                c1, c2, c3 = st.columns(3)
                e_pname  = c1.text_input("Project Name *", value=sel_proj_row["project_name"])
                e_grant  = c2.text_input("Grant Code",     value=sel_proj_row["grant_code"] or "")
                cur_status_idx = PROJECT_STATUSES.index(sel_proj_row["status"]) \
                                 if sel_proj_row["status"] in PROJECT_STATUSES else 0
                e_status = c3.selectbox("Status", PROJECT_STATUSES, index=cur_status_idx)
                if st.form_submit_button("Save Changes"):
                    if e_pname.strip():
                        conn = get_connection()
                        try:
                            conn.execute("UPDATE projects SET project_name=?, grant_code=?, status=? WHERE project_id=?",
                                         (e_pname.strip(), e_grant.strip() or None, e_status, sel_proj_id))
                            conn.commit()
                            st.success("Project updated.")
                            st.rerun()
                        except sqlite3.Error as e:
                            st.error(f"Database error: {e}")
                        finally:
                            conn.close()
                    else:
                        st.error("Project Name is required.")

            confirm_proj = st.checkbox(f"Confirm deletion of **{sel_proj_name}**", key="del_proj_chk")
            if st.button("Delete Project", type="primary", disabled=not confirm_proj, key="del_proj_btn"):
                conn = get_connection()
                try:
                    conn.execute("DELETE FROM projects WHERE project_id=?", (sel_proj_id,))
                    conn.commit()
                    st.success(f"Project '{sel_proj_name}' deleted.")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("Cannot delete: items are still linked to this project.")
                finally:
                    conn.close()


# ── Login page ───────────────────────────────────────────────────────────────

def page_login() -> None:
    st.title("Lab Inventory — Login")
    st.markdown("Please sign in to continue.")

    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign In", type="primary")

    if submitted:
        if not username.strip() or not password:
            st.error("Username and password are required.")
            return
        row = _get_account(username.strip())
        if row and _verify_password(password, row["salt"], row["password_hash"]):
            st.session_state["authenticated"] = True
            st.session_state["auth_username"] = row["username"]
            st.session_state["auth_role"] = row["role"]
            st.rerun()
        else:
            st.error("Invalid username or password.")


def page_manage_accounts() -> None:
    st.title("Manage Login Accounts")

    conn = get_connection()
    accounts = pd.read_sql_query(
        "SELECT account_id AS ID, username AS Username, role AS Role FROM login_accounts ORDER BY username",
        conn,
    )
    conn.close()

    st.dataframe(accounts, use_container_width=True, hide_index=True)
    st.divider()

    # ── Add account ────────────────────────────────────────────────────────
    st.subheader("Add Account")
    with st.form("add_account"):
        new_user = st.text_input("Username *")
        new_pass = st.text_input("Password *", type="password")
        new_pass2 = st.text_input("Confirm Password *", type="password")
        new_role = st.selectbox("Role", ["viewer", "admin"])
        if st.form_submit_button("Create Account"):
            if not new_user.strip() or not new_pass:
                st.error("Username and password are required.")
            elif new_pass != new_pass2:
                st.error("Passwords do not match.")
            else:
                salt = secrets.token_hex(16)
                pw_hash = _hash_password(new_pass, salt)
                conn = get_connection()
                try:
                    conn.execute(
                        "INSERT INTO login_accounts (username, password_hash, salt, role) VALUES (?,?,?,?)",
                        (new_user.strip(), pw_hash, salt, new_role),
                    )
                    conn.commit()
                    st.success(f"Account '{new_user.strip()}' created.")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("A user with that username already exists.")
                finally:
                    conn.close()

    st.divider()

    # ── Change password ────────────────────────────────────────────────────
    st.subheader("Change Password")
    with st.form("change_password"):
        target_user = st.text_input("Username to update *")
        chg_pass = st.text_input("New Password *", type="password")
        chg_pass2 = st.text_input("Confirm New Password *", type="password")
        if st.form_submit_button("Update Password"):
            if not target_user.strip() or not chg_pass:
                st.error("Username and password are required.")
            elif chg_pass != chg_pass2:
                st.error("Passwords do not match.")
            else:
                salt = secrets.token_hex(16)
                pw_hash = _hash_password(chg_pass, salt)
                conn = get_connection()
                cur = conn.execute(
                    "UPDATE login_accounts SET password_hash=?, salt=? WHERE username=?",
                    (pw_hash, salt, target_user.strip()),
                )
                conn.commit()
                conn.close()
                if cur.rowcount:
                    st.success(f"Password updated for '{target_user.strip()}'.")
                else:
                    st.error("Username not found.")

    st.divider()

    # ── Delete account ─────────────────────────────────────────────────────
    st.subheader("Delete Account")
    if not accounts.empty:
        del_user = st.selectbox("Select account to delete", accounts["Username"].tolist(), key="del_acct")
        confirm_del = st.checkbox(f"I confirm I want to delete **{del_user}**", key="del_acct_chk")
        if st.button("Delete Account", type="primary", disabled=not confirm_del):
            current = st.session_state.get("auth_username", "")
            if del_user == current:
                st.error("You cannot delete your own account.")
            else:
                conn = get_connection()
                conn.execute("DELETE FROM login_accounts WHERE username=?", (del_user,))
                conn.commit()
                conn.close()
                st.success(f"Account '{del_user}' deleted.")
                st.rerun()


# ── App entry point ───────────────────────────────────────────────────────────

def main() -> None:
    st.set_page_config(
        page_title="Lab Inventory",
        page_icon="🔬",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    initialize_db()

    # ── Authentication gate ───────────────────────────────────────────────
    if not st.session_state.get("authenticated"):
        page_login()
        return

    role = st.session_state.get("auth_role", "viewer")
    username = st.session_state.get("auth_username", "")

    # Read-only pages available to all roles
    viewer_pages = {
        "Dashboard":         page_dashboard,
        "All Items":         page_all_items,
    }

    # Write pages available to admins only
    admin_pages = {
        "Add New Item":      page_add_item,
        "Edit Item":         page_edit_item,
        "Check-Out / In":    page_checkout,
        "Import Excel":      page_import_excel,
        "Bulk Delete":       page_bulk_delete,
        "Manage Lookups":    page_manage,
        "Manage Accounts":   page_manage_accounts,
    }

    pages = viewer_pages if role == "viewer" else {**viewer_pages, **admin_pages}

    st.sidebar.title("Lab Inventory")
    st.sidebar.caption("Local SQLite · Streamlit UI test")
    st.sidebar.divider()

    selection = st.sidebar.radio("Navigate", list(pages.keys()), label_visibility="collapsed")
    st.sidebar.divider()
    st.sidebar.caption(f"Signed in as **{username}** ({role})")
    st.sidebar.caption(f"DB: `{os.path.basename(DB_PATH)}`")
    if st.sidebar.button("Logout"):
        st.session_state.clear()
        st.rerun()

    pages[selection]()


if __name__ == "__main__":
    main()
