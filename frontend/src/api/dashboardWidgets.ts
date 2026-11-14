import { api } from "@/api/client";
import type { DashboardWidget, DashboardWidgetInput, WidgetTypeManifestEntry } from "@/types";

export function fetchWidgetTypes() {
  return api.get<WidgetTypeManifestEntry[]>("/dashboard/widgets/types");
}

export function fetchDashboardWidgets(year: number, month: number) {
  return api.get<DashboardWidget[]>(`/dashboard/widgets?year=${year}&month=${month}`);
}

export function createDashboardWidget(input: DashboardWidgetInput, year: number, month: number) {
  return api.post<DashboardWidget>(`/dashboard/widgets?year=${year}&month=${month}`, input);
}

export function updateDashboardWidget(id: number, input: DashboardWidgetInput, year: number, month: number) {
  return api.patch<DashboardWidget>(`/dashboard/widgets/${id}?year=${year}&month=${month}`, input);
}

export function deleteDashboardWidget(id: number) {
  return api.delete<void>(`/dashboard/widgets/${id}`);
}
