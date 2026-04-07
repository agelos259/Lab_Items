import secrets

import streamlit as st
import psycopg2.errors

from auth import hash_password
from db import get_connection
from queries import fetch_df


def page_manage_accounts() -> None:
    st.title("Manage Login Accounts")

    accounts = fetch_df(
        "SELECT account_id AS ID, username AS Username, role AS Role "
        "FROM login_accounts ORDER BY username"
    )
    st.dataframe(accounts, use_container_width=True, hide_index=True)
    st.divider()

    # ── Add account ───────────────────────────────────────────────────────
    st.subheader("Add Account")
    with st.form("add_account"):
        new_user  = st.text_input("Username *")
        new_pass  = st.text_input("Password *", type="password")
        new_pass2 = st.text_input("Confirm Password *", type="password")
        new_role  = st.selectbox("Role", ["viewer", "admin"])
        if st.form_submit_button("Create Account"):
            if not new_user.strip() or not new_pass:
                st.error("Username and password are required.")
            elif new_pass != new_pass2:
                st.error("Passwords do not match.")
            else:
                salt    = secrets.token_hex(16)
                pw_hash = hash_password(new_pass, salt)
                conn    = get_connection()
                try:
                    conn.execute(
                        "INSERT INTO login_accounts (username, password_hash, salt, role) "
                        "VALUES (?,?,?,?)",
                        (new_user.strip(), pw_hash, salt, new_role),
                    )
                    conn.commit()
                    st.success(f"Account '{new_user.strip()}' created.")
                    st.rerun()
                except psycopg2.errors.UniqueViolation:
                    conn.rollback()
                    st.error("A user with that username already exists.")
                finally:
                    conn.close()
    st.divider()

    # ── Change password ───────────────────────────────────────────────────
    st.subheader("Change Password")
    with st.form("change_password"):
        target_user = st.text_input("Username to update *")
        chg_pass    = st.text_input("New Password *", type="password")
        chg_pass2   = st.text_input("Confirm New Password *", type="password")
        if st.form_submit_button("Update Password"):
            if not target_user.strip() or not chg_pass:
                st.error("Username and password are required.")
            elif chg_pass != chg_pass2:
                st.error("Passwords do not match.")
            else:
                salt    = secrets.token_hex(16)
                pw_hash = hash_password(chg_pass, salt)
                conn    = get_connection()
                cur     = conn.execute(
                    "UPDATE login_accounts SET password_hash=?, salt=? WHERE username=?",
                    (pw_hash, salt, target_user.strip()),
                )
                conn.commit()
                conn.close()
                if cur.rowcount:
                    st.success(f"Password updated for '{target_user.strip()}'.")
                else:
                    st.error("Username not found.")
    st.divider()

    # ── Delete account ────────────────────────────────────────────────────
    st.subheader("Delete Account")
    if not accounts.empty:
        del_user    = st.selectbox("Select account to delete", accounts["Username"].tolist(), key="del_acct")
        confirm_del = st.checkbox(f"I confirm I want to delete **{del_user}**", key="del_acct_chk")
        if st.button("Delete Account", type="primary", disabled=not confirm_del):
            if del_user == st.session_state.get("auth_username", ""):
                st.error("You cannot delete your own account.")
            else:
                conn = get_connection()
                conn.execute("DELETE FROM login_accounts WHERE username=?", (del_user,))
                conn.commit()
                conn.close()
                st.success(f"Account '{del_user}' deleted.")
                st.rerun()
