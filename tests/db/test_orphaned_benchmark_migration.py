"""Migration d9c4f1a6e2b8 must delete exactly the on-prem score ids the 273 refresh orphaned.

Locks Story 16.14 against drift: the hand-maintained ``_ORPHANED_SCORE_MODEL_IDS`` must
equal ``set(173fb95ecc4c._SCORES ids) - set(273b69541e94._SCORES ids)``. A miss (e.g. the
``inference-granite-vision-2b`` omission caught in review) silently leaves stale-seed
scores that hijack Alice's Tier-0 selection.
"""

import importlib.util
from pathlib import Path
from types import ModuleType

_VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"


def _load_migration(glob_pattern: str) -> ModuleType:
    path = next(_VERSIONS.glob(glob_pattern))
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_orphan_delete_list_equals_seed_difference() -> None:
    initial = _load_migration("173fb95ecc4c_*.py")
    refresh = _load_migration("273b69541e94_*.py")
    fix = _load_migration("d9c4f1a6e2b8_*.py")

    # Access the module-private constants via vars() so the dynamic-module attributes
    # type as Any (clean under both ruff's B009 and Pyrefly's missing-attribute check).
    initial_ids = {row[0] for row in vars(initial)["_SCORES"]}
    refresh_ids = {row[0] for row in vars(refresh)["_SCORES"]}
    orphaned = vars(fix)["_ORPHANED_SCORE_MODEL_IDS"]

    # The fix must delete exactly the ids the refresh seeded-but-orphaned, no more, no less.
    assert set(orphaned) == (initial_ids - refresh_ids)
    # The known culprit and the review-caught miss must both be covered.
    assert "inference-qwen3-vl-235b-GRC" in orphaned
    assert "inference-granite-vision-2b" in orphaned
