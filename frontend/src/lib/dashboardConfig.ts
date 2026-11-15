import type { DashboardConfig, DashboardWidgetConfig, DashboardWidgetInput, WidgetSort } from "@/types";

// Mirrors the backend ListDiagram's own defaults — the two must stay in sync
// so an unconfigured list widget behaves identically on both sides.
export const DEFAULT_LIST_SORT: WidgetSort = "none";
export const DEFAULT_LIST_LIMIT = 5;

export function cloneDashboardConfig(config: DashboardConfig): DashboardConfig {
  return structuredClone(config);
}

export function dashboardConfigsEqual(left: DashboardConfig, right: DashboardConfig): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

/** Persisted visualization options for a widget submission. Only the list
 * diagram reads options (sort, limit); the chart types keep the empty
 * options object they've always saved. */
export function buildVisualizationOptions(
  input: Pick<DashboardWidgetInput, "type" | "sort" | "limit">,
): DashboardWidgetConfig["visualization"]["options"] {
  if (input.type !== "list") return {};
  return {
    sort: input.sort ?? DEFAULT_LIST_SORT,
    limit: input.limit ?? DEFAULT_LIST_LIMIT,
  };
}

/** Read a saved list widget's sort/limit back for the edit form, falling
 * back to the defaults for anything missing or malformed — the backend
 * already rejected genuinely invalid values at save time. */
export function readListOptions(
  options: DashboardWidgetConfig["visualization"]["options"],
): { sort: WidgetSort; limit: number } {
  const sort = options.sort;
  const limit = options.limit;
  return {
    sort: sort === "value_desc" || sort === "value_asc" ? sort : DEFAULT_LIST_SORT,
    limit: typeof limit === "number" && Number.isInteger(limit) && limit > 0 ? limit : DEFAULT_LIST_LIMIT,
  };
}

export function upsertDashboardWidget(
  config: DashboardConfig,
  widget: DashboardWidgetConfig,
): DashboardConfig {
  const exists = config.widgets.some((item) => item.id === widget.id);
  return {
    ...cloneDashboardConfig(config),
    widgets: exists
      ? config.widgets.map((item) => item.id === widget.id ? widget : item)
      : [...config.widgets, widget],
  };
}

export function removeDashboardWidget(config: DashboardConfig, widgetId: string): DashboardConfig {
  return {
    ...cloneDashboardConfig(config),
    widgets: config.widgets.filter((item) => item.id !== widgetId),
  };
}
