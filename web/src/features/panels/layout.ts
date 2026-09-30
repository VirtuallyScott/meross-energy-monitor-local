/** Panel space geometry for the panel view (PNL-003, PNL-006). Mirrors app/panels/layout.py. */

import type { Channel, Panel, PanelBreaker, PanelNumbering } from "../../lib/types";
import { combine, NO_READING, type Reading } from "./readings";

/** One pole of a breaker: its space and the sensor reading it, if any. */
export interface BreakerLeg {
  pole: number;
  space: number;
  channel: PanelBreaker | null;
  reading: Reading;
}

export interface PlacedBreaker {
  key: string;
  slot: number;
  poles: number;
  amps: number | null;
  spaces: number[];
  row: number;
  column: 0 | 1;
  span: number;
  deviceId: string;
  deviceName: string;
  channels: PanelBreaker[];
  legs: BreakerLeg[];
  /** Summed power, highest pole current (PNL-011). */
  reading: Reading;
}

export interface EmptySpace {
  slot: number;
  row: number;
  column: 0 | 1;
}

export const occupied = (slot: number, poles: number, numbering: PanelNumbering): number[] =>
  Array.from({ length: poles }, (_, i) => slot + i * (numbering === "odd_even" ? 2 : 1));

function gridPosition(slot: number, spaces: number, numbering: PanelNumbering) {
  if (numbering === "odd_even") {
    return { row: Math.floor((slot - 1) / 2), column: ((slot - 1) % 2) as 0 | 1 };
  }
  const half = spaces / 2;
  return { row: (slot - 1) % half, column: Math.floor((slot - 1) / half) as 0 | 1 };
}

/** Group channels into breakers (two CTs can share one) and place them on the grid. */
export function layoutPanel(
  panel: Panel,
  live: Record<string, Reading | undefined>,
): { breakers: PlacedBreaker[]; empty: EmptySpace[] } {
  const groups = new Map<string, { first: PanelBreaker; channels: PanelBreaker[] }>();
  for (const b of panel.breakers) {
    const key = `${b.slot}:${b.poles}`;
    const group = groups.get(key);
    groups.set(key, { first: group?.first ?? b, channels: [...(group?.channels ?? []), b] });
  }

  const breakers = [...groups.entries()].map(([key, { first, channels }]): PlacedBreaker => {
    const spaces = occupied(first.slot, first.poles, panel.numbering);
    const legs = spaces.map((space, i): BreakerLeg => {
      const channel = channels.find((c) => c.pole === i + 1) ?? null;
      return {
        pole: i + 1,
        space,
        channel,
        reading: channel ? (live[channel.channel_id] ?? NO_READING) : NO_READING,
      };
    });
    return {
      key,
      slot: first.slot,
      poles: first.poles,
      amps: channels.find((c) => c.amps !== null)?.amps ?? null,
      spaces,
      ...gridPosition(first.slot, panel.spaces, panel.numbering),
      span: first.poles,
      deviceId: first.device_id,
      deviceName: first.device_name,
      channels,
      legs,
      reading: combine(legs.filter((l) => l.channel).map((l) => l.reading)),
    };
  });

  const taken = new Set(breakers.flatMap((b) => b.spaces));
  const empty = Array.from({ length: panel.spaces }, (_, i) => i + 1)
    .filter((slot) => !taken.has(slot))
    .map((slot) => ({ slot, ...gridPosition(slot, panel.spaces, panel.numbering) }));

  return { breakers, empty };
}

export function breakerLabel(b: { spaces: number[]; poles: number; amps: number | null }): string {
  const rating = b.amps === null ? "" : ` ${b.amps} A`;
  return `${b.spaces.join("/")} · ${b.poles}P${rating}`;
}

type Position = Pick<Channel, "panel_id" | "panel_slot" | "breaker_poles" | "breaker_amps">;
type LegPosition = Pick<Channel, "panel_id" | "panel_slot" | "breaker_poles" | "breaker_pole">;

/** For example "Main · 5/7 · 2P 30 A" (PNL-005). */
export function positionLabel(channel: Position, panels: Panel[]): string {
  const panel = panels.find((p) => p.id === channel.panel_id);
  if (!panel || channel.panel_slot === null) return "—";
  const poles = channel.breaker_poles ?? 1;
  const spaces = occupied(channel.panel_slot, poles, panel.numbering);
  return `${panel.name} · ${breakerLabel({ spaces, poles, amps: channel.breaker_amps })}`;
}

/** The space this channel's CT sits on, for multi-pole breakers (PNL-002). */
export function legSpace(channel: LegPosition, panels: Panel[]): number | null {
  const panel = panels.find((p) => p.id === channel.panel_id);
  if (!panel || channel.panel_slot === null) return null;
  const spaces = occupied(channel.panel_slot, channel.breaker_poles ?? 1, panel.numbering);
  return spaces[(channel.breaker_pole ?? 1) - 1] ?? null;
}
