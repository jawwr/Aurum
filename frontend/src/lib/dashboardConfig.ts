import type { DashboardConfig, DashboardWidgetConfig } from "@/types";

export function cloneDashboardConfig(config: DashboardConfig): DashboardConfig {
  return structuredClone(config);
}

export function dashboardConfigsEqual(left: DashboardConfig, right: DashboardConfig): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
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
