import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createDashboardWidget,
  deleteDashboardWidget,
  fetchDashboardWidgets,
  fetchWidgetTypes,
  updateDashboardWidget,
} from "@/api/dashboardWidgets";
import type { DashboardWidgetInput } from "@/types";

// Static per session (doesn't depend on year/month, rarely changes) — one
// fetch is enough, react-query's default caching handles the rest.
export function useWidgetTypes() {
  return useQuery({ queryKey: ["dashboard-widget-types"], queryFn: fetchWidgetTypes });
}

export function useDashboardWidgets(year: number, month: number) {
  return useQuery({
    queryKey: ["dashboard-widgets", year, month],
    queryFn: () => fetchDashboardWidgets(year, month),
  });
}

export function useCreateDashboardWidget(year: number, month: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: DashboardWidgetInput) => createDashboardWidget(input, year, month),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["dashboard-widgets"] }),
  });
}

export function useUpdateDashboardWidget(year: number, month: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, input }: { id: number; input: DashboardWidgetInput }) => updateDashboardWidget(id, input, year, month),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["dashboard-widgets"] }),
  });
}

export function useDeleteDashboardWidget() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deleteDashboardWidget(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["dashboard-widgets"] }),
  });
}
