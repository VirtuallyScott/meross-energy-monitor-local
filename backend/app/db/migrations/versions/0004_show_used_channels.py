"""Show channels that were hidden as ``unused`` at discovery but have since been given a role.

Until now the UI could not change ``visible`` and a role change left it as it was, so every
hidden channel with a real role was hidden by this bug, not by choice (CIR-001, CIR-002).

Revision ID: 0004
"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE channel SET visible = true WHERE role <> 'unused' AND NOT visible")


def downgrade() -> None:
    raise NotImplementedError("forward-only migrations (UPG-002)")
