export interface Me {
  user_id: string;
  username: string;
  global_permissions: string[];
  site_permissions: Record<string, string[]>;
}

export interface Site {
  id: string;
  name: string;
  time_zone: string;
  currency: string;
  load_circuit_id: string | null;
  grid_circuit_id: string | null;
}

export type ChannelRole = "grid_main" | "solar" | "battery" | "branch" | "unused";

export interface Channel {
  id: string;
  channel_no: number;
  name: string;
  display_name: string | null;
  device_label: string | null;
  role: ChannelRole;
  phase_label: string | null;
  ct_factor: number | null;
  visible: boolean;
}

export interface Device {
  id: string;
  site_id: string;
  dev_id: string;
  name: string;
  base_url: string;
  model: string;
  fw_ver: string | null;
  auth_enabled: boolean;
  has_password: boolean;
  enabled: boolean;
  online: boolean;
  last_seen_at: string | null;
  last_minute_ts: string | null;
  wifi_rssi: number | null;
  uptime_s: number | null;
  channels?: Channel[];
}

export interface ProbeResult {
  base_url: string;
  dev_id: string;
  name: string;
  model: string;
  fw_ver: string;
  auth_enabled: boolean;
}

export interface Circuit {
  id: string;
  site_id: string;
  name: string;
  kind: "device_merge" | "virtual";
  members: { channel_id: string; sign: 1 | -1 }[];
}

export interface LiveChannel {
  id: string;
  device_id: string;
  name: string;
  role: ChannelRole;
  power_w: number;
  voltage_v: number | null;
  day_kwh: number | null;
  day_ret_kwh: number | null;
}

export interface LiveSnapshot {
  site_id: string;
  ts: string | null;
  devices: { id: string; name: string; online: boolean }[];
  channels: LiveChannel[];
  circuits: { id: string; name: string; kind: string; power_w: number; channel_ids: string[] }[];
}

export interface ReadingPoint {
  ts: string;
  energy_kwh: number | null;
  ret_energy_kwh: number | null;
  power_avg_w: number | null;
  quality: "device" | "estimated";
}

export interface Series {
  series: string;
  name: string;
  kind: string;
  points: ReadingPoint[];
}

export const hasPerm = (me: Me | undefined, perm: string, siteId?: string): boolean =>
  !!me &&
  (me.global_permissions.includes(perm) ||
    (siteId !== undefined && (me.site_permissions[siteId] ?? []).includes(perm)));
