"""Panels and channel breaker positions (PNL-001, PNL-002).

Revision ID: 0002
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

STATEMENTS = [
    """
    CREATE TABLE panel (
      id uuid PRIMARY KEY,
      site_id uuid NOT NULL REFERENCES site(id),
      name varchar(120) NOT NULL,
      spaces smallint NOT NULL
        CONSTRAINT ck_panel_spaces CHECK (spaces BETWEEN 2 AND 84 AND spaces % 2 = 0),
      numbering varchar(16) NOT NULL DEFAULT 'odd_even'
        CONSTRAINT ck_panel_numbering CHECK (numbering IN ('odd_even','sequential')),
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX ix_panel_site ON panel(site_id)",
    """
    ALTER TABLE channel
      ADD COLUMN panel_id uuid REFERENCES panel(id),
      ADD COLUMN panel_slot smallint,
      ADD COLUMN breaker_poles smallint
        CONSTRAINT ck_channel_breaker_poles CHECK (breaker_poles IN (1, 2, 3)),
      ADD COLUMN breaker_amps smallint
        CONSTRAINT ck_channel_breaker_amps CHECK (breaker_amps BETWEEN 1 AND 400),
      ADD CONSTRAINT ck_channel_panel_slot CHECK ((panel_id IS NULL) = (panel_slot IS NULL))
    """,
    "CREATE INDEX ix_channel_panel ON channel(panel_id) WHERE panel_id IS NOT NULL",
]


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    raise NotImplementedError("forward-only migrations (UPG-002)")
