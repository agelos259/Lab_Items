import hashlib
import io

import pandas as pd
import streamlit as st
import psycopg2

from config import CONDITIONS, EXCEL_COL_MAP
from db import get_connection
from queries import fetch_lookup, get_next_lab_id, get_or_create_location, get_or_create_category


def _parse_qty(val):
    try:
        return max(int(float(str(val).strip())), 1)
    except (ValueError, TypeError):
        return 1


def _to_float(val):
    try:
        return float(str(val).replace(",", ".").strip())
    except (ValueError, TypeError):
        return None


def _sheet_hash(file_bytes: bytes, sheet_name: str) -> str:
    """Hash is per file+sheet so the same file can be re-uploaded for a different sheet."""
    return hashlib.sha256(file_bytes + b"::" + sheet_name.encode()).hexdigest()


# Column-index fallback for price columns (F=5, G=6, H=7, I=8, zero-indexed)
_PRICE_COL_POSITIONS = {
    5: "unit_price_ex_vat",
    6: "unit_price_inc_vat",
    7: "total_price_ex_vat",
    8: "total_price_inc_vat",
}


def _load_sheet(file_bytes: bytes, sheet_name: str, header_row: int):
    raw = pd.read_excel(io.BytesIO(file_bytes), sheet_name=sheet_name,
                        header=header_row, dtype=str)
    raw.columns = [str(c).strip() for c in raw.columns]
    rename_map = {orig: mapped for orig, mapped in EXCEL_COL_MAP.items() if orig in raw.columns}
    df = raw.rename(columns=rename_map)
    if "item_name" not in df.columns:
        return None, list(raw.columns)

    # Fall back to column position for price columns not matched by header name
    for pos, field in _PRICE_COL_POSITIONS.items():
        if field not in df.columns and pos < len(df.columns):
            df = df.rename(columns={df.columns[pos]: field})

    df = df[df["item_name"].notna() & (df["item_name"].astype(str).str.strip() != "")]
    df = df[df["item_name"].astype(str).str.strip() != "nan"]
    return df, None


def page_import_excel() -> None:
    st.title("Import from Excel")

    projs = fetch_lookup("projects", "project_id", "project_name")
    if not projs:
        st.error("No projects found. Please add a project first via Manage Lookups.")
        return

    st.caption(
        "Expected columns (Greek headers): "
        "**A/A · ΕΙΔΟΣ · ΜΟΝΤΕΛΟ · ΤΕΜΑΧΙΑ · S/N · "
        "ΤΙΜΗ ΤΕΜΑΧΙΟΥ ΧΩΡΙΣ ΦΠΑ · ΤΙΜΗ ΤΕΜΑΧΙΟΥ ΜΕ ΦΠΑ · "
        "ΤΙΜΗ ΠΟΣΟΤΗΤΑΣ ΧΩΡΙΣ ΦΠΑ · ΤΙΜΗ ΠΟΣΟΤΗΤΑΣ ΜΕ ΦΠΑ · "
        "ΠΑΡΑΛΑΒΗ (ΝΑΙ/ ΟΧΙ) · ΤΟΠΟΘΕΣΙΑ**"
    )

    uploaded = st.file_uploader("Choose an .xlsx or .xls file", type=["xlsx", "xls"])
    if not uploaded:
        return

    file_bytes = uploaded.read()

    try:
        xl = pd.ExcelFile(io.BytesIO(file_bytes))
        sheet_names = xl.sheet_names
    except Exception as e:
        st.error(f"Could not read file: {e}")
        return

    st.success(f"Found **{len(sheet_names)} sheet(s)**: {', '.join(sheet_names)}")
    st.divider()

    # Check which sheets were already imported
    conn_check = get_connection()
    import_status = {}
    for sheet in sheet_names:
        h = _sheet_hash(file_bytes, sheet)
        row = conn_check.execute(
            "SELECT imported_at, imported_by, row_count FROM import_log WHERE file_hash = ?",
            (h,)
        ).fetchone()
        import_status[sheet] = row  # None if not yet imported
    conn_check.close()

    proj_labels = list(projs.values())
    sheet_configs = {}

    for sheet in sheet_names:
        already = import_status[sheet]
        label = f"Sheet: **{sheet}**"
        if already:
            label += f"  ·  *already imported {already['imported_at'].strftime('%Y-%m-%d')} by {already['imported_by']}*"

        with st.expander(label, expanded=(already is None)):
            if already:
                st.warning(
                    f"Imported on **{already['imported_at'].strftime('%Y-%m-%d %H:%M')}** "
                    f"by **{already['imported_by']}** ({already['row_count']} items)."
                )
                include = st.checkbox("Import again anyway", key=f"inc_{sheet}", value=False)
            else:
                include = st.checkbox("Include this sheet", key=f"inc_{sheet}", value=True)

            if not include:
                sheet_configs[sheet] = {"include": False}
                continue

            col1, col2 = st.columns(2)
            proj_label = col1.selectbox("Project", proj_labels, key=f"proj_{sheet}")
            proj_id = [k for k, v in projs.items() if v == proj_label][0]
            header_row = col2.number_input(
                "Header row (0 = first row)", min_value=0, max_value=10,
                value=0, step=1, key=f"hdr_{sheet}"
            )

            try:
                df, bad_cols = _load_sheet(file_bytes, sheet, int(header_row))
            except Exception as e:
                st.error(f"Could not parse sheet: {e}")
                sheet_configs[sheet] = {"include": False}
                continue

            if df is None:
                st.error(f"Column ΜΟΝΤΕΛΟ not found. Detected: {', '.join(bad_cols)}")
                sheet_configs[sheet] = {"include": False}
                continue

            if df.empty:
                st.warning("No data rows found after filtering.")
                sheet_configs[sheet] = {"include": False}
                continue

            total = sum(_parse_qty(r.get("quantity", 1)) for _, r in df.iterrows())
            st.caption(f"{len(df)} rows → **{total} items** will be created")

            preview_cols = [c for c in [
                "excel_category", "item_name", "quantity", "manufacturer_sn",
                "received", "location_name",
            ] if c in df.columns]
            st.dataframe(
                df[preview_cols].rename(columns={
                    "excel_category": "Category", "item_name": "Product Name"
                }).head(10),
                use_container_width=True, hide_index=True,
            )
            if len(df) > 10:
                st.caption(f"Showing 10 of {len(df)} rows.")

            sheet_configs[sheet] = {
                "include": True, "proj_id": proj_id,
                "proj_label": proj_label, "df": df,
            }

    to_import = [s for s, cfg in sheet_configs.items() if cfg.get("include")]
    if not to_import:
        return

    st.divider()
    total_items = sum(
        sum(_parse_qty(r.get("quantity", 1)) for _, r in sheet_configs[s]["df"].iterrows())
        for s in to_import
    )
    st.markdown(
        f"Ready to import **{len(to_import)} sheet(s)** → **{total_items} items total**.\n\n"
        + "\n".join(
            f"- **{s}** → project *{sheet_configs[s]['proj_label']}*"
            for s in to_import
        )
    )

    if st.button("Import Selected Sheets", type="primary"):
        conn = get_connection()
        username = st.session_state.get("auth_username", "unknown")
        grand_inserted = 0
        grand_skipped = 0

        try:
            for sheet in to_import:
                cfg = sheet_configs[sheet]
                df = cfg["df"]
                proj_id = cfg["proj_id"]
                inserted = 0
                skipped = 0

                # Check location fallback once per sheet
                fallback_loc = conn.execute(
                    "SELECT location_id FROM locations LIMIT 1"
                ).fetchone()
                fallback_loc_id = fallback_loc["location_id"] if fallback_loc else None

                for _, r in df.iterrows():
                    name = str(r.get("item_name", "")).strip()
                    if not name or name == "nan":
                        skipped += 1
                        continue

                    cat_raw = str(r.get("excel_category", "")).strip()
                    if cat_raw and cat_raw != "nan":
                        cat_id = get_or_create_category(conn, cat_raw)
                        category = cat_raw
                    else:
                        cat_id = None
                        category = None

                    loc_raw = str(r.get("location_name", "")).strip()
                    if loc_raw and loc_raw != "nan":
                        loc_id = get_or_create_location(conn, loc_raw)
                    elif fallback_loc_id:
                        loc_id = fallback_loc_id
                    else:
                        skipped += 1
                        continue

                    sn = str(r.get("manufacturer_sn", "")).strip() or None
                    received = str(r.get("received", "")).strip() or None
                    qty = _parse_qty(r.get("quantity", 1))

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
                            (new_id, name, category, cat_id, sn, 1, CONDITIONS[0], received,
                             _to_float(r.get("unit_price_ex_vat")),
                             _to_float(r.get("unit_price_inc_vat")),
                             _to_float(r.get("total_price_ex_vat")),
                             _to_float(r.get("total_price_inc_vat")),
                             proj_id, loc_id),
                        )
                        inserted += 1

                conn.execute(
                    """INSERT INTO import_log (file_hash, file_name, imported_by, row_count)
                       VALUES (?,?,?,?)
                       ON CONFLICT (file_hash) DO UPDATE
                         SET file_name   = EXCLUDED.file_name,
                             imported_by = EXCLUDED.imported_by,
                             imported_at = NOW(),
                             row_count   = EXCLUDED.row_count""",
                    (_sheet_hash(file_bytes, sheet), f"{uploaded.name} [{sheet}]", username, inserted),
                )
                conn.commit()
                grand_inserted += inserted
                grand_skipped += skipped

        except psycopg2.Error as e:
            conn.rollback()
            st.error(f"Database error (rolled back): {e}")
        else:
            st.success(
                f"Import complete: **{grand_inserted} items created** across "
                f"{len(to_import)} sheet(s), {grand_skipped} rows skipped."
            )
        finally:
            conn.close()
