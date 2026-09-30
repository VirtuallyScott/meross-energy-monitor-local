import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { useParams, useSearchParams } from "react-router-dom";

import { Alert, Panel, Select } from "../../components/ui";
import { api, errorMessage } from "../../lib/api";
import { formatKwh } from "../../lib/format";
import { useCircuits, useDevices, useSites } from "../../lib/queries";
import type { Series } from "../../lib/types";
import { scale } from "./chart";
import "./history.css";

const RANGES = [
  { key: "24h", label: "24 hours", ms: 86_400_000, resolution: "15m" },
  { key: "7d", label: "7 days", ms: 7 * 86_400_000, resolution: "hour" },
  { key: "30d", label: "30 days", ms: 30 * 86_400_000, resolution: "day" },
] as const;
const W = 900;
const H = 280;

export function HistoryPage() {
  const { siteId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const { data: sites } = useSites();
  const { data: circuits = [] } = useCircuits(siteId);
  const { data: devices = [] } = useDevices(siteId);
  const tz = sites?.find((s) => s.id === siteId)?.time_zone;

  const range = RANGES.find((r) => r.key === params.get("range")) ?? RANGES[0];
  const metric = params.get("metric") === "energy" ? "energy" : "power";
  const series = params.get("series") ?? (circuits[0] ? `circuit:${circuits[0].id}` : "");
  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    next.set(key, value);
    setParams(next, { replace: true });
  };

  const options = useMemo(() => {
    const list = circuits.map((c) => ({ value: `circuit:${c.id}`, label: `${c.name} (circuit)` }));
    for (const device of devices) {
      // Channels come from the device detail endpoint; the list endpoint omits them.
      for (const ch of device.channels ?? []) {
        if (ch.visible && ch.role !== "unused")
          list.push({ value: `channel:${ch.id}`, label: ch.name });
      }
    }
    return list;
  }, [circuits, devices]);

  // Bucket the window to the minute so the query key is stable between renders.
  const end = Math.floor(Date.now() / 60_000) * 60_000;
  const start = end - range.ms;
  const [kind, id] = series.split(":");
  const readings = useQuery({
    enabled: !!id,
    queryKey: ["readings", series, range.key, Math.floor(end / 300_000)],
    queryFn: () =>
      api<Series[]>(
        `/readings?${kind === "circuit" ? "circuits" : "channels"}=${id}` +
          `&from=${new Date(start).toISOString()}&to=${new Date(end).toISOString()}` +
          `&resolution=${range.resolution}`,
      ),
  });

  const points = (readings.data?.[0]?.points ?? []).map((p) => ({
    t: Date.parse(p.ts),
    v: (metric === "power" ? p.power_avg_w : p.energy_kwh) ?? 0,
  }));
  const geo = scale(points, W, H);
  const total = readings.data?.[0]?.points.reduce((s, p) => s + (p.energy_kwh ?? 0), 0);
  const fmtTime = (t: number) =>
    new Intl.DateTimeFormat(undefined, {
      timeZone: tz,
      ...(range.key === "24h"
        ? { hour: "2-digit", minute: "2-digit" }
        : { month: "short", day: "numeric" }),
    }).format(t);

  return (
    <div className="history">
      <Panel title="History" eyebrow={tz ? `Times in ${tz}` : undefined}>
        <div className="history-controls">
          <Select
            label="Circuit or channel"
            value={series}
            onChange={(e) => setParam("series", e.target.value)}
          >
            {options.length === 0 && <option value="">No circuits yet</option>}
            {options.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
          <fieldset className="segmented">
            <legend>Range</legend>
            {RANGES.map((r) => (
              <button
                key={r.key}
                type="button"
                aria-pressed={r.key === range.key}
                onClick={() => setParam("range", r.key)}
              >
                {r.label}
              </button>
            ))}
          </fieldset>
          <fieldset className="segmented">
            <legend>Show</legend>
            {(["power", "energy"] as const).map((m) => (
              <button
                key={m}
                type="button"
                aria-pressed={m === metric}
                onClick={() => setParam("metric", m)}
              >
                {m === "power" ? "Avg power (W)" : "Energy (kWh)"}
              </button>
            ))}
          </fieldset>
        </div>

        {readings.isError && <Alert>{errorMessage(readings.error)}</Alert>}
        {total !== undefined && (
          <p className="history-total">
            <span className="eyebrow">Energy in range</span>{" "}
            <strong className="num">{formatKwh(total)} kWh</strong>
          </p>
        )}
        {!geo && !readings.isLoading && <p>No data in this range yet.</p>}
        {geo && (
          <figure className="chart">
            <svg
              viewBox={`-56 -12 ${W + 72} ${H + 40}`}
              role="img"
              aria-label={`${metric === "power" ? "Average power" : "Energy"} over ${range.label}`}
            >
              {geo.yTicks.map((tick) => (
                <g key={tick.y}>
                  <line x1={0} x2={W} y1={tick.y} y2={tick.y} className="grid" />
                  <text x={-10} y={tick.y + 4} textAnchor="end" className="tick">
                    {metric === "power" ? Math.round(tick.label) : tick.label.toFixed(2)}
                  </text>
                </g>
              ))}
              {geo.xTicks.map((tick) => (
                <text key={tick.t} x={tick.x} y={H + 24} textAnchor="middle" className="tick">
                  {fmtTime(tick.t)}
                </text>
              ))}
              <path d={geo.area} className="area" />
              <path d={geo.path} className="line" />
            </svg>
            <figcaption className="visually-hidden">
              <table>
                <thead>
                  <tr>
                    <th>Time</th>
                    <th>{metric === "power" ? "Average W" : "kWh"}</th>
                  </tr>
                </thead>
                <tbody>
                  {points.map((p) => (
                    <tr key={p.t}>
                      <td>{new Date(p.t).toISOString()}</td>
                      <td>{p.v}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </figcaption>
          </figure>
        )}
      </Panel>
    </div>
  );
}
