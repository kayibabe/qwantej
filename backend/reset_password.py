"""Local dev utility: reset a user's password without touching email/SMTP.

Usage (from the backend/ directory):
    python reset_password.py you@example.com

Prompts for the new password with hidden input (getpass) — the password never
appears on screen, in shell history, or in any log. Hashes with the app's own
bcrypt helper so the stored hash is identical to what /api/auth/register writes.
"""
import getpass
import sqlite3
import sys

from app.core.auth import hash_password


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python reset_password.py <email>")
        sys.exit(1)
    email = sys.argv[1].strip().lower()

    pw = getpass.getpass(f"New password for {email}: ")
    pw2 = getpass.getpass("Repeat: ")
    if pw != pw2:
        print("Passwords do not match — nothing changed.")
        sys.exit(1)
    if len(pw) < 8:
        print("Password must be at least 8 characters — nothing changed.")
        sys.exit(1)

    con = sqlite3.connect("qwantej.db")
    try:
        cur = con.execute(
            "UPDATE users SET hashed_password = ? WHERE lower(email) = ?",
            (hash_password(pw), email),
        )
        con.commit()
        if cur.rowcount == 1:
            print(f"Password updated for {email}.")
        else:
            print(f"No user found with email {email} — nothing changed.")
    finally:
        con.close()


if __name__ == "__main__":
    main()
