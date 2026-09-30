import type { CSSProperties } from "react";
import { Link } from "react-router-dom";

import { formatVoltage } from "../../lib/format";
import { type BreakerLeg, breakerLabel, type PlacedBreaker } from "./layout";
import { primaryReading, type Reading, type SlotMetric } from "./readings";

function legName(leg: BreakerLeg): string {
  return leg.channel ? (leg.channel.phase_label ?? leg.channel.channel_name) : "No sensor";
}

function spoken(reading: Reading, metric: SlotMetric): string {
  const main = primaryReading(reading, metric);
  const volts = formatVoltage(reading.voltageV);
  const estimated = metric === "amps" && reading.currentEstimated ? " estimated" : "";
  const value = `${main.value.replace("≈", "")} ${main.unit}${estimated}`;
  return reading.voltageV === null ? value : `${value} at ${volts.value} ${volts.unit}`;
}

function describe(breaker: PlacedBreaker, names: string, metric: SlotMetric): string {
  const where = `${breaker.poles > 1 ? "Spaces" : "Space"} ${breakerLabel(breaker)}`;
  if (breaker.poles === 1) return `${where}: ${names}, ${spoken(breaker.reading, metric)}`;
  const total = primaryReading(breaker.reading, metric);
  const label = metric === "amps" ? "highest pole" : "total";
  const legs = breaker.legs.map(
    (leg) =>
      `space ${leg.space} ${legName(leg)}${leg.channel ? ` ${spoken(leg.reading, metric)}` : ""}`,
  );
  return `${where}: ${names}, ${total.value.replace("≈", "")} ${total.unit} ${label}; ${legs.join("; ")}`;
}

/** Primary value (W or A) over the space's voltage (PNL-011). */
function SlotReading({ reading, metric }: { reading: Reading; metric: SlotMetric }) {
  const main = primaryReading(reading, metric);
  const volts = formatVoltage(reading.voltageV);
  return (
    <span className="slot-reading">
      <span
        className={`breaker-power num${main.live ? " is-live" : ""}`}
        title={metric === "amps" && reading.currentEstimated ? "Estimated from W ÷ V" : undefined}
      >
        {main.value}
        <span className="unit">{main.unit}</span>
      </span>
      <span className="slot-volts num">
        {volts.value}
        <span className="unit">{volts.unit}</span>
      </span>
    </span>
  );
}

export function BreakerCell({
  breaker,
  siteId,
  metric,
}: {
  breaker: PlacedBreaker;
  siteId: string;
  metric: SlotMetric;
}) {
  const names = [...new Set(breaker.channels.map((c) => c.channel_name))].join(" + ");
  const multi = breaker.poles > 1;
  const total = primaryReading(breaker.reading, metric);
  const totalLabel = metric === "amps" ? "peak" : "total";
  const style = {
    gridRow: `${breaker.row + 1} / span ${breaker.span}`,
    gridColumn: breaker.column === 0 ? 2 : 4,
  };
  return (
    <li className={`breaker side-${breaker.column}`} style={style}>
      <Link
        to={`/s/${siteId}/devices/${breaker.deviceId}`}
        aria-label={describe(breaker, names, metric)}
      >
        <span className="breaker-handle" aria-hidden="true" data-poles={breaker.poles} />
        <span className="breaker-body">
          <span className="breaker-name">{names}</span>
          <span className="breaker-meta">
            {breakerLabel(breaker)} ·{" "}
            {multi ? `${total.value} ${total.unit} ${totalLabel}` : breaker.deviceName}
          </span>
        </span>
        {multi ? (
          <span className="breaker-legs" style={{ "--poles": breaker.poles } as CSSProperties}>
            {breaker.legs.map((leg) => (
              <LegReading key={leg.pole} leg={leg} metric={metric} />
            ))}
          </span>
        ) : (
          <SlotReading reading={breaker.reading} metric={metric} />
        )}
      </Link>
    </li>
  );
}

/** One pole's own reading, level with its space, so an unbalanced 240 V load is visible. */
function LegReading({ leg, metric }: { leg: BreakerLeg; metric: SlotMetric }) {
  return (
    <span className={`breaker-leg${leg.channel ? "" : " is-empty"}`}>
      <span className="leg-name">{legName(leg)}</span>
      {leg.channel && <SlotReading reading={leg.reading} metric={metric} />}
    </span>
  );
}
