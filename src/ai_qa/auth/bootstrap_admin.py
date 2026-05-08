"""CLI support for bootstrapping the first local administrator."""

import argparse
import getpass
import os

from sqlalchemy.exc import SQLAlchemyError

from ai_qa.auth.service import InvalidBootstrapInputError, bootstrap_admin
from ai_qa.db.session import create_session_factory

_PASSWORD_ENV = "AI_QA_BOOTSTRAP_ADMIN_PASSWORD"


def main(argv: list[str] | None = None) -> int:
    """Create or update an administrator account from operator input."""
    parser = argparse.ArgumentParser(description="Bootstrap a local AI QA admin account")
    parser.add_argument("--email", required=True, help="Admin email address")
    parser.add_argument("--name", required=True, help="Admin display name")
    parser.add_argument(
        "--no-update-password",
        action="store_true",
        help="Keep existing password if the admin account already exists",
    )
    args = parser.parse_args(argv)

    password = os.getenv(_PASSWORD_ENV)
    if password is None:
        password = getpass.getpass("Admin password: ")
        confirmation = getpass.getpass("Confirm admin password: ")
        if password != confirmation:
            raise SystemExit("Passwords do not match")

    session_factory = create_session_factory()
    try:
        with session_factory() as session:
            user = bootstrap_admin(
                session,
                args.email,
                args.name,
                password,
                update_password=not args.no_update_password,
            )
    except InvalidBootstrapInputError as exc:
        raise SystemExit(str(exc)) from exc
    except SQLAlchemyError as exc:
        raise SystemExit("Admin bootstrap failed due to a database error") from exc

    print(f"Admin account ready: {user.email} ({user.display_name})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
