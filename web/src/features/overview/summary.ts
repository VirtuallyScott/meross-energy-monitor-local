import type { LiveSnapshot, Site } from "../../lib/types";

export interface Bar {
  id: string;
  name: string;
  watts: number;
  kind: "circuit" | "channel" | "unmetered";
}

export interface Summary {
  houseW: number | null;
  todayKwh: number | null;
  exportW: number;
  bars: Bar[];
  source: string;
}

/** Whole-house power and the ranked load list (UI-001, UI-004, CIR-007). */
export function summarize(snapshot: LiveSnapshot, site?: Site): Summary {
  const mains = snapshot.channels.filter((c) => c.role === "grid_main");
  const branches = snapshot.channels.filter((c) => c.role === "branch");
  const loadCircuit = site?.load_circuit_id
    ? snapshot.circuits.find((c) => c.id === site.load_circuit_id)
    : undefined;

  let houseW: number | null = null;
  let source = "Not configured";
  if (loadCircuit) {
    houseW = loadCircuit.power_w;
    source = loadCircuit.name;
  } else if (mains.length) {
    houseW = mains.reduce((sum, c) => sum + c.power_w, 0);
    source = `${mains.length} mains channel${mains.length > 1 ? "s" : ""}`;
  }
  const todayKwh = mains.length ? mains.reduce((sum, c) => sum + (c.day_kwh ?? 0), 0) : null;
  const exportW = mains.reduce((sum, c) => sum + Math.min(0, c.power_w), 0);

  const circuitBars: Bar[] = snapshot.circuits
    .filter((c) => c.id !== site?.load_circuit_id && c.id !== site?.grid_circuit_id)
    .map((c) => ({ id: c.id, name: c.name, watts: c.power_w, kind: "circuit" as const }));
  // Channels inside a device merge are represented by the merge, not listed twice.
  const merged = new Set(
    snapshot.circuits.filter((c) => c.kind === "device_merge").flatMap((c) => c.channel_ids),
  );
  const channelBars: Bar[] = branches
    .filter((c) => !merged.has(c.id))
    .map((c) => ({ id: c.id, name: c.name, watts: c.power_w, kind: "channel" as const }));

  const bars = [...circuitBars, ...channelBars];
  if (houseW !== null && branches.length) {
    const metered = branches.reduce((sum, c) => sum + c.power_w, 0);
    bars.push({
      id: "unmetered",
      name: "Unmetered remainder",
      watts: houseW - metered,
      kind: "unmetered",
    });
  }
  bars.sort((a, b) => b.watts - a.watts);
  return { houseW, todayKwh, exportW, bars, source };
}
