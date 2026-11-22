"""E1 - login, hashed passwords and role-based access (Ganesh).

Design reference: Sprint 1 section 4.18 / 4.20: login required; Admin manages
resources and views all schedules; Organizer manages only own events;
passwords stored hashed; every function checks the role.
"""
import hashlib
import hmac
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "e2-database"))
import database as db

PERMISSIONS = {
    "Admin": {"manage_resources", "view_schedule"},
    "Organizer": {"create_event", "cancel_own_event", "view_schedule"},
}


def hash_password(password):
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2 ** 14, r=8, p=1)
    return salt.hex() + "$" + digest.hex()


def verify_password(password, stored):
    try:
        salt_hex, digest_hex = stored.split("$")
        digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex),
                                n=2 ** 14, r=8, p=1)
    except ValueError:
        return False
    return hmac.compare_digest(digest.hex(), digest_hex)


def register(conn, name, email, password, role):
    if role not in PERMISSIONS:
        raise ValueError("Role must be Admin or Organizer")
    if len(password) < 6:
        raise ValueError("Password must be at least 6 characters")
    return db.add_user(conn, name, email, hash_password(password), role)


def login(conn, email, password):
    """Return the user dict (without hash) or None."""
    user = db.get_user_by_email(conn, email or "")
    if user and verify_password(password or "", user["password_hash"]):
        user.pop("password_hash")
        return user
    return None


def can(role, action):
    return action in PERMISSIONS.get(role, set())
