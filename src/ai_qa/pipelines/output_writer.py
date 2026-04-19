"""Output writer pipeline stage.

Persists pipeline output and metadata to the filesystem.
"""

import logging
import re
import uuid
from pathlib import Path

from ai_qa.models import StageResult
from ai_qa.pipelines.models import OutputMetadata

logger = logging.getLogger(__name__)


class OutputWriter:
    """Pipeline stage for persisting output and its metadata."""

    def __init__(self, output_base_dir: Path) -> None:
        """Initialize writer.

        Args:
            output_base_dir: Base workspace directory (e.g., Path("workspace/requirements"))
        """
        self.output_base_dir = output_base_dir

    async def write(
        self, file_name: str, content: str | bytes, metadata: OutputMetadata
    ) -> StageResult:
        """Write a single file and its metadata.

        Args:
            file_name: Target filename (without path)
            content: Content to write
            metadata: Associated metadata

        Returns:
            StageResult with written file paths on success, errors on failure
        """
        try:
            # Generate safe subfolder name based on the filename (without extension)
            # Find the stem (name without extension) to use for subfolder
            # Protect against Path Traversal by extracting just the filename
            file_name_only = Path(file_name).name
            path_obj = Path(file_name_only)
            stem = path_obj.stem

            safe_subfolder = self._to_kebab_case(stem)
            target_dir = self.output_base_dir / safe_subfolder
            target_dir.mkdir(parents=True, exist_ok=True)

            target_file_path = target_dir / file_name_only
            target_metadata_path = target_dir / "metadata.json"

            # Avoid corrupting partial output: write to temp files first, then rename atomically
            # Use UUID to prevent race conditions during concurrent writes
            temp_id = uuid.uuid4().hex
            temp_file_path = target_file_path.with_suffix(f".tmp.{temp_id}")
            temp_metadata_path = target_metadata_path.with_suffix(f".tmp.{temp_id}")

            if isinstance(content, str):
                temp_file_path.write_text(content, encoding="utf-8")
            else:
                temp_file_path.write_bytes(content)

            temp_metadata_path.write_text(metadata.model_dump_json(indent=2), encoding="utf-8")

            # Atomic rename (replace)
            temp_file_path.replace(target_file_path)
            temp_metadata_path.replace(target_metadata_path)

            return StageResult(
                success=True,
                data={
                    "file_path": str(target_file_path),
                    "metadata_path": str(target_metadata_path),
                },
                errors=[],
                warnings=[],
                confidence=1.0,
            )

        except OSError as e:
            if "temp_file_path" in locals() and temp_file_path.exists():
                temp_file_path.unlink(missing_ok=True)
            if "temp_metadata_path" in locals() and temp_metadata_path.exists():
                temp_metadata_path.unlink(missing_ok=True)
            logger.error(f"Failed to write output to {self.output_base_dir}: {e}")
            return StageResult(
                success=False,
                data=None,
                errors=[f"Write failed: {e}"],
                warnings=[],
                confidence=0.0,
            )
        except Exception as e:
            if "temp_file_path" in locals() and temp_file_path.exists():
                temp_file_path.unlink(missing_ok=True)
            if "temp_metadata_path" in locals() and temp_metadata_path.exists():
                temp_metadata_path.unlink(missing_ok=True)
            logger.error(f"Unexpected error writing output: {e}")
            return StageResult(
                success=False,
                data=None,
                errors=[f"Write failed due to unexpected error: {e}"],
                warnings=[],
                confidence=0.0,
            )

    def _to_kebab_case(self, text: str) -> str:
        """Convert text to safe kebab-case filename.

        Args:
            text: Text to convert.

        Returns:
            Kebab-case string suitable for safe filenames.
        """
        # Convert to lowercase
        text = text.lower()
        # Replace non-alphanumeric characters with hyphens
        text = re.sub(r"[^a-z0-9]+", "-", text)
        # Remove leading and trailing hyphens
        return text.strip("-")
