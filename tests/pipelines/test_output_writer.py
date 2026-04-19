"""Tests for the OutputWriter pipeline stage."""

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from ai_qa.pipelines.models import OutputMetadata
from ai_qa.pipelines.output_writer import OutputWriter


@pytest.fixture
def output_base_dir(tmp_path: Path) -> Path:
    """Provide a temporary directory for output."""
    return tmp_path / "workspace"


@pytest.fixture
def metadata() -> OutputMetadata:
    """Provide sample metadata."""
    return OutputMetadata(
        source_url="https://example.com/page",
        timestamp=datetime.now(UTC),
        model="gpt-4",
        confidence=0.95,
    )


@pytest.fixture
def writer(output_base_dir: Path) -> OutputWriter:
    """Provide an OutputWriter instance."""
    return OutputWriter(output_base_dir)


def test_to_kebab_case(writer: OutputWriter) -> None:
    """Test kebab-case conversion."""
    assert writer._to_kebab_case("Hello World") == "hello-world"
    assert writer._to_kebab_case("Test  Multiple   Spaces") == "test-multiple-spaces"
    assert writer._to_kebab_case("Special!@#Characters") == "special-characters"
    assert writer._to_kebab_case("-Leading and Trailing-") == "leading-and-trailing"


@pytest.mark.asyncio
async def test_write_success_text(
    writer: OutputWriter, output_base_dir: Path, metadata: OutputMetadata
) -> None:
    """Test successful write of text content."""
    result = await writer.write("Test File.txt", "Some text content", metadata)

    assert result.success is True
    assert result.confidence == 1.0
    assert not result.errors

    data = result.data
    assert data is not None
    assert "file_path" in data
    assert "metadata_path" in data

    file_path = Path(data["file_path"])
    metadata_path = Path(data["metadata_path"])

    assert file_path.exists()
    assert metadata_path.exists()

    assert file_path.read_text(encoding="utf-8") == "Some text content"

    # Verify metadata is written
    assert "gpt-4" in metadata_path.read_text(encoding="utf-8")

    # Verify directory structure
    assert file_path.parent == output_base_dir / "test-file"


@pytest.mark.asyncio
async def test_write_success_bytes(
    writer: OutputWriter, output_base_dir: Path, metadata: OutputMetadata
) -> None:
    """Test successful write of bytes content."""
    result = await writer.write("image.png", b"fake image data", metadata)

    assert result.success is True

    data = result.data
    assert data is not None
    file_path = Path(data["file_path"])

    assert file_path.exists()
    assert file_path.read_bytes() == b"fake image data"
    assert file_path.parent == output_base_dir / "image"


@pytest.mark.asyncio
@patch("pathlib.Path.replace")
async def test_write_os_error(mock_replace, writer: OutputWriter, metadata: OutputMetadata) -> None:
    """Test failure during write operations."""
    mock_replace.side_effect = OSError("Disk full")

    result = await writer.write("fail.txt", "content", metadata)

    assert result.success is False
    assert result.confidence == 0.0
    assert len(result.errors) == 1
    assert "Write failed: Disk full" in result.errors[0]


@pytest.mark.asyncio
@patch("pathlib.Path.replace")
async def test_write_unexpected_error(
    mock_replace, writer: OutputWriter, metadata: OutputMetadata
) -> None:
    """Test failure with an unexpected error."""
    mock_replace.side_effect = ValueError("Something completely unexpected")

    result = await writer.write("fail.txt", "content", metadata)

    assert result.success is False
    assert result.confidence == 0.0
    assert len(result.errors) == 1
    assert "Write failed due to unexpected error" in result.errors[0]
