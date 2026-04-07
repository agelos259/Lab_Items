import streamlit as st
from auth import get_account, verify_password


def page_login() -> None:
    st.title("Lab Inventory — Login")
    st.markdown("Please sign in to continue.")

    with st.form("login_form"):
        username  = st.text_input("Username")
        password  = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign In", type="primary")

    if submitted:
        if not username.strip() or not password:
            st.error("Username and password are required.")
            return
        row = get_account(username.strip())
        if row and verify_password(password, row["salt"], row["password_hash"]):
            st.session_state["authenticated"]  = True
            st.session_state["auth_username"]  = row["username"]
            st.session_state["auth_role"]      = row["role"]
            st.rerun()
        else:
            st.error("Invalid username or password.")
