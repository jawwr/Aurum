import { api } from "@/api/client";
import type { DashboardWidget, DashboardWidgetInput, DashboardWidgetManifest, WidgetType } from "@/types";

/** Resolve data capabilities for a chart without maintaining client-side
 * lists of dimensions, metrics, sources, filters, or validation rules. */
export function getWidgetCapabilities(
  manifest: DashboardWidgetManifest | undefined,
  type: WidgetType | null,
  selection?: Pick<DashboardWidget, "data_source" | "data_spec"> | null,
) {
  const diagram = manifest?.diagrams.find((entry) => entry.type === type);
  if (!diagram) return null;
  for (const source of manifest?.data_sources ?? []) {
    if (selection && source.id !== selection.data_source) continue;
    const spec = source.specifications.find((candidate) =>
      (!selection || candidate.id === selection.data_spec)
      && diagram.compatible_data_specs.includes(`${source.id}:${candidate.id}`)
      && candidate.compatible_diagrams.includes(diagram.type)
    );
    if (spec) {
      return {
        data_source: source.id,
        data_spec: spec.id,
        diagram,
        spec,
        dimensions: spec.dimensions.filter(
          (dimension) =>
            spec.dimension_kinds[dimension] === diagram.dataset_kind
            && diagram.allowed_dimensions.includes(dimension),
        ),
        metrics: spec.metrics.filter((metric) => diagram.allowed_metrics.includes(metric)),
      };
    }
  }
  return null;
}

export function fetchWidgetTypes() {
  return api.get<DashboardWidgetManifest>("/dashboard/widgets/types");
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
