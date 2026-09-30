/** Number and time formatting. Units are always explicit (NFR-022). */

export function formatPower(watts: number | null | undefined): { value: string; unit: string } {
  if (watts === null || watts === undefined || Number.isNaN(watts))
    return { value: "—", unit: "W" };
  const abs = Math.abs(watts);
  if (abs >= 10_000) return { value: (watts / 1000).toFixed(1), unit: "kW" };
  if (abs >= 1_000) return { value: (watts / 1000).toFixed(2), unit: "kW" };
  return { value: Math.round(watts).toString(), unit: "W" };
}

const DASH = "—";

export function formatVoltage(volts: number | null | undefined): { value: string; unit: string } {
  if (volts === null || volts === undefined || Number.isNaN(volts))
    return { value: DASH, unit: "V" };
  return { value: volts.toFixed(1), unit: "V" };
}

export function formatCurrent(amps: number | null | undefined): { value: string; unit: string } {
  if (amps === null || amps === undefined || Number.isNaN(amps)) return { value: DASH, unit: "A" };
  return { value: amps.toFixed(Math.abs(amps) >= 10 ? 1 : 2), unit: "A" };
}

export function formatKwh(kwh: number | null | undefined, digits = 2): string {
  if (kwh === null || kwh === undefined || Number.isNaN(kwh)) return "—";
  return kwh.toFixed(digits);
}

export function relativeTime(iso: string | null, now: number = Date.now()): string {
  if (!iso) return "never";
  const seconds = Math.round((now - new Date(iso).getTime()) / 1000);
  if (seconds < 5) return "just now";
  if (seconds < 90) return `${seconds}s ago`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 90) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 36) return `${hours} h ago`;
  return `${Math.round(hours / 24)} d ago`;
}

export function formatUptime(seconds: number | null): string {
  if (seconds === null) return "—";
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  return d > 0 ? `${d}d ${h}h` : `${h}h ${Math.floor((seconds % 3600) / 60)}m`;
}
