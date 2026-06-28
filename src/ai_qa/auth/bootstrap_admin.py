"""CLI support for bootstrapping the first local administrator."""

import argparse

from sqlalchemy.exc import SQLAlchemyError

from ai_qa.auth.service import InvalidBootstrapInputError, bootstrap_admin
from ai_qa.db.session import create_session_factory


def main(argv: list[str] | None = None) -> int:
    """Create or update an administrator account from operator input."""
    parser = argparse.ArgumentParser(description="Bootstrap a local AI QA admin account")
    parser.add_argument("--email", required=True, help="Admin email address")
    parser.add_argument("--name", required=True, help="Admin display name")
    args = parser.parse_args(argv)

    session_factory = create_session_factory()
    try:
        with session_factory() as session:
            user = bootstrap_admin(
                session,
                args.email,
                args.name,
            )
    except InvalidBootstrapInputError as exc:
        raise SystemExit(str(exc)) from exc
    except SQLAlchemyError as exc:
        import traceback

        traceback.print_exc()
        raise SystemExit(f"Admin bootstrap failed due to a database error: {exc}") from exc

    print(f"Admin account ready: {user.email} ({user.display_name})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
