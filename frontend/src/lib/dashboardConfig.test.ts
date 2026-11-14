import { describe, expect, it } from "vitest";
import {
  cloneDashboardConfig,
  dashboardConfigsEqual,
  removeDashboardWidget,
  upsertDashboardWidget,
} from "@/lib/dashboardConfig";
import type { DashboardConfig, DashboardWidgetConfig } from "@/types";

const widget = (id: string, title = id): DashboardWidgetConfig => ({
  id,
  title,
  data_source: "transactions",
  data_spec: "analytics",
  query: {
    dimension: "category",
    metric: "sum",
    filters: { transaction_type: "expense", account_id: null },
    granularity: null,
  },
  visualization: { type: "pie", options: {} },
});

const initial: DashboardConfig = { schema_version: 1, widgets: [widget("saved")] };

describe("dashboard draft configuration", () => {
  it("clones saved state without sharing mutable nested data", () => {
    const draft = cloneDashboardConfig(initial);
    draft.widgets[0].query.filters.transaction_type = "income";
    expect(initial.widgets[0].query.filters.transaction_type).toBe("expense");
    expect(dashboardConfigsEqual(initial, draft)).toBe(false);
  });

  it("adds and edits widgets locally while preserving order", () => {
    const added = upsertDashboardWidget(initial, widget("new"));
    expect(added.widgets.map((item) => item.id)).toEqual(["saved", "new"]);
    const edited = upsertDashboardWidget(added, widget("saved", "Renamed"));
    expect(edited.widgets.map((item) => item.title)).toEqual(["Renamed", "new"]);
  });

  it("removes a widget locally and supports rollback to the saved copy", () => {
    const draft = removeDashboardWidget(initial, "saved");
    expect(draft.widgets).toEqual([]);
    expect(initial.widgets).toHaveLength(1);
    expect(cloneDashboardConfig(initial)).toEqual(initial);
  });
});
