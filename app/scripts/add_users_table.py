"""Add users table for Google OAuth authentication."""

import sys

sys.path.append(".")


from app.db.models import Base
from app.db.session import engine


def add_users_table():
    """Add users table to the database."""
    print("Adding users table for authentication...")

    # Create the new table
    Base.metadata.create_all(bind=engine)

    print("Users table added successfully!")
    print("Table created:")
    print("- users: User accounts authenticated via Google OAuth")
    print("  Fields: id, email, name, picture, google_id, refresh_token, is_active, created_at, last_login_at")
    print("  Indexes: email, google_id, last_login_at")


if __name__ == "__main__":
    add_users_table()

