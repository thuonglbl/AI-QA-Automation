"""Tests for the model_transfer tool."""

import datetime

from sqlalchemy.orm import Session

from ai_qa.admin.model_transfer import generate_migration_content
from ai_qa.db.models import DiscoveredModelSnapshot, ModelBenchmarkScore


def test_generate_migration_content(mock_db: Session) -> None:
    now = datetime.datetime.now(datetime.UTC)

    mock_model = DiscoveredModelSnapshot(
        model_id="mock-model",
        display_name="Mock Model",
        supports_vision=True,
        last_seen_at=now,
    )
    mock_score = ModelBenchmarkScore(
        model_id="mock-model",
        capability="reasoning",
        score=95.5,
    )

    class MockResult:
        def __init__(self, data):
            self.data = data

        def scalars(self):
            return self

        def all(self):
            return self.data

    def mock_execute(stmt):
        stmt_str = str(stmt)
        if "discovered_models" in stmt_str:
            return MockResult([mock_model])
        if "model_benchmark_scores" in stmt_str:
            return MockResult([mock_score])
        return MockResult([])

    mock_db.execute.side_effect = mock_execute

    # Generate content
    content = generate_migration_content(mock_db, "fake_down_rev")

    assert "fake_down_rev" in content
    assert "'mock-model', 'Mock Model', True" in content
    assert "'mock-model', 'reasoning', 95.5" in content
    assert "DELETE FROM model_benchmark_scores" in content
