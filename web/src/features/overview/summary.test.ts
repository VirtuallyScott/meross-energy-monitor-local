import { describe, expect, it } from "vitest";

import type { LiveSnapshot } from "../../lib/types";
import { summarize } from "./summary";

const ch = (
  id: string,
  name: string,
  role: "grid_main" | "branch",
  power_w: number,
  day_kwh = 0,
) => ({
  id,
  name,
  role,
  power_w,
  device_id: "d",
  phase_label: null,
  voltage_v: 124,
  current_a: null,
  pf: null,
  day_kwh,
  day_ret_kwh: 0,
});

const snapshot: LiveSnapshot = {
  site_id: "s",
  ts: null,
  devices: [],
  channels: [
    ch("1", "Primary Phase A", "grid_main", 1500, 10),
    ch("7", "Primary Phase B", "grid_main", 1300, 9),
    ch("2", "Phase A Waterfall Pool Pump", "branch", 380),
    ch("8", "Phase B Waterfall Pool Pump", "branch", 380),
    ch("4", "A4", "branch", 100),
  ],
  circuits: [
    {
      id: "m",
      name: "Waterfall Pool Pump",
      kind: "device_merge",
      power_w: 760,
      channel_ids: ["2", "8"],
    },
  ],
};

describe("summarize", () => {
  it("adds mains for house power and today's energy", () => {
    const s = summarize(snapshot);
    expect(s.houseW).toBe(2800);
    expect(s.todayKwh).toBe(19);
  });

  it("uses merges instead of their halves and adds the unmetered remainder", () => {
    const names = summarize(snapshot).bars.map((b) => [b.name, b.watts]);
    expect(names).toEqual([
      ["Unmetered remainder", 1940],
      ["Waterfall Pool Pump", 760],
      ["A4", 100],
    ]);
  });

  it("reports no house figure when nothing is configured", () => {
    const s = summarize({
      ...snapshot,
      channels: snapshot.channels.filter((c) => c.role === "branch"),
    });
    expect(s.houseW).toBeNull();
    expect(s.bars.find((b) => b.kind === "unmetered")).toBeUndefined();
  });
});
