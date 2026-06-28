"""Unit tests for the Azure app-role -> platform-role mapping (story 23.3)."""

from ai_qa.auth.service import (
    ADMIN_ROLE,
    PROJECT_ADMIN_ROLE,
    STANDARD_ROLE,
    map_app_roles,
    primary_role,
)


def test_single_role_maps() -> None:
    assert map_app_roles(["admin"]) == {ADMIN_ROLE}
    assert map_app_roles(["project-admin"]) == {PROJECT_ADMIN_ROLE}
    assert map_app_roles(["user"]) == {STANDARD_ROLE}


def test_multiple_roles_map_to_set() -> None:
    assert map_app_roles(["project-admin", "user"]) == {PROJECT_ADMIN_ROLE, STANDARD_ROLE}
    assert map_app_roles(["admin", "user"]) == {ADMIN_ROLE, STANDARD_ROLE}


def test_unknown_and_empty_default_to_standard() -> None:
    assert map_app_roles([]) == {STANDARD_ROLE}
    assert map_app_roles(None) == {STANDARD_ROLE}
    assert map_app_roles(["something-else"]) == {STANDARD_ROLE}
    # Unknown values are dropped but a known one still maps.
    assert map_app_roles(["nope", "admin"]) == {ADMIN_ROLE}


def test_case_insensitive_and_underscore_variant() -> None:
    assert map_app_roles(["ADMIN"]) == {ADMIN_ROLE}
    assert map_app_roles([" Project-Admin "]) == {PROJECT_ADMIN_ROLE}
    # Defensive: underscore variant of the Azure value also maps.
    assert map_app_roles(["project_admin"]) == {PROJECT_ADMIN_ROLE}


def test_non_string_values_are_ignored() -> None:
    assert map_app_roles(["admin", 123, None]) == {ADMIN_ROLE}  # type: ignore[list-item]


def test_primary_role_priority() -> None:
    assert primary_role({ADMIN_ROLE, PROJECT_ADMIN_ROLE, STANDARD_ROLE}) == ADMIN_ROLE
    assert primary_role({PROJECT_ADMIN_ROLE, STANDARD_ROLE}) == PROJECT_ADMIN_ROLE
    assert primary_role({STANDARD_ROLE}) == STANDARD_ROLE
    assert primary_role(set()) == STANDARD_ROLE
