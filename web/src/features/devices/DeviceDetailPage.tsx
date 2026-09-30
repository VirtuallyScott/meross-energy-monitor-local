import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { Alert, Button, Panel, StatusDot } from "../../components/ui";
import { errorMessage, patch, post, put } from "../../lib/api";
import { formatKwh, formatPower, relativeTime } from "../../lib/format";
import { useDevice, useMe } from "../../lib/queries";
import { type Channel, type ChannelRole, hasPerm } from "../../lib/types";
import "./devices.css";

const ROLES: { value: ChannelRole; label: string }[] = [
  { value: "grid_main", label: "Grid main" },
  { value: "branch", label: "Branch circuit" },
  { value: "solar", label: "Solar" },
  { value: "battery", label: "Battery" },
  { value: "unused", label: "Unused" },
];

type LiveValues = Record<
  string,
  { power?: number; voltage?: number; pf?: number; day_energy?: number }
>;

export function DeviceDetailPage() {
  const { siteId = "", deviceId = "" } = useParams();
  const qc = useQueryClient();
  const { data: me } = useMe();
  const { data: device, error } = useDevice(deviceId);
  const canManage = hasPerm(me, "device:manage", siteId);
  const canCredential = hasPerm(me, "device:credential", siteId);

  const test = useMutation({
    mutationFn: () =>
      post<{ ok: boolean; latency_ms?: number; error?: string }>(`/devices/${deviceId}/test`),
  });
  const sync = useMutation({
    mutationFn: () => post(`/devices/${deviceId}/sync`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["device", deviceId] }),
  });

  if (error) return <Alert>{errorMessage(error)}</Alert>;
  if (!device) return <p className="eyebrow">Loading…</p>;
  const status = ((device as unknown as { status?: LiveValues }).status ?? {}) as LiveValues;

  return (
    <div className="devices-page">
      <p className="crumb">
        <Link to={`/s/${siteId}/devices`}>Devices</Link> / {device.name}
      </p>
      <Panel
        title={device.name}
        eyebrow={`${device.model.toUpperCase()} · ${device.dev_id}`}
        actions={
          canManage && (
            <>
              <Button onClick={() => test.mutate()} disabled={test.isPending}>
                Test connection
              </Button>
              <Button onClick={() => sync.mutate()} disabled={sync.isPending}>
                Sync config
              </Button>
            </>
          )
        }
      >
        <dl className="facts">
          <div>
            <dt>State</dt>
            <dd>
              <StatusDot online={device.online} />
            </dd>
          </div>
          <div>
            <dt>Address</dt>
            <dd className="num">{device.base_url}</dd>
          </div>
          <div>
            <dt>Last live data</dt>
            <dd>{relativeTime(device.last_seen_at)}</dd>
          </div>
          <div>
            <dt>Last minute stored</dt>
            <dd>{relativeTime(device.last_minute_ts)}</dd>
          </div>
        </dl>
        {test.data && (
          <Alert tone={test.data.ok ? "info" : "danger"}>
            {test.data.ok ? `Reachable in ${test.data.latency_ms} ms.` : test.data.error}
          </Alert>
        )}
        {test.isError && <Alert>{errorMessage(test.error)}</Alert>}
        {sync.isError && <Alert>{errorMessage(sync.error)}</Alert>}
      </Panel>

      <Panel title="Channels" eyebrow="Roles decide what counts as whole-house and solar">
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">Pos.</th>
                <th scope="col">Name</th>
                <th scope="col">Role</th>
                <th scope="col">Power</th>
                <th scope="col">Voltage</th>
                <th scope="col">Today</th>
              </tr>
            </thead>
            <tbody>
              {(device.channels ?? []).map((c) => (
                <ChannelRow
                  key={c.id}
                  channel={c}
                  live={status[`em:${c.channel_no}`]}
                  deviceId={deviceId}
                  editable={canManage}
                />
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      {canCredential && <CredentialPanel deviceId={deviceId} hasPassword={device.has_password} />}
    </div>
  );
}

function ChannelRow({
  channel,
  live,
  deviceId,
  editable,
}: {
  channel: Channel;
  live: LiveValues[string] | undefined;
  deviceId: string;
  editable: boolean;
}) {
  const qc = useQueryClient();
  const update = useMutation({
    mutationFn: (body: Partial<Channel>) => patch(`/channels/${channel.id}`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["device", deviceId] }),
  });
  const power = formatPower(live?.power);
  return (
    <tr className={channel.role === "unused" ? "row-muted" : undefined}>
      <td className="num">{channel.phase_label ?? channel.channel_no}</td>
      <th scope="row">{channel.name}</th>
      <td>
        {editable ? (
          <select
            aria-label={`Role for ${channel.name}`}
            value={channel.role}
            disabled={update.isPending}
            onChange={(e) => update.mutate({ role: e.target.value as ChannelRole })}
          >
            {ROLES.map((r) => (
              <option key={r.value} value={r.value}>
                {r.label}
              </option>
            ))}
          </select>
        ) : (
          ROLES.find((r) => r.value === channel.role)?.label
        )}
      </td>
      <td className="num">
        {power.value} <span className="unit">{power.unit}</span>
      </td>
      <td className="num">{live?.voltage !== undefined ? `${live.voltage.toFixed(1)} V` : "—"}</td>
      <td className="num">{formatKwh(live?.day_energy)} kWh</td>
    </tr>
  );
}

function CredentialPanel({ deviceId, hasPassword }: { deviceId: string; hasPassword: boolean }) {
  const qc = useQueryClient();
  const [password, setPassword] = useState("");
  const save = useMutation({
    mutationFn: (value: string | null) =>
      put(`/devices/${deviceId}/credential`, { password: value }),
    onSuccess: () => {
      setPassword("");
      qc.invalidateQueries({ queryKey: ["device", deviceId] });
    },
  });
  return (
    <Panel title="Device password" eyebrow={hasPassword ? "Stored, encrypted" : "Not stored"}>
      {save.isError && <Alert>{errorMessage(save.error)}</Alert>}
      <form
        className="inline-form"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate(password);
        }}
      >
        <label className="visually-hidden" htmlFor="dev-pw">
          New device password
        </label>
        <input
          id="dev-pw"
          type="password"
          maxLength={32}
          autoComplete="new-password"
          value={password}
          placeholder="New password"
          onChange={(e) => setPassword(e.target.value)}
        />
        <Button type="submit" disabled={!password || save.isPending}>
          Save
        </Button>
        {hasPassword && (
          <Button tone="danger" type="button" onClick={() => save.mutate(null)}>
            Clear
          </Button>
        )}
      </form>
    </Panel>
  );
}
