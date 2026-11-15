import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchWidgetTypes, filterAvailability, getWidgetCapabilities, saveDashboardWidgets, withoutForbiddenMetrics } from "@/api/dashboardWidgets";
import type { DashboardWidgetManifest } from "@/types";

vi.mock("@/lib/auth", () => ({
  getAuthHeader: () => null,
  clearCredentials: () => undefined,
}));

const manifest: DashboardWidgetManifest = {
  data_sources: [
    {
      id: "transactions",
      specifications: [
        {
          id: "analytics",
          dimensions: ["category", "total"],
          metrics: ["sum", "count"],
          filters: ["transaction_type", "account_id", "granularity"],
          required_parameters: ["dimension", "metric"],
          dimension_kinds: { category: "categorical", total: "time_series" },
          required_by_dimension: { total: ["granularity"] },
          forbidden_by_dimension: { category: ["granularity"] },
          forbidden_metrics_by_dimension: {},
          filter_options: {
            transaction_type: ["expense", "income", "transfer"],
            granularity: ["day", "week", "month"],
          },
          compatible_diagrams: ["pie", "bar", "line"],
        },
      ],
    },
  ],
  diagrams: [
    {
      type: "pie",
      dataset_kind: "categorical",
      allowed_dimensions: ["category"],
      allowed_metrics: ["sum", "count"],
      needs_granularity: false,
      compatible_data_specs: ["transactions:analytics"],
    },
    {
      type: "line",
      dataset_kind: "time_series",
      allowed_dimensions: ["total"],
      allowed_metrics: ["sum", "count"],
      needs_granularity: true,
      compatible_data_specs: ["transactions:analytics"],
    },
  ],
};

describe("getWidgetCapabilities", () => {
  it("resolves source, spec, dimensions, and metrics from backend manifest", () => {
    expect(getWidgetCapabilities(manifest, "pie")).toMatchObject({
      data_source: "transactions",
      data_spec: "analytics",
      dimensions: ["category"],
      metrics: ["sum", "count"],
    });
  });

  it("keeps time-series dimensions available only to compatible diagrams", () => {
    expect(getWidgetCapabilities(manifest, "line")?.dimensions).toEqual(["total"]);
    expect(getWidgetCapabilities(manifest, "pie")?.dimensions).not.toContain("total");
  });

  it("uses the manifest to exclude ungrouped items from pie while retaining them in list", () => {
    const spec = manifest.data_sources[0]!.specifications[0]!;
    const withItem: DashboardWidgetManifest = {
      ...manifest,
      data_sources: [{ id: "transactions", specifications: [{
        ...spec,
        dimensions: [...spec.dimensions, "item"],
        dimension_kinds: { ...spec.dimension_kinds, item: "categorical" },
        compatible_diagrams: [...spec.compatible_diagrams, "list"],
      }] }],
      diagrams: [...manifest.diagrams, {
        ...manifest.diagrams[0], type: "list", allowed_dimensions: ["category", "item"],
      }],
    };
    expect(getWidgetCapabilities(withItem, "pie")?.dimensions).toEqual(["category"]);
    expect(getWidgetCapabilities(withItem, "list")?.dimensions).toEqual(["category", "item"]);
  });

  it("returns no configuration for an unknown chart or incompatible saved source", () => {
    expect(getWidgetCapabilities(manifest, "bar")).toBeNull();
    expect(
      getWidgetCapabilities(manifest, "pie", { data_source: "budgets", data_spec: "status" }),
    ).toBeNull();
  });
});

describe("withoutForbiddenMetrics", () => {
  it("drops the metrics a dimension forbids", () => {
    const spec = { forbidden_metrics_by_dimension: { transaction: ["count"] } };
    expect(withoutForbiddenMetrics(["sum", "count"], spec, "transaction")).toEqual(["sum"]);
    expect(withoutForbiddenMetrics(["sum", "count"], spec, "category")).toEqual(["sum", "count"]);
  });

  it("returns the metrics unchanged when the manifest predates the field", () => {
    // useWidgetTypes caches the manifest with staleTime: Infinity — a
    // session started before the backend update keeps serving a manifest
    // without forbidden_metrics_by_dimension. Reading it must not crash
    // (it used to blank the whole Dashboard when a chart type was picked).
    expect(withoutForbiddenMetrics(["sum", "count"], {}, "transaction")).toEqual(["sum", "count"]);
    expect(withoutForbiddenMetrics(["sum", "count"], undefined, "transaction")).toEqual(["sum", "count"]);
    expect(withoutForbiddenMetrics(["sum", "count"], null, "transaction")).toEqual(["sum", "count"]);
  });
});

describe("filterAvailability", () => {
  it("allows an all-types choice for every dimension that supports the filter", () => {
    const spec = {
      filters: ["transaction_type"],
      required_by_dimension: { category: [], item: [] },
      forbidden_by_dimension: { type: ["transaction_type"] },
    };
    expect(filterAvailability(spec, "transaction_type", "category")).toBe("optional");
    expect(filterAvailability(spec, "transaction_type", "item")).toBe("optional");
    expect(filterAvailability(spec, "transaction_type", "type")).toBe("hidden");
  });
});

describe("dashboard widget API contracts", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("fetches the backend data manifest instead of a client-side list", async () => {
    const responseBody = { data_sources: [], diagrams: [] };
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => responseBody,
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(fetchWidgetTypes()).resolves.toEqual(responseBody);
    expect(fetchMock).toHaveBeenCalledWith("/api/dashboard/widgets/types", expect.any(Object));
  });

  it("sends the complete versioned Dashboard document with PUT", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ config: { schema_version: 1, widgets: [] }, widgets: [] }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await saveDashboardWidgets({
      schema_version: 1,
      widgets: [{
        id: "widget-1",
        data_source: "transactions",
        data_spec: "analytics",
        title: "Expenses",
        query: {
          dimension: "category",
          metric: "sum",
          filters: { transaction_type: "expense", account_id: null },
          granularity: null,
        },
        visualization: { type: "bar", options: {} },
      }],
    },
      2026,
      8,
    );

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(init.body as string)).toMatchObject({
      schema_version: 1,
      widgets: [{ id: "widget-1", query: { dimension: "category" } }],
    });
    expect(init.method).toBe("PUT");
  });
});
