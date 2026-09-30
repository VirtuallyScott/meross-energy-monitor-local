import { describe, expect, it } from "vitest";

import type { LiveChannel, Panel, PanelBreaker } from "../../lib/types";
import {
  combine,
  mainsTotal,
  NO_READING,
  panelMains,
  parseMetric,
  primaryReading,
  readingsById,
  toReading,
} from "./readings";

const live = (over: Partial<LiveChannel>): LiveChannel => ({
  id: "c1",
  device_id: "d1",
  name: "Dryer",
  phase_label: "A2",
  role: "branch",
  power_w: 600,
  voltage_v: 120,
  current_a: 5.1,
  pf: 0.98,
  day_kwh: 1.5,
  day_ret_kwh: 0,
  ...over,
});

const placed = (over: Partial<PanelBreaker>): PanelBreaker => ({
  channel_id: "c1",
  channel_name: "Dryer",
  phase_label: "A2",
  device_id: "d1",
  device_name: "Garage EM16P",
  slot: 1,
  poles: 1,
  pole: 1,
  amps: null,
  ...over,
});

const panel = (breakers: PanelBreaker[]): Panel => ({
  id: "p1",
  site_id: "s1",
  name: "Main",
  spaces: 8,
  numbering: "odd_even",
  breakers,
});

describe("toReading (PNL-011)", () => {
  it("uses the device's measured current", () => {
    expect(toReading(live({}))).toEqual({
      powerW: 600,
      voltageV: 120,
      currentA: 5.1,
      currentEstimated: false,
    });
  });

  it("derives current from W / V when the device reports none", () => {
    const reading = toReading(live({ current_a: null, power_w: 600, voltage_v: 120 }));
    expect(reading.currentA).toBe(5);
    expect(reading.currentEstimated).toBe(true);
  });

  it("uses magnitude for export when deriving current", () => {
    expect(toReading(live({ current_a: null, power_w: -240, voltage_v: 120 })).currentA).toBe(2);
  });

  it("leaves current unknown with no voltage reference", () => {
    const reading = toReading(live({ current_a: null, voltage_v: 0.09 }));
    expect(reading.currentA).toBeNull();
    expect(reading.currentEstimated).toBe(false);
  });

  it("indexes live channels by id", () => {
    const byId = readingsById([live({ id: "a" }), live({ id: "b", power_w: 10 })]);
    expect(byId.b?.powerW).toBe(10);
  });
});

describe("combine (PNL-011)", () => {
  it("sums power and takes the highest pole current", () => {
    const total = combine([
      { powerW: 400, voltageV: 121, currentA: 3.3, currentEstimated: false },
      { powerW: 350, voltageV: 122, currentA: 2.9, currentEstimated: true },
    ]);
    expect(total).toEqual({ powerW: 750, voltageV: null, currentA: 3.3, currentEstimated: false });
  });

  it("marks the total estimated only when the highest pole's current is estimated", () => {
    const total = combine([
      { powerW: 400, voltageV: 121, currentA: 3.3, currentEstimated: true },
      { powerW: 350, voltageV: 122, currentA: 2.9, currentEstimated: false },
    ]);
    expect(total.currentEstimated).toBe(true);
  });

  it("keeps a single pole's voltage", () => {
    const one = { powerW: 5, voltageV: 120, currentA: 0.1, currentEstimated: false };
    expect(combine([one])).toEqual(one);
  });

  it("stays unknown when no pole has a reading", () => {
    expect(combine([NO_READING, NO_READING])).toEqual(NO_READING);
  });
});

describe("primaryReading (PNL-011)", () => {
  const reading = { powerW: 1500, voltageV: 120, currentA: 12.5, currentEstimated: false };
  it("shows power in watts mode", () =>
    expect(primaryReading(reading, "watts")).toEqual({ value: "1.50", unit: "kW", live: true }));
  it("shows current in amps mode", () =>
    expect(primaryReading(reading, "amps")).toEqual({ value: "12.5", unit: "A", live: true }));
  it("marks derived current as estimated", () =>
    expect(primaryReading({ ...reading, currentEstimated: true }, "amps").value).toBe("≈12.5"));
  it("dashes a missing reading and is not live", () =>
    expect(primaryReading(NO_READING, "amps")).toEqual({ value: "—", unit: "A", live: false }));
});

describe("parseMetric", () => {
  it("reads amps from the URL", () => expect(parseMetric("amps")).toBe("amps"));
  it("defaults to watts", () => {
    expect(parseMetric(null)).toBe("watts");
    expect(parseMetric("volts")).toBe("watts");
  });
});

describe("panelMains (PNL-010)", () => {
  const a1 = live({ id: "a1", phase_label: "A1", role: "grid_main", device_id: "d1" });
  const b1 = live({ id: "b1", phase_label: "B1", role: "grid_main", device_id: "d1" });
  const other = live({ id: "x1", phase_label: "A1", role: "grid_main", device_id: "d2" });
  const branch = live({ id: "c1", role: "branch", device_id: "d1" });

  it("takes grid_main channels of devices with a sensor on the panel, A before B", () => {
    const mains = panelMains(panel([placed({ device_id: "d1" })]), [b1, branch, other, a1]);
    expect(mains.map((m) => m.id)).toEqual(["a1", "b1"]);
  });

  it("falls back to every grid_main channel in the site when nothing is placed", () => {
    expect(panelMains(panel([]), [b1, other, a1]).map((m) => m.id)).toEqual(["a1", "x1", "b1"]);
  });

  it("totals power and today's energy", () => {
    const total = mainsTotal([
      live({ power_w: 1500, day_kwh: 10 }),
      live({ power_w: 1300, day_kwh: null }),
    ]);
    expect(total).toEqual({ powerW: 2800, dayKwh: 10 });
  });

  it("has no total with no mains", () =>
    expect(mainsTotal([])).toEqual({ powerW: null, dayKwh: null }));
});
