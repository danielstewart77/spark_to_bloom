#!/usr/bin/env python3
"""Bootstrap or update a Spark to Bloom auth user."""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from auth import create_user  # noqa: E402


def _read_password() -> str:
    password = getpass.getpass("Password: ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        raise ValueError("Passwords did not match.")
    if not password:
        raise ValueError("Password must not be empty.")
    return password


def main() -> int:
    parser = argparse.ArgumentParser(description="Create or update a Spark to Bloom user.")
    parser.add_argument("--username", required=True)
    parser.add_argument("--password")
    parser.add_argument("--admin", action="store_true")
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()

    password = args.password or _read_password()
    user = create_user(
        args.username,
        password,
        is_admin=args.admin,
        replace=args.replace,
    )
    print(
        f"created user username={user['username']} "
        f"admin={bool(user['is_admin'])} id={user['id']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
