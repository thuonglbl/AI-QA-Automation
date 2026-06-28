"""seed discovered models and benchmark scores

Seeds the admin model-benchmark dashboard data (the discovered-model snapshot +
the per-capability operator scores) so a fresh environment (e.g. UAT) shows the
ranked models immediately, without re-entering scores. Idempotent: each row is
inserted ON CONFLICT DO NOTHING, so it is a safe no-op where the rows already
exist (local dev, or after Alice has populated the snapshot on the target).
``updated_by_user_id`` is left NULL because user ids differ per environment.
Postgres-only (tests build the schema via create_all, not migrations).

Revision ID: 173fb95ecc4c
Revises: 8b1189329f95
Create Date: 2026-06-19
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "173fb95ecc4c"
down_revision: str | Sequence[str] | None = "8b1189329f95"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (model_id, display_name, supports_vision)
_DISCOVERED: list[tuple[str, str | None, bool | None]] = [
    ("Anthropic/Claude-GPT-OSS-120B", "Anthropic/Claude-GPT-OSS-120B", None),
    ("ask-your-corp-confluence", "Chat with your CORP Confluence", True),
    ("ask-your-corp-jira", "Chat with your CORP Jira", True),
    ("chat-with-corp-mcp", "Chat with CORP-MCP", False),
    ("claude-g5", "claude-g5", True),
    ("claude-oss", "claude-oss", True),
    ("inference-apertus-70b", "inference-apertus-70b", True),
    ("inference-apertus-70b-GRC", "inference-apertus-70b-GRC", None),
    ("inference-bl", "inference-bl", None),
    ("inference-deepseek-v32", "inference-deepseek-v32", True),
    ("inference-deepseek-v32-GRC", "inference-deepseek-v32-GRC", None),
    ("inference-gemma-12b-it", "inference-gemma-12b-it", True),
    ("inference-gemma4-31b", "inference-gemma4-31b", None),
    ("inference-gemma4-31b-GRC", "inference-gemma4-31b-GRC", None),
    ("inference-glm-51-754b", "inference-glm-51-754b", None),
    ("inference-glm45-air-110b", "inference-glm45-air-110b", True),
    ("inference-gpt-oss-120b", "inference-gpt-oss-120b", True),
    ("inference-gpt-oss-120b-GRC", "inference-gpt-oss-120b-GRC", None),
    ("inference-granite-33-8b", "inference-granite-33-8b", True),
    ("inference-granite-vision-2b", "inference-granite-vision-2b", True),
    ("inference-llama4-maverick", "inference-llama4-maverick", True),
    ("inference-llama4-maverick-GRC", "inference-llama4-maverick-GRC", None),
    ("inference-llama4-scout-17b", "inference-llama4-scout-17b", True),
    ("inference-mistral-v03-7b", "inference-mistral-v03-7b", True),
    ("inference-qwen3-8b", "inference-qwen3-8b", True),
    ("inference-qwen3-vl-235b", "inference-qwen3-vl-235b", True),
    ("inference-qwen3-vl-235b-GRC", "inference-qwen3-vl-235b-GRC", None),
    ("inference-qwq-32b", "inference-qwq-32b", True),
    ("on-premises-corp-gpt-osslatest", "On-premises-Custom-CORP-gpt-oss:latest", True),
]

# (model_id, capability, score)
_SCORES: list[tuple[str, str, float]] = [
    ("Anthropic/Claude-GPT-OSS-120B", "coding", 0.0),
    ("Anthropic/Claude-GPT-OSS-120B", "fast", 0.0),
    ("Anthropic/Claude-GPT-OSS-120B", "global", 0.0),
    ("Anthropic/Claude-GPT-OSS-120B", "instruction", 0.0),
    ("Anthropic/Claude-GPT-OSS-120B", "reasoning", 0.0),
    ("Anthropic/Claude-GPT-OSS-120B", "vision", 0.0),
    ("ask-your-corp-confluence", "coding", 0.0),
    ("ask-your-corp-confluence", "fast", 0.0),
    ("ask-your-corp-confluence", "global", 0.0),
    ("ask-your-corp-confluence", "instruction", 0.0),
    ("ask-your-corp-confluence", "reasoning", 0.0),
    ("ask-your-corp-confluence", "vision", 0.0),
    ("ask-your-corp-jira", "coding", 0.0),
    ("ask-your-corp-jira", "fast", 0.0),
    ("ask-your-corp-jira", "global", 0.0),
    ("ask-your-corp-jira", "instruction", 0.0),
    ("ask-your-corp-jira", "reasoning", 0.0),
    ("ask-your-corp-jira", "vision", 0.0),
    ("chat-with-corp-mcp", "coding", 0.0),
    ("chat-with-corp-mcp", "fast", 0.0),
    ("chat-with-corp-mcp", "global", 0.0),
    ("chat-with-corp-mcp", "instruction", 0.0),
    ("chat-with-corp-mcp", "reasoning", 0.0),
    ("chat-with-corp-mcp", "vision", 0.0),
    ("claude-g5", "coding", 0.0),
    ("claude-g5", "fast", 0.0),
    ("claude-g5", "global", 0.0),
    ("claude-g5", "instruction", 0.0),
    ("claude-g5", "reasoning", 0.0),
    ("claude-g5", "vision", 0.0),
    ("claude-oss", "coding", 0.0),
    ("claude-oss", "fast", 0.0),
    ("claude-oss", "global", 0.0),
    ("claude-oss", "instruction", 0.0),
    ("claude-oss", "reasoning", 0.0),
    ("claude-oss", "vision", 0.0),
    ("inference-apertus-70b", "coding", 45.0),
    ("inference-apertus-70b", "fast", 48.0),
    ("inference-apertus-70b", "global", 58.0),
    ("inference-apertus-70b", "instruction", 58.0),
    ("inference-apertus-70b", "reasoning", 60.0),
    ("inference-apertus-70b", "vision", 0.0),
    ("inference-apertus-70b-GRC", "coding", 45.0),
    ("inference-apertus-70b-GRC", "fast", 48.0),
    ("inference-apertus-70b-GRC", "global", 58.0),
    ("inference-apertus-70b-GRC", "instruction", 58.0),
    ("inference-apertus-70b-GRC", "reasoning", 60.0),
    ("inference-apertus-70b-GRC", "vision", 0.0),
    ("inference-bl", "coding", 0.0),
    ("inference-bl", "fast", 0.0),
    ("inference-bl", "global", 0.0),
    ("inference-bl", "instruction", 0.0),
    ("inference-bl", "reasoning", 0.0),
    ("inference-bl", "vision", 0.0),
    ("inference-deepseek-v32", "coding", 82.0),
    ("inference-deepseek-v32", "fast", 30.0),
    ("inference-deepseek-v32", "global", 84.0),
    ("inference-deepseek-v32", "instruction", 85.0),
    ("inference-deepseek-v32", "reasoning", 88.0),
    ("inference-deepseek-v32", "vision", 0.0),
    ("inference-deepseek-v32-GRC", "coding", 82.0),
    ("inference-deepseek-v32-GRC", "fast", 30.0),
    ("inference-deepseek-v32-GRC", "global", 84.0),
    ("inference-deepseek-v32-GRC", "instruction", 85.0),
    ("inference-deepseek-v32-GRC", "reasoning", 88.0),
    ("inference-deepseek-v32-GRC", "vision", 0.0),
    ("inference-gemma-12b-it", "coding", 45.0),
    ("inference-gemma-12b-it", "fast", 85.0),
    ("inference-gemma-12b-it", "global", 56.0),
    ("inference-gemma-12b-it", "instruction", 58.0),
    ("inference-gemma-12b-it", "reasoning", 58.0),
    ("inference-gemma-12b-it", "vision", 65.0),
    ("inference-gemma4-31b", "coding", 55.0),
    ("inference-gemma4-31b", "fast", 60.0),
    ("inference-gemma4-31b", "global", 70.0),
    ("inference-gemma4-31b", "instruction", 70.0),
    ("inference-gemma4-31b", "reasoning", 70.0),
    ("inference-gemma4-31b", "vision", 80.0),
    ("inference-gemma4-31b-GRC", "coding", 55.0),
    ("inference-gemma4-31b-GRC", "fast", 60.0),
    ("inference-gemma4-31b-GRC", "global", 70.0),
    ("inference-gemma4-31b-GRC", "instruction", 70.0),
    ("inference-gemma4-31b-GRC", "reasoning", 70.0),
    ("inference-gemma4-31b-GRC", "vision", 80.0),
    ("inference-glm-51-754b", "coding", 90.0),
    ("inference-glm-51-754b", "fast", 25.0),
    ("inference-glm-51-754b", "global", 90.0),
    ("inference-glm-51-754b", "instruction", 90.0),
    ("inference-glm-51-754b", "reasoning", 92.0),
    ("inference-glm-51-754b", "vision", 0.0),
    ("inference-glm45-air-110b", "coding", 76.0),
    ("inference-glm45-air-110b", "fast", 65.0),
    ("inference-glm45-air-110b", "global", 80.0),
    ("inference-glm45-air-110b", "instruction", 80.0),
    ("inference-glm45-air-110b", "reasoning", 82.0),
    ("inference-glm45-air-110b", "vision", 0.0),
    ("inference-gpt-oss-120b", "coding", 70.0),
    ("inference-gpt-oss-120b", "fast", 60.0),
    ("inference-gpt-oss-120b", "global", 80.0),
    ("inference-gpt-oss-120b", "instruction", 88.0),
    ("inference-gpt-oss-120b", "reasoning", 85.0),
    ("inference-gpt-oss-120b", "vision", 0.0),
    ("inference-gpt-oss-120b-GRC", "coding", 70.0),
    ("inference-gpt-oss-120b-GRC", "fast", 60.0),
    ("inference-gpt-oss-120b-GRC", "global", 80.0),
    ("inference-gpt-oss-120b-GRC", "instruction", 88.0),
    ("inference-gpt-oss-120b-GRC", "reasoning", 85.0),
    ("inference-gpt-oss-120b-GRC", "vision", 0.0),
    ("inference-granite-33-8b", "coding", 42.0),
    ("inference-granite-33-8b", "fast", 88.0),
    ("inference-granite-33-8b", "global", 52.0),
    ("inference-granite-33-8b", "instruction", 60.0),
    ("inference-granite-33-8b", "reasoning", 50.0),
    ("inference-granite-33-8b", "vision", 0.0),
    ("inference-granite-vision-2b", "coding", 15.0),
    ("inference-granite-vision-2b", "fast", 70.0),
    ("inference-granite-vision-2b", "global", 35.0),
    ("inference-granite-vision-2b", "instruction", 30.0),
    ("inference-granite-vision-2b", "reasoning", 25.0),
    ("inference-granite-vision-2b", "vision", 45.0),
    ("inference-llama4-maverick", "coding", 65.0),
    ("inference-llama4-maverick", "fast", 45.0),
    ("inference-llama4-maverick", "global", 78.0),
    ("inference-llama4-maverick", "instruction", 78.0),
    ("inference-llama4-maverick", "reasoning", 80.0),
    ("inference-llama4-maverick", "vision", 85.0),
    ("inference-llama4-maverick-GRC", "coding", 65.0),
    ("inference-llama4-maverick-GRC", "fast", 45.0),
    ("inference-llama4-maverick-GRC", "global", 78.0),
    ("inference-llama4-maverick-GRC", "instruction", 78.0),
    ("inference-llama4-maverick-GRC", "reasoning", 80.0),
    ("inference-llama4-maverick-GRC", "vision", 85.0),
    ("inference-llama4-scout-17b", "coding", 55.0),
    ("inference-llama4-scout-17b", "fast", 70.0),
    ("inference-llama4-scout-17b", "global", 65.0),
    ("inference-llama4-scout-17b", "instruction", 65.0),
    ("inference-llama4-scout-17b", "reasoning", 68.0),
    ("inference-llama4-scout-17b", "vision", 72.0),
    ("inference-mistral-v03-7b", "coding", 35.0),
    ("inference-mistral-v03-7b", "fast", 88.0),
    ("inference-mistral-v03-7b", "global", 42.0),
    ("inference-mistral-v03-7b", "instruction", 48.0),
    ("inference-mistral-v03-7b", "reasoning", 40.0),
    ("inference-mistral-v03-7b", "vision", 0.0),
    ("inference-qwen3-8b", "coding", 58.0),
    ("inference-qwen3-8b", "fast", 92.0),
    ("inference-qwen3-8b", "global", 64.0),
    ("inference-qwen3-8b", "instruction", 66.0),
    ("inference-qwen3-8b", "reasoning", 62.0),
    ("inference-qwen3-8b", "vision", 0.0),
    ("inference-qwen3-vl-235b", "coding", 78.0),
    ("inference-qwen3-vl-235b", "fast", 35.0),
    ("inference-qwen3-vl-235b", "global", 86.0),
    ("inference-qwen3-vl-235b", "instruction", 86.0),
    ("inference-qwen3-vl-235b", "reasoning", 87.0),
    ("inference-qwen3-vl-235b", "vision", 95.0),
    ("inference-qwen3-vl-235b-GRC", "coding", 78.0),
    ("inference-qwen3-vl-235b-GRC", "fast", 35.0),
    ("inference-qwen3-vl-235b-GRC", "global", 86.0),
    ("inference-qwen3-vl-235b-GRC", "instruction", 86.0),
    ("inference-qwen3-vl-235b-GRC", "reasoning", 87.0),
    ("inference-qwen3-vl-235b-GRC", "vision", 95.0),
    ("inference-qwq-32b", "coding", 64.0),
    ("inference-qwq-32b", "fast", 52.0),
    ("inference-qwq-32b", "global", 72.0),
    ("inference-qwq-32b", "instruction", 70.0),
    ("inference-qwq-32b", "reasoning", 80.0),
    ("inference-qwq-32b", "vision", 0.0),
    ("on-premises-corp-gpt-osslatest", "coding", 0.0),
    ("on-premises-corp-gpt-osslatest", "fast", 0.0),
    ("on-premises-corp-gpt-osslatest", "global", 0.0),
    ("on-premises-corp-gpt-osslatest", "instruction", 0.0),
    ("on-premises-corp-gpt-osslatest", "reasoning", 0.0),
    ("on-premises-corp-gpt-osslatest", "vision", 0.0),
]


def _discovered_table() -> sa.TableClause:
    return sa.table(
        "discovered_models",
        sa.column("id", sa.Uuid),
        sa.column("model_id", sa.String),
        sa.column("display_name", sa.String),
        sa.column("supports_vision", sa.Boolean),
        sa.column("last_seen_at", sa.DateTime(timezone=True)),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )


def _scores_table() -> sa.TableClause:
    return sa.table(
        "model_benchmark_scores",
        sa.column("id", sa.Uuid),
        sa.column("model_id", sa.String),
        sa.column("capability", sa.String),
        sa.column("score", sa.Float),
        sa.column("note", sa.Text),
        sa.column("updated_by_user_id", sa.Uuid),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    now = sa.func.now()
    new_uuid = sa.func.gen_random_uuid()
    discovered = _discovered_table()
    for model_id, display_name, supports_vision in _DISCOVERED:
        op.execute(
            pg_insert(discovered)
            .values(
                id=new_uuid,
                model_id=model_id,
                display_name=display_name,
                supports_vision=supports_vision,
                last_seen_at=now,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_nothing(index_elements=["model_id"])
        )
    scores = _scores_table()
    for model_id, capability, score in _SCORES:
        op.execute(
            pg_insert(scores)
            .values(
                id=new_uuid,
                model_id=model_id,
                capability=capability,
                score=score,
                note=None,
                updated_by_user_id=None,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_nothing(index_elements=["model_id", "capability"])
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    score_ids = sorted({m for m, _, _ in _SCORES})
    disc_ids = sorted({m for m, _, _ in _DISCOVERED})
    op.execute(
        sa.text("DELETE FROM model_benchmark_scores WHERE model_id IN :ids").bindparams(
            sa.bindparam("ids", value=score_ids, expanding=True)
        )
    )
    op.execute(
        sa.text("DELETE FROM discovered_models WHERE model_id IN :ids").bindparams(
            sa.bindparam("ids", value=disc_ids, expanding=True)
        )
    )
