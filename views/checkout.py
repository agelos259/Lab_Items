import streamlit as st
import psycopg2

from config import CONDITIONS
from db import get_connection
from queries import fetch_df, fetch_lookup


def page_checkout() -> None:
    st.title("Check-Out / Check-In")

    all_items = fetch_df(
        "SELECT internal_id, item_name, condition, user_id FROM items "
        "ORDER BY CAST(SUBSTR(internal_id, 5) AS INTEGER)"
    )
    if all_items.empty:
        st.info("No items in database.")
        return

    locs  = fetch_lookup("locations", "location_id", "location_name")
    users = fetch_lookup("users",     "user_id",     "name")

    tab_out, tab_in = st.tabs(["Check-Out", "Check-In / Return"])

    # ── Check-Out ─────────────────────────────────────────────────────────────
    with tab_out:
        available = all_items[all_items["condition"] != "In Use"]
        if available.empty:
            st.info("No available items to check out.")
        else:
            id_labels = [
                f"{r['internal_id']} — {r['item_name']}"
                for _, r in available.iterrows()
            ]
            chosen_labels = st.multiselect(
                "Select item(s) to check out",
                options=id_labels,
                placeholder="Search or select items…",
            )
            chosen_ids = [lbl.split(" — ")[0] for lbl in chosen_labels]

            if chosen_ids:
                st.caption(f"{len(chosen_ids)} item(s) selected")

            with st.form("checkout_form"):
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
                    if failed:
                        st.error(f"Failed for: {', '.join(failed)}")

    # ── Check-In ──────────────────────────────────────────────────────────────
    with tab_in:
        checked_out = all_items[all_items["condition"] == "In Use"]
        if checked_out.empty:
            st.info("No items currently checked out.")
        else:
            id_labels_ci = [
                f"{r['internal_id']} — {r['item_name']} "
                f"(assigned to: {users.get(r['user_id'], '—') if r['user_id'] else '—'})"
                for _, r in checked_out.iterrows()
            ]
            chosen_labels_ci = st.multiselect(
                "Select item(s) to return",
                options=id_labels_ci,
                placeholder="Search or select items…",
            )
            chosen_ids_ci = [lbl.split(" — ")[0] for lbl in chosen_labels_ci]

            if chosen_ids_ci:
                st.caption(f"{len(chosen_ids_ci)} item(s) selected")

            with st.form("checkin_form"):
                default_ci    = next(
                    (i for i, n in enumerate(locs.values()) if "Off-Site" not in n), 0
                )
                loc_label_ci  = st.selectbox("Return To Location *", list(locs.values()), index=default_ci)
                loc_id_ci     = [k for k, v in locs.items() if v == loc_label_ci][0]
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
                    if failed_ci:
                        st.error(f"Failed for: {', '.join(failed_ci)}")
