import io

import pandas as pd
import streamlit as st
import psycopg2

from config import CATEGORIES, CONDITIONS, EXCEL_COL_MAP
from db import get_connection
from queries import fetch_lookup, get_next_lab_id, get_or_create_location, get_or_create_category


def page_import_excel() -> None:
    st.title("Import from Excel")

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

    st.subheader("Step 2 — Upload Excel File")
    st.caption(
        "Expected columns (Greek headers): "
        "**A/A · ΕΙΔΟΣ · ΜΟΝΤΕΛΟ · ΤΕΜΑΧΙΑ · S/N · "
        "ΤΙΜΗ ΤΕΜΑΧΙΟΥ ΧΩΡΙΣ ΦΠΑ · ΤΙΜΗ ΤΕΜΑΧΙΟΥ ΜΕ ΦΠΑ · "
        "ΤΙΜΗ ΠΟΣΟΤΗΤΑΣ ΧΩΡΙΣ ΦΠΑ · ΤΙΜΗ ΠΟΣΟΤΗΤΑΣ ΜΕ ΦΠΑ · "
        "ΠΑΡΑΛΑΒΗ (ΝΑΙ/ ΟΧΙ) · ΤΟΠΟΘΕΣΙΑ**"
    )
    with st.expander("Advanced parse options", expanded=False):
        header_row = st.number_input("Header row (0 = first row)", min_value=0, max_value=10, value=0, step=1)
        sheet_name = st.text_input("Sheet name (leave blank for first sheet)", value="")

    uploaded = st.file_uploader("Choose an .xlsx or .xls file", type=["xlsx", "xls"])
    if not uploaded:
        return

    try:
        sheet = sheet_name.strip() if sheet_name.strip() else 0
        raw   = pd.read_excel(io.BytesIO(uploaded.read()), sheet_name=sheet,
                               header=int(header_row), dtype=str)
    except Exception as e:
        st.error(f"Could not read file: {e}")
        return

    raw.columns = [str(c).strip() for c in raw.columns]
    rename_map  = {orig: mapped for orig, mapped in EXCEL_COL_MAP.items() if orig in raw.columns}
    df          = raw.rename(columns=rename_map)

    if "item_name" not in df.columns:
        st.error(f"Column ΜΟΝΤΕΛΟ not found. Detected: {', '.join(raw.columns.tolist())}")
        return

    df = df[df["item_name"].notna() & (df["item_name"].astype(str).str.strip() != "")]
    df = df[df["item_name"].astype(str).str.strip() != "nan"]
    if df.empty:
        st.warning("No data rows found after filtering empty product names.")
        return

    def _parse_qty(val):
        try:
            return max(int(float(str(val).strip())), 1)
        except (ValueError, TypeError):
            return 1

    total_instances = sum(_parse_qty(r.get("quantity", 1)) for _, r in df.iterrows())
    st.success(f"Parsed **{len(df)} rows** → will create **{total_instances} individual items**.")
    st.divider()

    st.subheader("Step 3 — Set Defaults")
    col_b, col_c = st.columns(2)
    default_cat  = col_b.selectbox("Fallback Category", CATEGORIES)
    default_cond = col_c.selectbox("Default Condition *", CONDITIONS, index=0)
    st.divider()

    st.subheader("Step 4 — Preview")
    preview_cols = [c for c in [
        "excel_category", "item_name", "quantity", "manufacturer_sn",
        "received", "location_name",
        "unit_price_ex_vat", "unit_price_inc_vat",
        "total_price_ex_vat", "total_price_inc_vat",
    ] if c in df.columns]
    st.dataframe(
        df[preview_cols].rename(columns={
            "excel_category": "Category (ΕΙΔΟΣ)", "item_name": "Product Name (ΜΟΝΤΕΛΟ)"
        }).head(20),
        use_container_width=True, hide_index=True,
    )
    if len(df) > 20:
        st.caption(f"Showing 20 of {len(df)} rows.")
    st.divider()

    st.subheader("Step 5 — Import")
    st.markdown(f"Ready to create **{total_instances} items** into project **{proj_label}**.")

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
                cat_raw  = str(r.get("excel_category", "")).strip()
                category = cat_raw if (cat_raw and cat_raw != "nan") else default_cat
                cat_id   = get_or_create_category(conn, category)

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
                        (new_id, name, category, cat_id, sn, 1, default_cond, received,
                         to_float(r.get("unit_price_ex_vat")),
                         to_float(r.get("unit_price_inc_vat")),
                         to_float(r.get("total_price_ex_vat")),
                         to_float(r.get("total_price_inc_vat")),
                         proj_id, loc_id),
                    )
                    inserted += 1

            conn.commit()
            st.success(f"Import complete: **{inserted} items created**, {skipped} rows skipped.")
            created = list(set(new_locs))
            if created:
                st.info(f"New locations auto-created: {', '.join(created)}")
        except psycopg2.Error as e:
            conn.rollback()
            st.error(f"Database error (rolled back): {e}")
        finally:
            conn.close()
