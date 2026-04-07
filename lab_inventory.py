"""
Lab Inventory Management System
================================
Entry point — run with:  python -m streamlit run lab_inventory.py
"""

import streamlit as st

from style import apply_styles
from auth import seed_admin_account
from db import initialize_db
from views.login import page_login
from views.dashboard import page_dashboard
from views.all_items import page_all_items
from views.add_item import page_add_item
from views.edit_item import page_edit_item
from views.checkout import page_checkout
from views.import_excel import page_import_excel
from views.bulk_delete import page_bulk_delete
from views.manage import page_manage
from views.accounts import page_manage_accounts
from views.assignments import page_assignments


def main() -> None:
    st.set_page_config(
        page_title="Lab Inventory",
        page_icon="🔬",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    apply_styles()

    # Bootstrap DB once per session
    if not st.session_state.get("_db_ready"):
        initialize_db()
        seed_admin_account()
        st.session_state["_db_ready"] = True

    # ── Auth gate ─────────────────────────────────────────────────────────
    if not st.session_state.get("authenticated"):
        page_login()
        return

    role     = st.session_state.get("auth_role", "viewer")
    username = st.session_state.get("auth_username", "")

    viewer_pages = {
        "Dashboard":   page_dashboard,
        "All Items":   page_all_items,
        "Assignments": page_assignments,
    }
    admin_pages = {
        "Add New Item":    page_add_item,
        "Edit Item":       page_edit_item,
        "Check-Out / In":  page_checkout,
        "Import Excel":    page_import_excel,
        "Bulk Delete":     page_bulk_delete,
        "Manage Lookups":  page_manage,
        "Manage Accounts": page_manage_accounts,
    }
    pages = viewer_pages if role == "viewer" else {**viewer_pages, **admin_pages}

    # ── Sidebar ───────────────────────────────────────────────────────────
    st.sidebar.title("Lab Inventory")
    st.sidebar.caption("PostgreSQL · Streamlit UI")
    st.sidebar.divider()
    selection = st.sidebar.radio("Navigate", list(pages.keys()), label_visibility="collapsed")
    st.sidebar.divider()
    st.sidebar.caption(f"Signed in as **{username}** ({role})")
    if st.sidebar.button("Logout"):
        st.session_state.clear()
        st.rerun()

    pages[selection]()


if __name__ == "__main__":
    main()
