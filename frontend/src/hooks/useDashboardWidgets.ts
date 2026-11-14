import { useCallback, useEffect, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { fetchDashboardWidgets, fetchWidgetTypes, saveDashboardWidgets } from "@/api/dashboardWidgets";
import type { DashboardConfig, DashboardWidgetsResponse } from "@/types";
import { cloneDashboardConfig, dashboardConfigsEqual } from "@/lib/dashboardConfig";

export function useWidgetTypes() {
  return useQuery({
    queryKey: ["dashboard-widget-types", "data-architecture"],
    queryFn: fetchWidgetTypes,
    staleTime: Infinity,
  });
}

export function useDashboardWidgets(year: number, month: number) {
  const query = useQuery({
    queryKey: ["dashboard-widgets", year, month],
    queryFn: () => fetchDashboardWidgets(year, month),
  });
  const [savedConfig, setSavedConfig] = useState<DashboardConfig | null>(null);
  const [draftConfig, setDraftConfig] = useState<DashboardConfig | null>(null);

  const isDirty = useMemo(
    () => savedConfig !== null && draftConfig !== null && !dashboardConfigsEqual(savedConfig, draftConfig),
    [savedConfig, draftConfig],
  );

  useEffect(() => {
    if (!query.data || isDirty) return;
    const next = cloneDashboardConfig(query.data.config);
    setSavedConfig(next);
    setDraftConfig(cloneDashboardConfig(next));
  }, [query.data, isDirty]);

  const updateDraft = useCallback((update: (current: DashboardConfig) => DashboardConfig) => {
    setDraftConfig((current) => current ? update(cloneDashboardConfig(current)) : current);
  }, []);

  const discardChanges = useCallback(() => {
    setDraftConfig(savedConfig ? cloneDashboardConfig(savedConfig) : null);
  }, [savedConfig]);

  const commitSavedConfig = useCallback((config: DashboardConfig) => {
    setSavedConfig(cloneDashboardConfig(config));
    setDraftConfig(cloneDashboardConfig(config));
  }, []);

  return { ...query, savedConfig, draftConfig, isDirty, updateDraft, discardChanges, commitSavedConfig };
}

export function useSaveDashboardWidgets(year: number, month: number) {
  return useMutation<DashboardWidgetsResponse, Error, DashboardConfig>({
    mutationFn: (config) => saveDashboardWidgets(config, year, month),
  });
}
