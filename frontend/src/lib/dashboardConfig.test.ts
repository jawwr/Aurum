import { describe, expect, it } from "vitest";
import {
  buildVisualizationOptions,
  cloneDashboardConfig,
  dashboardConfigsEqual,
  DEFAULT_LIST_LIMIT,
  DEFAULT_LIST_SORT,
  readListOptions,
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

describe("list widget visualization options", () => {
  it("saves sort and limit for list widgets, filling in the defaults", () => {
    expect(buildVisualizationOptions({ type: "list", sort: "value_desc", limit: 3 })).toEqual({
      sort: "value_desc",
      limit: 3,
    });
    expect(buildVisualizationOptions({ type: "list", sort: "value_asc", limit: 12 })).toEqual({
      sort: "value_asc",
      limit: 12,
    });
    expect(buildVisualizationOptions({ type: "list", sort: null, limit: null })).toEqual({
      sort: DEFAULT_LIST_SORT,
      limit: DEFAULT_LIST_LIMIT,
    });
  });

  it("keeps chart-type widgets on the empty options object they always saved", () => {
    expect(buildVisualizationOptions({ type: "pie", sort: "value_desc", limit: 3 })).toEqual({});
    expect(buildVisualizationOptions({ type: "bar", sort: null, limit: null })).toEqual({});
  });

  it("defaults an unconfigured list to no sorting and five rows", () => {
    expect(DEFAULT_LIST_SORT).toBe("none");
    expect(DEFAULT_LIST_LIMIT).toBe(5);
    expect(readListOptions({})).toEqual({ sort: "none", limit: 5 });
  });

  it("reads a saved list widget's sort and limit back for the edit form", () => {
    expect(readListOptions({ sort: "value_desc", limit: 12 })).toEqual({ sort: "value_desc", limit: 12 });
    expect(readListOptions({ sort: "value_asc", limit: 9 })).toEqual({ sort: "value_asc", limit: 9 });
  });

  it("falls back to the defaults for missing or malformed stored values", () => {
    expect(readListOptions({ sort: "alphabetical", limit: 0 })).toEqual({ sort: "none", limit: 5 });
    expect(readListOptions({ limit: "5" })).toEqual({ sort: "none", limit: 5 });
    expect(readListOptions({ limit: 2.5 })).toEqual({ sort: "none", limit: 5 });
  });
});
