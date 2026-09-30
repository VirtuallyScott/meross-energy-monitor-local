"""Which pole of a multi-pole breaker each channel reads (PNL-002, PNL-004).

Revision ID: 0003
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

STATEMENTS = [
    "ALTER TABLE channel ADD COLUMN breaker_pole smallint",
    # Existing placements predate per-pole sensors: number them in channel order.
    """
    UPDATE channel c SET breaker_pole = least(n.rn, c.breaker_poles)
    FROM (
      SELECT id, row_number() OVER (
        PARTITION BY panel_id, panel_slot ORDER BY device_id, channel_no
      ) AS rn
      FROM channel WHERE panel_id IS NOT NULL
    ) n
    WHERE n.id = c.id
    """,
    # Any legs beyond the breaker's pole count lose their position rather than collide.
    """
    UPDATE channel SET panel_id = NULL, panel_slot = NULL, breaker_poles = NULL,
      breaker_pole = NULL, breaker_amps = NULL
    WHERE panel_id IS NOT NULL AND id IN (
      SELECT id FROM (
        SELECT id, row_number() OVER (
          PARTITION BY panel_id, panel_slot ORDER BY device_id, channel_no
        ) AS rn, breaker_poles FROM channel WHERE panel_id IS NOT NULL
      ) x WHERE rn > breaker_poles
    )
    """,
    """
    ALTER TABLE channel
      ADD CONSTRAINT ck_channel_breaker_pole CHECK (breaker_pole BETWEEN 1 AND breaker_poles),
      ADD CONSTRAINT uq_channel_breaker_pole UNIQUE (panel_id, panel_slot, breaker_pole)
        DEFERRABLE INITIALLY DEFERRED
    """,
]


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    raise NotImplementedError("forward-only migrations (UPG-002)")
