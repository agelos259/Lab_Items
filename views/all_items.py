import pandas as pd
import streamlit as st
import psycopg2

from config import CONDITIONS
from db import get_connection
from queries import fetch_df, fetch_lookup, ITEMS_FULL_QUERY


def page_all_items() -> None:
    st.title("All Items")

    projs    = fetch_lookup("projects",   "project_id",  "project_name")
    cats_df  = fetch_df("SELECT category_name FROM categories ORDER BY category_name")
    cat_list = cats_df["category_name"].tolist() if not cats_df.empty else []
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
        query += " AND (i.item_name ILIKE ? OR i.internal_id ILIKE ? OR i.model ILIKE ?)"
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
    query += " ORDER BY CAST(SUBSTR(i.internal_id, 5) AS INTEGER)"

    df = fetch_df(query, tuple(params))
    df = df.drop(columns=["Model", "Received", "Return Date"], errors="ignore")

    for price_col in ("Unit (ex VAT)", "Unit (inc VAT)", "Total (ex VAT)", "Total (inc VAT)"):
        if price_col in df.columns:
            df[price_col] = pd.to_numeric(df[price_col].replace("—", None), errors="coerce")

    group_by_name = st.toggle("Group by name", value=False)

    if group_by_name:
        def _join_unique(s):
            vals = sorted({v for v in s if v and v != "—"})
            return ", ".join(vals) if vals else "—"

        grouped = (
            df.groupby("Item Name", sort=False)
            .agg(
                Category   = ("Category",        "first"),
                Count      = ("Item Name",        "count"),
                Locations  = ("Location",         _join_unique),
                Projects   = ("Project",          _join_unique),
                Conditions = ("Condition",        _join_unique),
                **({
                    "Unit (ex VAT)":  ("Unit (ex VAT)",  "mean"),
                    "Unit (inc VAT)": ("Unit (inc VAT)", "mean"),
                } if "Unit (ex VAT)" in df.columns else {}),
            )
            .reset_index()
        )
        st.caption(f"{len(df)} item(s) grouped into **{len(grouped)} unique name(s)**.")
        st.dataframe(grouped, use_container_width=True, hide_index=True)
        return

    st.caption(
        f"{len(df)} item(s) — "
        "edit **Assigned To**, **Location**, **Unit (ex VAT)** or **Unit (inc VAT)** directly in the table."
    )

    user_options = ["— Unassigned —"] + list(users.values())
    loc_options  = list(locs.values())
    EDITABLE     = {"Assigned To", "Location", "Unit (ex VAT)", "Unit (inc VAT)"}
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

    changed = df.compare(edited, keep_shape=False, keep_equal=False)
    if not changed.empty:
        conn  = get_connection()
        saved = 0
        try:
            for idx in changed.index.tolist():
                row_new  = edited.iloc[idx]
                item_id  = row_new["ID"]
                new_user = row_new["Assigned To"]
                new_loc  = row_new["Location"]
                user_id  = None if new_user == "— Unassigned —" \
                           else [k for k, v in users.items() if v == new_user][0]
                loc_id   = [k for k, v in locs.items() if v == new_loc][0]
                condition = "Available" if user_id is None else "In Use"
                unit_ex   = row_new.get("Unit (ex VAT)")
                unit_inc  = row_new.get("Unit (inc VAT)")
                unit_ex   = float(unit_ex)  if pd.notna(unit_ex)  else None
                unit_inc  = float(unit_inc) if pd.notna(unit_inc) else None
                conn.execute(
                    "UPDATE items SET user_id=?, location_id=?, condition=?, "
                    "unit_price_ex_vat=?, unit_price_inc_vat=? WHERE internal_id=?",
                    (user_id, loc_id, condition, unit_ex, unit_inc, item_id),
                )
                saved += 1
            conn.commit()
        except psycopg2.Error as e:
            conn.rollback()
            st.error(f"Database error: {e}")
        finally:
            conn.close()
        if saved:
            st.success(f"Saved changes to {saved} item(s).")
            st.rerun()
