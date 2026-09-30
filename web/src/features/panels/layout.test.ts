import { describe, expect, it } from "vitest";

import type { Panel, PanelBreaker } from "../../lib/types";
import { breakerLabel, layoutPanel, legSpace, occupied, positionLabel } from "./layout";
import { NO_READING, type Reading } from "./readings";

const watts = (powerW: number): Reading => ({
  powerW,
  voltageV: 120,
  currentA: powerW / 120,
  currentEstimated: false,
});

const breaker = (over: Partial<PanelBreaker>): PanelBreaker => ({
  channel_id: "c1",
  channel_name: "Dryer",
  phase_label: "A1",
  device_id: "d1",
  device_name: "Garage EM16P",
  slot: 1,
  poles: 1,
  pole: 1,
  amps: null,
  ...over,
});

const panel = (over: Partial<Panel> = {}): Panel => ({
  id: "p1",
  site_id: "s1",
  name: "Main",
  spaces: 8,
  numbering: "odd_even",
  breakers: [],
  ...over,
});

describe("occupied (PNL-003)", () => {
  it("steps by two on odd/even panels", () => {
    expect(occupied(5, 2, "odd_even")).toEqual([5, 7]);
  });
  it("steps by one on sequential panels", () => {
    expect(occupied(5, 2, "sequential")).toEqual([5, 6]);
  });
});

describe("layoutPanel (PNL-006)", () => {
  it("places odd spaces left and even spaces right", () => {
    const { breakers } = layoutPanel(
      panel({ breakers: [breaker({ slot: 3 }), breaker({ channel_id: "c2", slot: 4 })] }),
      {},
    );
    expect(breakers.map((b) => [b.row, b.column])).toEqual([
      [1, 0],
      [1, 1],
    ]);
  });

  it("spans a double-pole breaker over two rows", () => {
    const { breakers } = layoutPanel(panel({ breakers: [breaker({ slot: 5, poles: 2 })] }), {});
    expect(breakers[0]).toMatchObject({ row: 2, column: 0, span: 2, spaces: [5, 7] });
  });

  it("puts each CT of a double-pole breaker on its own space and sums them", () => {
    const { breakers } = layoutPanel(
      panel({
        breakers: [
          breaker({ channel_id: "b2", phase_label: "B2", slot: 1, poles: 2, pole: 2 }),
          breaker({ channel_id: "a2", phase_label: "A2", slot: 1, poles: 2, pole: 1 }),
        ],
      }),
      { a2: watts(400), b2: watts(350) },
    );
    expect(breakers).toHaveLength(1);
    expect(breakers[0]?.reading.powerW).toBe(750);
    expect(breakers[0]?.reading.currentA).toBeCloseTo(400 / 120);
    expect(
      breakers[0]?.legs.map((l) => [l.space, l.channel?.phase_label, l.reading.powerW]),
    ).toEqual([
      [1, "A2", 400],
      [3, "B2", 350],
    ]);
  });

  it("shows a pole with no sensor as an empty leg", () => {
    const { breakers } = layoutPanel(
      panel({ breakers: [breaker({ slot: 5, poles: 2, pole: 1 })] }),
      { c1: watts(900) },
    );
    expect(breakers[0]?.legs[1]).toEqual({ pole: 2, space: 7, channel: null, reading: NO_READING });
  });

  it("reports no power when no channel has a live reading", () => {
    const { breakers } = layoutPanel(panel({ breakers: [breaker({})] }), {});
    expect(breakers[0]?.reading).toEqual(NO_READING);
  });

  it("lists the spaces no breaker covers", () => {
    const { empty } = layoutPanel(panel({ breakers: [breaker({ slot: 1, poles: 2 })] }), {});
    expect(empty.map((e) => e.slot)).toEqual([2, 4, 5, 6, 7, 8]);
  });

  it("uses left column then right column on sequential panels", () => {
    const { breakers } = layoutPanel(
      panel({ numbering: "sequential", breakers: [breaker({ slot: 5, poles: 2 })] }),
      {},
    );
    expect(breakers[0]).toMatchObject({ row: 0, column: 1, spaces: [5, 6] });
  });
});

describe("labels (PNL-005)", () => {
  it("describes a double-pole breaker with rating", () => {
    expect(breakerLabel({ spaces: [5, 7], poles: 2, amps: 30 })).toBe("5/7 · 2P 30 A");
  });
  it("describes a single-pole breaker without rating", () => {
    expect(breakerLabel({ spaces: [12], poles: 1, amps: null })).toBe("12 · 1P");
  });
  it("names the panel for a channel", () => {
    const panels = [panel()];
    expect(
      positionLabel({ panel_id: "p1", panel_slot: 5, breaker_poles: 2, breaker_amps: 30 }, panels),
    ).toBe("Main · 5/7 · 2P 30 A");
  });
  it("finds the space of the leg a channel reads", () => {
    const pos = { panel_id: "p1", panel_slot: 1, breaker_poles: 2, breaker_pole: 2 };
    expect(legSpace(pos, [panel()])).toBe(3);
    expect(legSpace({ ...pos, panel_id: null }, [panel()])).toBeNull();
  });
  it("shows a dash for a channel with no position", () => {
    expect(
      positionLabel(
        { panel_id: null, panel_slot: null, breaker_poles: null, breaker_amps: 20 },
        [],
      ),
    ).toBe("—");
  });
});
