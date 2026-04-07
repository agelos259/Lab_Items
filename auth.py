"""
Authentication helpers: password hashing, account lookup, default admin seeding.
"""

import hashlib
import secrets

import psycopg2.errors

from db import get_connection


def hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt.encode(), 260_000
    ).hex()


def verify_password(password: str, salt: str, stored_hash: str) -> bool:
    return secrets.compare_digest(hash_password(password, salt), stored_hash)


def get_account(username: str):
    """Return the login_accounts row for username, or None."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM login_accounts WHERE username = ?", (username,)
    ).fetchone()
    conn.close()
    return row


def seed_admin_account() -> None:
    """Insert a default admin/admin account if no accounts exist yet."""
    conn = get_connection()
    if conn.scalar("SELECT COUNT(*) FROM login_accounts") == 0:
        salt    = secrets.token_hex(16)
        pw_hash = hash_password("admin", salt)
        conn.execute(
            "INSERT INTO login_accounts (username, password_hash, salt, role) "
            "VALUES (?, ?, ?, ?)",
            ("admin", pw_hash, salt, "admin"),
        )
        conn.commit()
    conn.close()
