import { useMutation, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { Alert, Button, Field, Panel, StatusDot } from "../../components/ui";
import { errorMessage, post } from "../../lib/api";
import { formatUptime, relativeTime } from "../../lib/format";
import { useDevices, useMe } from "../../lib/queries";
import { type Device, hasPerm, type ProbeResult } from "../../lib/types";
import "./devices.css";

export function DevicesPage() {
  const { siteId = "" } = useParams();
  const { data: me } = useMe();
  const { data: devices, isLoading, error } = useDevices(siteId);
  const canManage = hasPerm(me, "device:manage", siteId);

  return (
    <div className="devices-page">
      <Panel title="Energy monitors" eyebrow="This site">
        {error && <Alert>{errorMessage(error)}</Alert>}
        {isLoading && <p className="eyebrow">Loading…</p>}
        {devices && devices.length === 0 && <p>No devices on this site yet.</p>}
        {devices && devices.length > 0 && <DeviceTable devices={devices} siteId={siteId} />}
      </Panel>
      {canManage && <AddDevice siteId={siteId} />}
    </div>
  );
}

function DeviceTable({ devices, siteId }: { devices: Device[]; siteId: string }) {
  return (
    <div className="table-scroll">
      <table className="data-table">
        <thead>
          <tr>
            <th scope="col">Device</th>
            <th scope="col">State</th>
            <th scope="col">Address</th>
            <th scope="col">Last data</th>
            <th scope="col">Wi-Fi</th>
            <th scope="col">Uptime</th>
          </tr>
        </thead>
        <tbody>
          {devices.map((d) => (
            <tr key={d.id}>
              <th scope="row">
                <Link to={`/s/${siteId}/devices/${d.id}`}>{d.name}</Link>
                <span className="sub num">
                  {d.model.toUpperCase()} · fw {d.fw_ver ?? "?"}
                </span>
                {!d.auth_enabled && <span className="tag tag-warn">No device password</span>}
              </th>
              <td>
                {d.enabled ? (
                  <StatusDot online={d.online} />
                ) : (
                  <span className="tag">Disabled</span>
                )}
              </td>
              <td className="num">{d.base_url.replace(/^https?:\/\//, "")}</td>
              <td>{relativeTime(d.last_seen_at)}</td>
              <td className="num">{d.wifi_rssi !== null ? `${d.wifi_rssi} dBm` : "—"}</td>
              <td className="num">{formatUptime(d.uptime_s)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AddDevice({ siteId }: { siteId: string }) {
  const qc = useQueryClient();
  const [address, setAddress] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [preview, setPreview] = useState<ProbeResult | null>(null);

  const body = () => ({ address, password: password || null });
  const probe = useMutation({
    mutationFn: () => post<ProbeResult>("/devices/probe", body()),
    onSuccess: (result) => {
      setPreview(result);
      setName(result.name);
    },
  });
  const create = useMutation({
    mutationFn: () =>
      post<Device>("/devices", { ...body(), site_id: siteId, display_name: name || null }),
    onSuccess: () => {
      setAddress("");
      setPassword("");
      setPreview(null);
      qc.invalidateQueries({ queryKey: ["devices", siteId] });
    },
  });

  const onProbe = (e: FormEvent) => {
    e.preventDefault();
    setPreview(null);
    probe.mutate();
  };

  return (
    <Panel title="Add a device" eyebrow="By address">
      <form onSubmit={onProbe} className="add-form">
        {probe.isError && <Alert>{errorMessage(probe.error)}</Alert>}
        <Field
          label="IP address or URL"
          required
          placeholder="192.168.2.75"
          value={address}
          onChange={(e) => {
            setAddress(e.target.value);
            setPreview(null);
          }}
          hint="Private network addresses only. Give the device a DHCP reservation so it keeps this address."
        />
        <Field
          label="Device password (optional)"
          type="password"
          maxLength={32}
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          hint="Only needed if a password is set on the device. Stored encrypted and never shown again."
        />
        <Button type="submit" disabled={!address || probe.isPending}>
          {probe.isPending ? "Contacting device…" : "Find device"}
        </Button>
      </form>

      {preview && (
        <div className="probe-result">
          <dl>
            <div>
              <dt>Model</dt>
              <dd className="num">{preview.model.toUpperCase()}</dd>
            </div>
            <div>
              <dt>Device ID</dt>
              <dd className="num">{preview.dev_id}</dd>
            </div>
            <div>
              <dt>Firmware</dt>
              <dd className="num">{preview.fw_ver}</dd>
            </div>
            <div>
              <dt>Auth</dt>
              <dd>{preview.auth_enabled ? "Password required" : "No password set"}</dd>
            </div>
          </dl>
          {!preview.auth_enabled && (
            <Alert tone="info">
              This device accepts commands from anyone on the network. Set a password in its web UI.
            </Alert>
          )}
          {create.isError && <Alert>{errorMessage(create.error)}</Alert>}
          <Field label="Display name" value={name} onChange={(e) => setName(e.target.value)} />
          <Button tone="primary" onClick={() => create.mutate()} disabled={create.isPending}>
            {create.isPending ? "Adding…" : "Add this device"}
          </Button>
        </div>
      )}
    </Panel>
  );
}
