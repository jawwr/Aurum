import {beforeEach, describe, expect, it} from "vitest";
import {ShoppingBasket, Wallet} from "lucide-react";
import {setLanguage} from "@/lib/i18n";
import {buildListRows, formatListValue} from "@/components/dashboard/WidgetListBody";
import type {DiagramPoint, WidgetMetric} from "@/types";

function point(overrides: Partial<DiagramPoint>): DiagramPoint {
  return {
    label: "Row",
    value: "1",
    color: null,
    element_id: null,
    key: "item:1",
    icon: null,
    time_bucket: null,
    series_key: null,
    ...overrides,
  };
}

describe("formatListValue", () => {
  beforeEach(() => setLanguage("en"));

  it("formats sum rows through the shared currency formatter", () => {
    expect(formatListValue(614, "sum")).toBe("+$614");
    expect(formatListValue(-30, "sum")).toBe("-$30");
    expect(formatListValue(0, "sum")).toBe("$0");
  });

  it("renders count rows as a whole number", () => {
    expect(formatListValue(3, "count")).toBe("3");
    expect(formatListValue(7.0, "count")).toBe("7");
  });
});

describe("buildListRows", () => {
  beforeEach(() => setLanguage("en"));

  const points: DiagramPoint[] = [
    point({ key: "category:7", label: "Groceries", value: "125.00", icon: "shopping-basket", color: "#1baf7a" }),
    point({ key: "tag:2", label: "Trips", value: "40" }),
    point({ key: "diagram:other", label: "Other", value: "9", icon: "unknown-glyph", color: "#898781" }),
  ];

  it("builds one row per point, in the order the backend returned them", () => {
    // The backend's ListDiagram already applied the widget's sort and
    // limit — a "none" sort must surface the DataSource's own order, so
    // buildListRows must not reorder even though the values would sort
    // differently.
    const rows = buildListRows(points, "sum");
    expect(rows.map((row) => row.key)).toEqual(["category:7", "tag:2", "diagram:other"]);
    expect(rows.map((row) => row.label)).toEqual(["Groceries", "Trips", "Other"]);
  });

  it("resolves icons through getCategoryIcon with its Wallet fallback", () => {
    const rows = buildListRows(points, "sum");
    expect(rows[0].icon).toBe(ShoppingBasket); // a known icon key
    expect(rows[1].icon).toBe(Wallet); // no icon at all
    expect(rows[2].icon).toBe(Wallet); // an icon key lucide doesn't map
  });

  it("keeps entity colors and falls back to the muted text tone without one", () => {
    const rows = buildListRows(points, "sum");
    expect(rows[0].color).toBe("#1baf7a");
    expect(rows[1].color).toBe("var(--text-muted)");
  });

  it("colors values by sign", () => {
    const rows = buildListRows([
      point({ key: "negative", value: "-30000" }),
      point({ key: "positive", value: "25" }),
      point({ key: "zero", value: "0" }),
    ], "sum");
    expect(rows.map((row) => row.valueColor)).toEqual([
      "var(--danger)", "var(--success)", "var(--text-muted)",
    ]);
  });

  it("formats each row's value by the widget's metric", () => {
    const sumRows = buildListRows(points, "sum" as WidgetMetric);
    expect(sumRows[0].formattedValue).toBe("+$125");
    const countRows = buildListRows(
      points.map((p) => ({ ...p, value: "3" })),
      "count",
    );
    expect(countRows.every((row) => row.formattedValue === "3")).toBe(true);
  });
});
