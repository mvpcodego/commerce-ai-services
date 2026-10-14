"""Очередь задач и журнал попыток

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("priority", sa.SmallInteger, nullable=False, server_default="0"),
        sa.Column("status", sa.Text, nullable=False, server_default="queued"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer, nullable=False, server_default="5"),
        sa.Column("run_after", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deadline", sa.DateTime(timezone=True)),
        sa.Column("idempotency_key", sa.Text, unique=True),
        sa.Column("locked_by", sa.Text),
        sa.Column("locked_at", sa.DateTime(timezone=True)),
        sa.Column("result", postgresql.JSONB),
        sa.Column("last_error", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status in ('queued','running','done','failed','dead','expired')", name="jobs_status_check"
        ),
        schema="ops",
    )
    # Частичный индекс под захват: в нём только задачи, которые ещё ждут исполнения.
    op.create_index(
        "jobs_ready_idx",
        "jobs",
        [sa.text("priority desc"), "run_after", "id"],
        schema="ops",
        postgresql_where=sa.text("status in ('queued','failed')"),
    )
    op.create_index(
        "jobs_running_idx", "jobs", ["locked_at"], schema="ops", postgresql_where=sa.text("status = 'running'")
    )
    op.create_table(
        "job_runs",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("job_id", sa.BigInteger, sa.ForeignKey("ops.jobs.id", ondelete="cascade"), nullable=False),
        sa.Column("attempt", sa.Integer, nullable=False),
        sa.Column("worker", sa.Text, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("ok", sa.Boolean, nullable=False),
        sa.Column("error", sa.Text),
        sa.Column("duration_ms", sa.Integer, nullable=False),
        schema="ops",
    )
    op.create_index("job_runs_job_id_idx", "job_runs", ["job_id"], schema="ops")


def downgrade() -> None:
    op.drop_table("job_runs", schema="ops")
    op.drop_table("jobs", schema="ops")
