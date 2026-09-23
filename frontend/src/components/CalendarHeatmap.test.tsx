import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { CalendarHeatmap } from "./CalendarHeatmap";

describe("CalendarHeatmap", () => {
  it("renders a separate icon without text for every sleep highlight", () => {
    const markup = renderToStaticMarkup(
      <CalendarHeatmap
        scope="month"
        period="2026-09"
        variant="sleep"
        data={[{
          date: "2026-09-03",
          value: 9,
          detail: "9 小时；睡得最久、最早入睡、最早起床",
          awards: ["longest", "earliest-sleep", "earliest-wake"],
        }]}
      />,
    );

    expect(markup).toContain("heat-award-longest");
    expect(markup).toContain("heat-award-earliest-sleep");
    expect(markup).toContain("heat-award-earliest-wake");
    expect(markup).not.toContain(">久<");
    expect(markup).not.toContain(">睡<");
    expect(markup).not.toContain(">起<");
  });

  it("renders the daily count when a special sport record appears more than once", () => {
    const markup = renderToStaticMarkup(
      <CalendarHeatmap
        scope="month"
        period="2026-09"
        variant="sport"
        data={[{
          date: "2026-09-03",
          value: 36,
          detail: "36 分钟，7 条记录，3 个 2 分钟标记，4 个 30 分钟标记",
          marker: true,
          markerCount: 3,
          yellowMarker: true,
          yellowMarkerCount: 4,
        }]}
      />,
    );

    expect(markup).toMatch(/heat-marker-red[^]*?heat-marker-box">2<\/span><span class="heat-marker-count">×3<\/span>/);
    expect(markup).toMatch(/heat-marker-yellow[^]*?heat-marker-box">30<\/span><span class="heat-marker-count">×4<\/span>/);
  });
});
