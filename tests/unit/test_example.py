import pytest


# Example of a factory-like fixture
@pytest.fixture
def sample_user():
    return {"id": 1, "username": "testuser", "email": "test@example.com"}


@pytest.mark.parametrize("input_val, expected", [(1, 2), (2, 4), (3, 6)])
def test_example_math(input_val, expected):
    """Example test demonstrating parametrization."""
    assert input_val * 2 == expected


def test_example_fixture_usage(sample_user):
    """Example test demonstrating fixture usage."""
    assert sample_user["username"] == "testuser"
    assert "email" in sample_user
