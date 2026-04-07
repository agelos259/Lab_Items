"""
Shared query helpers: fetch_df, fetch_lookup, get_next_lab_id, get_or_create_*.
"""

import pandas as pd
import psycopg2.extras

from db import DBConn, get_connection


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


def fetch_df(query: str, params: tuple = ()) -> pd.DataFrame:
    conn = get_connection()
    try:
        cur = conn.raw.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(query.replace("?", "%s"), params or None)
        rows = cur.fetchall()
        if not rows:
            cols = [d[0] for d in cur.description] if cur.description else []
            return pd.DataFrame(columns=cols)
        return pd.DataFrame([dict(r) for r in rows])
    except Exception:
        return pd.DataFrame()
    finally:
        conn.close()


def fetch_lookup(table: str, id_col: str, label_col: str) -> dict:
    """Return {id: label} dict for a lookup table."""
    df = fetch_df(f"SELECT {id_col}, {label_col} FROM {table} ORDER BY {label_col}")
    if df.empty:
        return {}
    return dict(zip(df[id_col], df[label_col]))


def get_next_lab_id(conn: DBConn) -> str:
    row = conn.execute(
        "SELECT internal_id FROM items "
        "ORDER BY CAST(SUBSTR(internal_id, 5) AS INTEGER) DESC LIMIT 1"
    ).fetchone()
    if not row:
        return "LAB-001"
    last_num = int(row["internal_id"].split("-")[1])
    return f"LAB-{last_num + 1:03d}"


def get_or_create_location(conn: DBConn, name: str) -> int:
    name = name.strip()
    row = conn.execute(
        """INSERT INTO locations (location_name) VALUES (?)
           ON CONFLICT (location_name) DO UPDATE SET location_name = EXCLUDED.location_name
           RETURNING location_id""",
        (name,)
    ).fetchone()
    return row["location_id"]


def get_or_create_category(conn: DBConn, name: str) -> int:
    name = name.strip()
    row = conn.execute(
        """INSERT INTO categories (category_name) VALUES (?)
           ON CONFLICT (category_name) DO UPDATE SET category_name = EXCLUDED.category_name
           RETURNING category_id""",
        (name,)
    ).fetchone()
    return row["category_id"]
