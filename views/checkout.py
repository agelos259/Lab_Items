import pandas as pd
import streamlit as st
import psycopg2

from config import CONDITIONS
from db import get_connection
from queries import fetch_df, fetch_lookup


def page_checkout() -> None:
    st.title("Check-Out / Check-In")

    locs  = fetch_lookup("locations", "location_id", "location_name")
    users = fetch_lookup("users",     "user_id",     "name")

    df = fetch_df(
        """
        SELECT
            i.internal_id                                 AS "ID",
            i.item_name                                   AS "Item Name",
            COALESCE(cat.category_name, i.category, '—') AS "Category",
            l.location_name                               AS "Location",
            COALESCE(u.name, '— Unassigned —')            AS "Assigned To",
            i.condition                                   AS "Condition",
            i.user_id                                     AS _user_id
        FROM items i
        JOIN locations l         ON i.location_id  = l.location_id
        LEFT JOIN categories cat ON i.category_id  = cat.category_id
        LEFT JOIN users u        ON i.user_id      = u.user_id
        ORDER BY l.location_name,
                 CAST(SUBSTR(i.internal_id, 5) AS INTEGER)
        """
    )

    if df.empty:
        st.info("No items in database.")
        return

    tab_out, tab_in = st.tabs(["Check-Out", "Check-In / Return"])

    # ── Check-Out ─────────────────────────────────────────────────────────────
    with tab_out:
        available = df[df["Condition"] != "In Use"].drop(columns=["_user_id"]).reset_index(drop=True)

        if available.empty:
            st.info("No available items to check out.")
        else:
            available.insert(0, "Select", False)

            c1, c2 = st.columns([3, 2])
            search_out = c1.text_input("Search", "", key="search_out")
            loc_filter_out = c2.selectbox("Filter by location", ["All"] + sorted(df["Location"].unique().tolist()), key="loc_out")

            filtered_out = available.copy()
            if search_out:
                mask = (
                    filtered_out["Item Name"].str.contains(search_out, case=False, na=False) |
                    filtered_out["ID"].str.contains(search_out, case=False, na=False)
                )
                filtered_out = filtered_out[mask]
            if loc_filter_out != "All":
                filtered_out = filtered_out[filtered_out["Location"] == loc_filter_out]

            edited_out = st.data_editor(
                filtered_out,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Select": st.column_config.CheckboxColumn("Select", default=False),
                    "ID":         st.column_config.TextColumn("ID",         disabled=True),
                    "Item Name":  st.column_config.TextColumn("Item Name",  disabled=True),
                    "Category":   st.column_config.TextColumn("Category",   disabled=True),
                    "Location":   st.column_config.TextColumn("Location",   disabled=True),
                    "Assigned To":st.column_config.TextColumn("Assigned To",disabled=True),
                    "Condition":  st.column_config.TextColumn("Condition",  disabled=True),
                },
                key="editor_out",
            )

            chosen_ids = edited_out[edited_out["Select"] == True]["ID"].tolist()
            st.caption(f"{len(chosen_ids)} item(s) selected")

            with st.form("checkout_form"):
                user_label = st.selectbox("Assign To *", ["— Select user —"] + list(users.values()))
                user_id    = None if user_label == "— Select user —" \
                             else [k for k, v in users.items() if v == user_label][0]
                offsite_default = next(
                    (i for i, n in enumerate(locs.values()) if "Off-Site" in n), 0
                )
                loc_label = st.selectbox("New Location *", list(locs.values()), index=offsite_default)
                loc_id    = [k for k, v in locs.items() if v == loc_label][0]
                co_submitted = st.form_submit_button("Confirm Check-Out", type="primary")

            if co_submitted:
                if not chosen_ids:
                    st.error("Please select at least one item.")
                elif not user_id:
                    st.error("Please select a user.")
                else:
                    conn = get_connection()
                    saved, failed = [], []
                    try:
                        for iid in chosen_ids:
                            try:
                                conn.execute(
                                    "UPDATE items SET condition='In Use', user_id=?, location_id=? "
                                    "WHERE internal_id=?",
                                    (user_id, loc_id, iid),
                                )
                                saved.append(iid)
                            except psycopg2.Error:
                                conn.rollback()
                                failed.append(iid)
                        conn.commit()
                    except psycopg2.Error as e:
                        conn.rollback()
                        st.error(f"Database error: {e}")
                    finally:
                        conn.close()
                    if saved:
                        st.success(
                            f"**{len(saved)} item(s)** checked out to **{user_label}** "
                            f"— Location: {loc_label}\n\n"
                            + ", ".join(f"`{i}`" for i in saved)
                        )
                        st.rerun()
                    if failed:
                        st.error(f"Failed for: {', '.join(failed)}")

    # ── Check-In ──────────────────────────────────────────────────────────────
    with tab_in:
        checked_out = df[df["Condition"] == "In Use"].drop(columns=["_user_id"]).reset_index(drop=True)

        if checked_out.empty:
            st.info("No items currently checked out.")
        else:
            checked_out.insert(0, "Select", False)

            c1, c2 = st.columns([3, 2])
            search_in = c1.text_input("Search", "", key="search_in")
            user_filter_in = c2.selectbox("Filter by assignee", ["All"] + list(users.values()), key="user_in")

            filtered_in = checked_out.copy()
            if search_in:
                mask = (
                    filtered_in["Item Name"].str.contains(search_in, case=False, na=False) |
                    filtered_in["ID"].str.contains(search_in, case=False, na=False)
                )
                filtered_in = filtered_in[mask]
            if user_filter_in != "All":
                filtered_in = filtered_in[filtered_in["Assigned To"] == user_filter_in]

            edited_in = st.data_editor(
                filtered_in,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Select": st.column_config.CheckboxColumn("Select", default=False),
                    "ID":         st.column_config.TextColumn("ID",         disabled=True),
                    "Item Name":  st.column_config.TextColumn("Item Name",  disabled=True),
                    "Category":   st.column_config.TextColumn("Category",   disabled=True),
                    "Location":   st.column_config.TextColumn("Location",   disabled=True),
                    "Assigned To":st.column_config.TextColumn("Assigned To",disabled=True),
                    "Condition":  st.column_config.TextColumn("Condition",  disabled=True),
                },
                key="editor_in",
            )

            chosen_ids_ci = edited_in[edited_in["Select"] == True]["ID"].tolist()
            st.caption(f"{len(chosen_ids_ci)} item(s) selected")

            with st.form("checkin_form"):
                default_ci   = next(
                    (i for i, n in enumerate(locs.values()) if "Off-Site" not in n), 0
                )
                loc_label_ci = st.selectbox("Return To Location *", list(locs.values()), index=default_ci)
                loc_id_ci    = [k for k, v in locs.items() if v == loc_label_ci][0]
                new_condition = st.selectbox("Set Condition", CONDITIONS)
                ci_submitted  = st.form_submit_button("Confirm Check-In", type="primary")

            if ci_submitted:
                if not chosen_ids_ci:
                    st.error("Please select at least one item.")
                else:
                    conn = get_connection()
                    saved_ci, failed_ci = [], []
                    try:
                        for iid in chosen_ids_ci:
                            try:
                                conn.execute(
                                    "UPDATE items SET condition=?, user_id=NULL, location_id=? "
                                    "WHERE internal_id=?",
                                    (new_condition, loc_id_ci, iid),
                                )
                                saved_ci.append(iid)
                            except psycopg2.Error:
                                conn.rollback()
                                failed_ci.append(iid)
                        conn.commit()
                    except psycopg2.Error as e:
                        conn.rollback()
                        st.error(f"Database error: {e}")
                    finally:
                        conn.close()
                    if saved_ci:
                        st.success(
                            f"**{len(saved_ci)} item(s)** returned "
                            f"— Location: {loc_label_ci} | Condition: {new_condition}\n\n"
                            + ", ".join(f"`{i}`" for i in saved_ci)
                        )
                        st.rerun()
                    if failed_ci:
                        st.error(f"Failed for: {', '.join(failed_ci)}")
