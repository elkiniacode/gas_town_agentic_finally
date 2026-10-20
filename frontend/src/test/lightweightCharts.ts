// In-memory stand-in for `lightweight-charts` (jsdom has no canvas). Installed for every
// test by setup.ts; `charts` records each created chart so tests can inspect series data.
import type { LineData } from "lightweight-charts";

export class FakeSeries {
  data: LineData[] = [];
  options: Record<string, unknown> = {};
  setData = vi.fn((data: LineData[]) => {
    this.data = data;
  });
  applyOptions = vi.fn((opts: Record<string, unknown>) => {
    Object.assign(this.options, opts);
  });
}

export class FakeChart {
  series: FakeSeries[] = [];
  removed = false;
  fitContent = vi.fn();
  constructor(
    readonly container: HTMLElement,
    readonly options: unknown,
  ) {}
  addSeries = vi.fn((_type: unknown, opts: Record<string, unknown> = {}) => {
    const s = new FakeSeries();
    s.options = { ...opts };
    this.series.push(s);
    return s;
  });
  applyOptions = vi.fn();
  timeScale = () => ({ fitContent: this.fitContent });
  remove = vi.fn(() => {
    this.removed = true;
  });
}

export const charts: FakeChart[] = [];

/** The live (not removed) chart rendered into the element with `data-testid={testId}`. */
export function chartFor(testId: string): FakeChart {
  const chart = charts.find((c) => !c.removed && c.container.dataset.testid === testId);
  if (!chart) throw new Error(`no chart rendered into ${testId}`);
  return chart;
}

export const lightweightChartsMock = {
  createChart: (container: HTMLElement, options: unknown) => {
    const chart = new FakeChart(container, options);
    charts.push(chart);
    return chart;
  },
  LineSeries: { type: "Line" },
  ColorType: { Solid: "solid", VerticalGradient: "gradient" },
  TickMarkType: { Year: 0, Month: 1, DayOfMonth: 2, Time: 3, TimeWithSeconds: 4 },
};
