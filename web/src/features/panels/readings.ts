/** Live readings for the panel view: mains strip (PNL-010) and per-space values (PNL-011). */

import { formatCurrent, formatPower } from "../../lib/format";
import type { LiveChannel, Panel } from "../../lib/types";

/** What each space shows beside its voltage, kept in the URL as `?show=`. */
export type SlotMetric = "watts" | "amps";

export interface Reading {
  powerW: number | null;
  voltageV: number | null;
  currentA: number | null;
  /** True when current was derived as W / V instead of measured. */
  currentEstimated: boolean;
}

export const NO_READING: Reading = {
  powerW: null,
  voltageV: null,
  currentA: null,
  currentEstimated: false,
};

/** Below this there is no phase reference to derive current from (matches the backend). */
const MIN_REFERENCE_VOLTAGE_V = 5;

export const parseMetric = (value: string | null): SlotMetric =>
  value === "amps" ? "amps" : "watts";

export function toReading(channel: LiveChannel): Reading {
  const volts = channel.voltage_v;
  if (channel.current_a !== null) {
    return {
      powerW: channel.power_w,
      voltageV: volts,
      currentA: channel.current_a,
      currentEstimated: false,
    };
  }
  const canDerive = volts !== null && volts >= MIN_REFERENCE_VOLTAGE_V;
  return {
    powerW: channel.power_w,
    voltageV: volts,
    currentA: canDerive ? Math.abs(channel.power_w) / volts : null,
    currentEstimated: canDerive,
  };
}

export const readingsById = (channels: LiveChannel[]): Record<string, Reading> =>
  Object.fromEntries(channels.map((c) => [c.id, toReading(c)]));

const known = (values: (number | null)[]): number[] =>
  values.filter((v): v is number => v !== null);

/**
 * A breaker's total from its poles. Power adds; current does not, since a 240 V load's
 * current flows through both poles, so the highest pole current stands for the breaker.
 */
export function combine(poles: Reading[]): Reading {
  if (poles.length === 1 && poles[0]) return poles[0];
  const watts = known(poles.map((p) => p.powerW));
  const peak = poles.reduce<Reading | null>(
    (best, p) =>
      p.currentA !== null && (best?.currentA == null || p.currentA > best.currentA) ? p : best,
    null,
  );
  return {
    powerW: watts.length ? watts.reduce((sum, w) => sum + w, 0) : null,
    voltageV: null,
    currentA: peak?.currentA ?? null,
    currentEstimated: peak?.currentEstimated ?? false,
  };
}

/** The value shown beside the voltage, in the viewer's chosen unit. */
export function primaryReading(
  reading: Reading,
  metric: SlotMetric,
): { value: string; unit: string; live: boolean } {
  if (metric === "watts") {
    const power = formatPower(reading.powerW);
    return { ...power, live: !!reading.powerW };
  }
  const current = formatCurrent(reading.currentA);
  const value =
    reading.currentEstimated && reading.currentA !== null ? `≈${current.value}` : current.value;
  return { value, unit: current.unit, live: !!reading.currentA };
}

/**
 * The panel's mains (PNL-010): `grid_main` channels of devices with a sensor on this panel,
 * or every `grid_main` channel in the site while the panel has none placed. A1 before B1.
 */
export function panelMains(panel: Panel, channels: LiveChannel[]): LiveChannel[] {
  const devices = new Set(panel.breakers.map((b) => b.device_id));
  return channels
    .filter((c) => c.role === "grid_main" && (devices.size === 0 || devices.has(c.device_id)))
    .sort(
      (a, b) =>
        (a.phase_label ?? "").localeCompare(b.phase_label ?? "") ||
        a.device_id.localeCompare(b.device_id) ||
        a.name.localeCompare(b.name),
    );
}

export function mainsTotal(mains: LiveChannel[]): { powerW: number | null; dayKwh: number | null } {
  if (!mains.length) return { powerW: null, dayKwh: null };
  const kwh = known(mains.map((m) => m.day_kwh));
  return {
    powerW: mains.reduce((sum, m) => sum + m.power_w, 0),
    dayKwh: kwh.length ? kwh.reduce((sum, k) => sum + k, 0) : null,
  };
}
