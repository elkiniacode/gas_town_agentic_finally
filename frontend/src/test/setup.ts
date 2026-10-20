import "@testing-library/jest-dom/vitest";
import { charts } from "./lightweightCharts";

// jsdom has no canvas: every test renders charts into the recording fake.
vi.mock("lightweight-charts", async () => (await import("./lightweightCharts")).lightweightChartsMock);

afterEach(() => {
  charts.length = 0;
});
