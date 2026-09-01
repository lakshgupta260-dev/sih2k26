"""Operational command line.

Exists to solve a bootstrap problem: self-registration only ever produces a
SITE_SUPERVISOR, and creating a user with a higher role requires an existing
administrator. Something outside the HTTP API has to create the first one.

Usage::

    python -m app.cli create-admin --email you@example.com --password '...'
    python -m app.cli create-admin --email you@example.com          # prompts
    python -m app.cli list-admins
"""
from __future__ import annotations

import argparse
import getpass
import sys

from pydantic import EmailStr, TypeAdapter, ValidationError

from app.core.constants import UserRole
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.user import User
from app.repositories.user import UserRepository
from app.schemas.user import PASSWORD_MIN


_EMAIL_ADAPTER = TypeAdapter(EmailStr)


def _validate_email(raw: str) -> str:
    """Apply exactly the validation the API applies.

    Without this the CLI could mint an account whose address the API would
    later reject, producing a user who can never log in.
    """
    try:
        return str(_EMAIL_ADAPTER.validate_python(raw.strip())).lower()
    except ValidationError as exc:
        reason = exc.errors()[0].get("msg", "invalid email address")
        sys.exit(f"Invalid email address: {reason}")


def _read_password(supplied: str | None) -> str:
    """Take the password from the flag, or prompt without echoing it."""
    if supplied:
        return supplied
    first = getpass.getpass("Password: ")
    second = getpass.getpass("Confirm password: ")
    if first != second:
        sys.exit("Passwords do not match.")
    return first


def create_admin(email: str, password: str | None, full_name: str) -> int:
    """Create an administrator, or promote an existing user to administrator."""
    email = _validate_email(email)
    password = _read_password(password)
    if len(password) < PASSWORD_MIN:
        sys.exit(f"Password must be at least {PASSWORD_MIN} characters.")

    db = SessionLocal()
    try:
        repo = UserRepository(db)
        existing = repo.get_by_email(email)

        if existing is not None:
            existing.role = UserRole.ADMIN
            existing.is_active = True
            existing.hashed_password = hash_password(password)
            db.add(existing)
            db.commit()
            print(f"Promoted existing user to ADMIN: {email}")
            return 0

        user = User(
            email=email,
            hashed_password=hash_password(password),
            full_name=full_name,
            role=UserRole.ADMIN,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        print(f"Created ADMIN: {email}  (id={user.id})")
        return 0
    finally:
        db.close()


def list_admins() -> int:
    db = SessionLocal()
    try:
        admins = [
            u
            for u in UserRepository(db).list_users(limit=500)
            if u.role == UserRole.ADMIN
        ]
        if not admins:
            print("No administrators exist. Create one with 'create-admin'.")
            return 0
        for u in admins:
            state = "active" if u.is_active else "inactive"
            print(f"{u.email:<40} {state:<9} {u.id}")
        return 0
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create-admin", help="Create or promote an administrator")
    create.add_argument("--email", required=True)
    create.add_argument(
        "--password",
        help="Omit to be prompted (avoids the password entering your shell history).",
    )
    create.add_argument("--full-name", default="Platform Administrator")

    sub.add_parser("list-admins", help="List administrator accounts")

    args = parser.parse_args(argv)
    if args.command == "create-admin":
        return create_admin(args.email, args.password, args.full_name)
    if args.command == "list-admins":
        return list_admins()
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
