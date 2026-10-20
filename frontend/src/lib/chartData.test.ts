import { pnlSeries } from "./chartData";

const sec = (iso: string) => Date.parse(iso) / 1000;

describe("pnlSeries", () => {
  const snapshots = [
    { total_value: 10000, recorded_at: "2026-10-18T14:00:00.000Z" },
    { total_value: 10005.5, recorded_at: "2026-10-18T14:00:30.000Z" },
  ];

  it("converts snapshots to unix-second points and appends the live total", () => {
    const now = sec("2026-10-18T14:01:00.000Z");
    expect(pnlSeries(snapshots, 10011.4, now)).toEqual([
      { time: sec("2026-10-18T14:00:00.000Z"), value: 10000 },
      { time: sec("2026-10-18T14:00:30.000Z"), value: 10005.5 },
      { time: now, value: 10011.4 },
    ]);
  });

  it("omits the live point when there is none or it isn't newer than the last snapshot", () => {
    expect(pnlSeries(snapshots, null, sec("2026-10-18T14:01:00.000Z"))).toHaveLength(2);
    expect(pnlSeries(snapshots, 10011.4, sec("2026-10-18T14:00:30.000Z"))).toHaveLength(2);
  });

  it("keeps times strictly ascending: same-second snapshots collapse to the later one", () => {
    const points = pnlSeries(
      [
        { total_value: 10000, recorded_at: "2026-10-18T14:00:00.100Z" },
        { total_value: 9990, recorded_at: "2026-10-18T14:00:00.900Z" },
        { total_value: 9980, recorded_at: "2026-10-18T14:00:01.000Z" },
      ],
      null,
    );
    expect(points).toEqual([
      { time: sec("2026-10-18T14:00:00.000Z"), value: 9990 },
      { time: sec("2026-10-18T14:00:01.000Z"), value: 9980 },
    ]);
  });

  it("is just the live point with no history", () => {
    expect(pnlSeries([], 10000, 1_000)).toEqual([{ time: 1_000, value: 10000 }]);
  });
});
