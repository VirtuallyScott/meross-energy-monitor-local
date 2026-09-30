/** Pure geometry for the history chart, kept separate so it is unit-testable. */

export interface Point {
  t: number;
  v: number;
}

export interface Scaled {
  path: string;
  area: string;
  yTicks: { y: number; label: number }[];
  xTicks: { x: number; t: number }[];
  max: number;
}

export function niceMax(value: number): number {
  if (value <= 0) return 1;
  const exp = 10 ** Math.floor(Math.log10(value));
  const step = [1, 2, 2.5, 5, 10].find((s) => s * exp >= value) ?? 10;
  return step * exp;
}

export function scale(points: Point[], width: number, height: number, ticks = 4): Scaled | null {
  const first = points[0];
  const last = points[points.length - 1];
  if (points.length < 2 || !first || !last) return null;
  const t0 = first.t;
  const t1 = last.t;
  const max = niceMax(Math.max(...points.map((p) => p.v)));
  const min = Math.min(0, ...points.map((p) => p.v));
  const span = t1 - t0 || 1;
  const x = (t: number) => ((t - t0) / span) * width;
  const y = (v: number) => height - ((v - min) / (max - min || 1)) * height;
  const coords = points.map((p) => `${x(p.t).toFixed(1)},${y(p.v).toFixed(1)}`);
  const path = `M${coords.join("L")}`;
  const area = `${path}L${width},${y(0).toFixed(1)}L0,${y(0).toFixed(1)}Z`;
  const yTicks = Array.from({ length: ticks + 1 }, (_, i) => {
    const label = min + ((max - min) * i) / ticks;
    return { y: y(label), label };
  });
  const xTicks = Array.from({ length: ticks + 1 }, (_, i) => {
    const t = t0 + (span * i) / ticks;
    return { x: x(t), t };
  });
  return { path, area, yTicks, xTicks, max };
}
