import streamlit as st
from db import get_connection
from queries import fetch_df, ITEMS_FULL_QUERY


def page_dashboard() -> None:
    st.title("Lab Inventory — Dashboard")

    conn       = get_connection()
    total      = conn.scalar("SELECT COUNT(*) FROM items")
    available  = conn.scalar("SELECT COUNT(*) FROM items WHERE condition = 'Available'")
    in_use     = conn.scalar("SELECT COUNT(*) FROM items WHERE condition = 'In Use'")
    needs_attn = conn.scalar(
        "SELECT COUNT(*) FROM items WHERE condition IN ('Broken','Needs Repair')"
    )
    offsite = conn.scalar(
        "SELECT COUNT(*) FROM items WHERE location_id = "
        "(SELECT location_id FROM locations WHERE location_name = 'Off-Site / Home')"
    )
    conn.close()

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total Items",     total      or 0)
    c2.metric("Available",       available  or 0)
    c3.metric("In Use",          in_use     or 0)
    c4.metric("Needs Attention", needs_attn or 0, delta_color="inverse")
    c5.metric("Off-Site",        offsite    or 0)

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
