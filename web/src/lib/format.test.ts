import { describe, expect, it } from "vitest";

import { formatKwh, formatPower, formatUptime, relativeTime } from "./format";

describe("formatPower", () => {
  it("uses W below 1 kW", () => expect(formatPower(842.6)).toEqual({ value: "843", unit: "W" }));
  it("uses kW with 2 decimals from 1 kW", () =>
    expect(formatPower(2857.4)).toEqual({ value: "2.86", unit: "kW" }));
  it("uses 1 decimal from 10 kW", () =>
    expect(formatPower(12345)).toEqual({ value: "12.3", unit: "kW" }));
  it("keeps sign for export", () => expect(formatPower(-1500).value).toBe("-1.50"));
  it("shows a dash for missing data", () => expect(formatPower(null).value).toBe("—"));
});

describe("formatKwh", () => {
  it("rounds", () => expect(formatKwh(28.2591)).toBe("28.26"));
  it("dashes missing", () => expect(formatKwh(undefined)).toBe("—"));
});

describe("relativeTime", () => {
  const now = Date.parse("2026-09-29T12:00:00Z");
  it("handles never", () => expect(relativeTime(null, now)).toBe("never"));
  it("seconds", () => expect(relativeTime("2026-09-29T11:59:30Z", now)).toBe("30s ago"));
  it("minutes", () => expect(relativeTime("2026-09-29T11:00:00Z", now)).toBe("60 min ago"));
});

describe("formatUptime", () => {
  it("days and hours", () => expect(formatUptime(116_640)).toBe("1d 8h"));
  it("hours and minutes", () => expect(formatUptime(28_063)).toBe("7h 47m"));
});
