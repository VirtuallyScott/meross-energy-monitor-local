"""Initial schema: config, auth, jobs, hypertables, aggregates, policies.

Revision ID: 0001
"""

import re

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

CONFIG_SQL = """
CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS citext;

CREATE TABLE site (
  id uuid PRIMARY KEY,
  name varchar(120) NOT NULL,
  time_zone varchar(64) NOT NULL,
  currency char(3) NOT NULL DEFAULT 'USD',
  address text,
  grid_circuit_id uuid, solar_circuit_id uuid, load_circuit_id uuid,
  version integer NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  archived_at timestamptz
);

CREATE TABLE device (
  id uuid PRIMARY KEY,
  site_id uuid NOT NULL REFERENCES site(id),
  dev_id varchar(80) NOT NULL UNIQUE,
  display_name varchar(120), device_name varchar(120),
  base_url varchar(300) NOT NULL,
  model varchar(32) NOT NULL, fw_ver varchar(32), hw_ver varchar(32), mac varchar(32),
  auth_enabled boolean NOT NULL DEFAULT false,
  credential_ciphertext bytea, credential_key_version smallint, credential_updated_at timestamptz,
  enabled boolean NOT NULL DEFAULT true,
  online boolean NOT NULL DEFAULT false,
  last_seen_at timestamptz, last_minute_ts timestamptz,
  status_json jsonb,
  version integer NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  archived_at timestamptz
);
CREATE INDEX ix_device_site ON device(site_id);

CREATE TABLE channel (
  id uuid PRIMARY KEY,
  device_id uuid NOT NULL REFERENCES device(id) ON DELETE CASCADE,
  channel_no smallint NOT NULL,
  device_label varchar(120), display_name varchar(120),
  role varchar(16) NOT NULL DEFAULT 'branch'
    CONSTRAINT ck_channel_role CHECK (role IN ('grid_main','solar','battery','branch','unused')),
  phase_label varchar(16), ct_factor double precision,
  visible boolean NOT NULL DEFAULT true,
  CONSTRAINT uq_channel_device_no UNIQUE (device_id, channel_no)
);

CREATE TABLE circuit (
  id uuid PRIMARY KEY,
  site_id uuid NOT NULL REFERENCES site(id),
  name varchar(120) NOT NULL,
  kind varchar(16) NOT NULL CONSTRAINT ck_circuit_kind CHECK (kind IN ('device_merge','virtual')),
  device_id uuid REFERENCES device(id) ON DELETE CASCADE,
  device_merge_mask bigint,
  tags varchar(40)[] NOT NULL DEFAULT '{}',
  version integer NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  archived_at timestamptz
);
CREATE UNIQUE INDEX uq_circuit_device_merge ON circuit(device_id, device_merge_mask)
  WHERE kind = 'device_merge';

CREATE TABLE circuit_member (
  circuit_id uuid NOT NULL REFERENCES circuit(id) ON DELETE CASCADE,
  channel_id uuid NOT NULL REFERENCES channel(id) ON DELETE CASCADE,
  sign smallint NOT NULL DEFAULT 1 CONSTRAINT ck_circuit_member_sign CHECK (sign IN (1,-1)),
  PRIMARY KEY (circuit_id, channel_id)
);

CREATE TABLE device_event (
  id bigserial PRIMARY KEY,
  device_id uuid NOT NULL REFERENCES device(id) ON DELETE CASCADE,
  ts timestamptz NOT NULL DEFAULT now(),
  kind varchar(40) NOT NULL,
  detail jsonb
);
CREATE INDEX ix_device_event_device_ts ON device_event(device_id, ts DESC);

CREATE TABLE data_gap (
  id bigserial PRIMARY KEY,
  channel_id uuid NOT NULL REFERENCES channel(id) ON DELETE CASCADE,
  start_ts timestamptz NOT NULL, end_ts timestamptz NOT NULL,
  cause varchar(40) NOT NULL,
  resolved boolean NOT NULL DEFAULT false
);
CREATE INDEX ix_data_gap_channel ON data_gap(channel_id, start_ts);
"""

AUTH_SQL = """
CREATE TABLE app_user (
  id uuid PRIMARY KEY,
  username citext NOT NULL UNIQUE,
  email citext UNIQUE,
  display_name varchar(120),
  password_hash text NOT NULL,
  is_active boolean NOT NULL DEFAULT true,
  last_login_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE user_role_binding (
  id uuid PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
  role_id varchar(32) NOT NULL
    CHECK (role_id IN ('admin','site_manager','energy_analyst','viewer','kiosk')),
  site_id uuid REFERENCES site(id) ON DELETE CASCADE,
  expires_at timestamptz,
  granted_by uuid,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_binding_user ON user_role_binding(user_id);

CREATE TABLE api_token (
  id uuid PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
  name varchar(80) NOT NULL,
  prefix varchar(16) NOT NULL,
  token_hash bytea NOT NULL UNIQUE,
  permissions varchar(40)[] NOT NULL,
  site_id uuid REFERENCES site(id) ON DELETE CASCADE,
  kind varchar(16) NOT NULL DEFAULT 'personal',
  expires_at timestamptz NOT NULL,
  last_used_at timestamptz, revoked_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE user_session (
  id_hash bytea PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
  csrf_token varchar(64) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  last_seen_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL,
  ip inet, user_agent varchar(300)
);
CREATE INDEX ix_session_user ON user_session(user_id);

CREATE TABLE audit_log (
  id bigserial PRIMARY KEY,
  ts timestamptz NOT NULL DEFAULT now(),
  actor_user_id uuid, actor_token_id uuid, source_ip inet,
  action varchar(64) NOT NULL,
  resource_type varchar(40), resource_id varchar(64), site_id uuid,
  outcome varchar(16) NOT NULL DEFAULT 'success',
  detail jsonb
);
CREATE INDEX ix_audit_ts ON audit_log(ts DESC);

-- AUD-001: the log is append-only for application code.
CREATE FUNCTION audit_log_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'audit_log is append-only'; END $$;
CREATE TRIGGER audit_log_no_update BEFORE UPDATE OR DELETE ON audit_log
  FOR EACH ROW EXECUTE FUNCTION audit_log_immutable();

CREATE TABLE job (
  id uuid PRIMARY KEY,
  kind varchar(40) NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}',
  status varchar(16) NOT NULL DEFAULT 'queued',
  run_after timestamptz NOT NULL DEFAULT now(),
  attempts integer NOT NULL DEFAULT 0,
  max_attempts integer NOT NULL DEFAULT 3,
  created_by uuid,
  created_at timestamptz NOT NULL DEFAULT now(),
  started_at timestamptz, finished_at timestamptz,
  error text, result jsonb
);
CREATE INDEX ix_job_queue ON job(status, run_after) WHERE status = 'queued';
"""

TIMESERIES_SQL = """
CREATE TABLE energy_minute (
  channel_id uuid NOT NULL,
  ts timestamptz NOT NULL,
  energy_kwh double precision, ret_energy_kwh double precision,
  voltage_min double precision, voltage_avg double precision, voltage_max double precision,
  current_min double precision, current_avg double precision, current_max double precision,
  power_min double precision, power_avg double precision, power_max double precision,
  ret_power_min double precision, ret_power_avg double precision, ret_power_max double precision,
  quality smallint NOT NULL DEFAULT 0,
  ingested_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (channel_id, ts)
);
SELECT create_hypertable('energy_minute', by_range('ts', INTERVAL '7 days'));
ALTER TABLE energy_minute SET (
  timescaledb.compress,
  timescaledb.compress_segmentby = 'channel_id',
  timescaledb.compress_orderby = 'ts DESC'
);
SELECT add_compression_policy('energy_minute', INTERVAL '7 days');
SELECT add_retention_policy('energy_minute', INTERVAL '730 days');

CREATE TABLE live_sample (
  channel_id uuid NOT NULL,
  ts timestamptz NOT NULL,
  power_w double precision, current_a double precision, voltage_v double precision,
  pf double precision,
  day_kwh double precision, week_kwh double precision,
  month_kwh double precision, year_kwh double precision,
  day_ret_kwh double precision, week_ret_kwh double precision,
  month_ret_kwh double precision, year_ret_kwh double precision,
  PRIMARY KEY (channel_id, ts)
);
SELECT create_hypertable('live_sample', by_range('ts', INTERVAL '1 day'));
ALTER TABLE live_sample SET (
  timescaledb.compress, timescaledb.compress_segmentby = 'channel_id'
);
SELECT add_compression_policy('live_sample', INTERVAL '1 day');
SELECT add_retention_policy('live_sample', INTERVAL '7 days');

CREATE TABLE device_status (
  device_id uuid NOT NULL,
  ts timestamptz NOT NULL,
  online boolean, rssi_dbm integer, uptime_s integer, clock_skew_s integer,
  cloud_connected boolean, mqtt_connected boolean,
  PRIMARY KEY (device_id, ts)
);
SELECT create_hypertable('device_status', by_range('ts', INTERVAL '7 days'));
ALTER TABLE device_status SET (
  timescaledb.compress, timescaledb.compress_segmentby = 'device_id'
);
SELECT add_compression_policy('device_status', INTERVAL '7 days');
SELECT add_retention_policy('device_status', INTERVAL '90 days');
"""

AGGREGATES_SQL = """
CREATE MATERIALIZED VIEW energy_15m WITH (timescaledb.continuous) AS
SELECT channel_id,
       time_bucket(INTERVAL '15 minutes', ts) AS bucket,
       sum(energy_kwh) AS energy_kwh,
       sum(ret_energy_kwh) AS ret_energy_kwh,
       avg(power_avg) AS power_avg,
       max(power_max) AS power_max,
       min(voltage_min) AS voltage_min,
       avg(voltage_avg) AS voltage_avg,
       max(voltage_max) AS voltage_max,
       avg(current_avg) AS current_avg,
       max(quality) AS quality,
       count(*) AS minutes
FROM energy_minute
GROUP BY channel_id, bucket
WITH NO DATA;
SELECT add_continuous_aggregate_policy('energy_15m',
  start_offset => INTERVAL '3 days', end_offset => INTERVAL '30 minutes',
  schedule_interval => INTERVAL '5 minutes');

CREATE MATERIALIZED VIEW energy_hourly WITH (timescaledb.continuous) AS
SELECT channel_id,
       time_bucket(INTERVAL '1 hour', bucket) AS bucket,
       sum(energy_kwh) AS energy_kwh,
       sum(ret_energy_kwh) AS ret_energy_kwh,
       sum(power_avg * minutes) / nullif(sum(minutes), 0) AS power_avg,
       max(power_max) AS power_max,
       min(voltage_min) AS voltage_min,
       sum(voltage_avg * minutes) / nullif(sum(minutes), 0) AS voltage_avg,
       max(voltage_max) AS voltage_max,
       sum(current_avg * minutes) / nullif(sum(minutes), 0) AS current_avg,
       max(quality) AS quality,
       sum(minutes) AS minutes
FROM energy_15m
GROUP BY channel_id, time_bucket(INTERVAL '1 hour', bucket)
WITH NO DATA;
SELECT add_continuous_aggregate_policy('energy_hourly',
  start_offset => INTERVAL '7 days', end_offset => INTERVAL '1 hour',
  schedule_interval => INTERVAL '15 minutes');
"""


def _statements(sql: str) -> list[str]:
    """Split on semicolons that end a line. asyncpg runs one statement per call."""
    return [part.strip() for part in re.split(r";\s*\n", sql) if part.strip()]


def upgrade() -> None:
    for block in (CONFIG_SQL, AUTH_SQL, TIMESERIES_SQL, AGGREGATES_SQL):
        for statement in _statements(block):
            op.execute(statement)


def downgrade() -> None:
    raise NotImplementedError("forward-only migrations (UPG-002)")
