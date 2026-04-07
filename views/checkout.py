import streamlit as st
import psycopg2

from config import CONDITIONS
from db import get_connection
from queries import fetch_df, fetch_lookup


def page_checkout() -> None:
    st.title("Check-Out / Check-In Item")

    all_items = fetch_df(
        "SELECT internal_id, item_name, condition FROM items "
        "ORDER BY CAST(SUBSTR(internal_id, 5) AS INTEGER)"
    )
    if all_items.empty:
        st.info("No items in database.")
        return

    id_labels = [f"{r['internal_id']} — {r['item_name']} [{r['condition']}]"
                 for _, r in all_items.iterrows()]
    chosen_id = st.selectbox("Select Item", id_labels).split(" — ")[0]

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
                except psycopg2.Error as e:
                    conn.rollback()
                    st.error(f"Database error: {e}")
                finally:
                    conn.close()

    with tab_in:
        with st.form("checkin_form"):
            st.subheader(f"Return / Check In: {chosen_id}")
            default_ci   = next(
                (i for i, n in enumerate(locs.values()) if "Off-Site" not in n), 0
            )
            loc_label_ci  = st.selectbox("Return To Location *", list(locs.values()), index=default_ci)
            loc_id_ci     = [k for k, v in locs.items() if v == loc_label_ci][0]
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
            except psycopg2.Error as e:
                conn.rollback()
                st.error(f"Database error: {e}")
            finally:
                conn.close()
