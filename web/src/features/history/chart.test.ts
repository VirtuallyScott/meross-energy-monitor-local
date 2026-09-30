import { describe, expect, it } from "vitest";

import { niceMax, scale } from "./chart";

describe("niceMax", () => {
  it.each([
    [0, 1],
    [3.2, 5],
    [2857, 5000],
    [180, 200],
    [1000, 1000],
  ])("%d -> %d", (input, expected) => expect(niceMax(input)).toBe(expected));
});

describe("scale", () => {
  it("needs two points", () => expect(scale([{ t: 0, v: 1 }], 100, 50)).toBeNull());

  it("maps first and last points to the edges", () => {
    const s = scale(
      [
        { t: 0, v: 0 },
        { t: 10, v: 100 },
      ],
      200,
      100,
    );
    if (!s) throw new Error("expected a scaled chart");
    expect(s.path).toBe("M0.0,100.0L200.0,0.0");
    expect(s.yTicks[0]).toEqual({ y: 100, label: 0 });
    expect(s.xTicks.at(-1)?.x).toBe(200);
  });
});
