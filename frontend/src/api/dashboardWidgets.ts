import { api } from "@/api/client";
import type {
  DashboardConfig,
  DashboardWidgetsResponse,
  DashboardWidget,
  DashboardWidgetManifest,
  DataSpecManifestEntry,
  WidgetType,
} from "@/types";

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

/** Metrics actually selectable for a dimension: the caller's already
 * diagram-filtered metric list minus the per-dimension exclusions
 * ("item" only supports sum). Tolerates a manifest cached from an
 * older backend without forbidden_metrics_by_dimension — a missing field
 * means "no exclusions", not a crash (see useWidgetTypes' staleTime:
 * Infinity: the in-memory manifest outlives a backend restart within a
 * session). */
export function withoutForbiddenMetrics(
  metrics: readonly string[],
  spec: Pick<DataSpecManifestEntry, "forbidden_metrics_by_dimension"> | undefined | null,
  dimension: string,
): string[] {
  const forbidden = spec?.forbidden_metrics_by_dimension?.[dimension] ?? [];
  return metrics.filter((metric) => !forbidden.includes(metric));
}

/** How the form should offer a filter for a dimension: "required" (the
 * backend rejects the widget without it — render a mandatory select),
 * "optional" (the dimension accepts it but doesn't require it — render a
 * select with an "all" choice, sent as null), or "hidden" (forbidden for
 * the dimension, or the spec
 * doesn't support the filter at all). Derived entirely from manifest data,
 * same as the metric options. */
export function filterAvailability(
  spec: Pick<DataSpecManifestEntry, "filters" | "required_by_dimension" | "forbidden_by_dimension"> | undefined | null,
  filter: string,
  dimension: string,
): "required" | "optional" | "hidden" {
  if (!spec) return "hidden";
  if ((spec.forbidden_by_dimension?.[dimension] ?? []).includes(filter)) return "hidden";
  if (!spec.filters.includes(filter)) return "hidden";
  if ((spec.required_by_dimension?.[dimension] ?? []).includes(filter)) return "required";
  return "optional";
}

export function fetchDashboardWidgets(year: number, month: number) {
  return api.get<DashboardWidgetsResponse>(`/dashboard/widgets?year=${year}&month=${month}`);
}

export function saveDashboardWidgets(config: DashboardConfig, year: number, month: number) {
  return api.put<DashboardWidgetsResponse>(`/dashboard/widgets?year=${year}&month=${month}`, config);
}
