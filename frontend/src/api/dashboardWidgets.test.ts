import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchWidgetTypes, getWidgetCapabilities, saveDashboardWidgets } from "@/api/dashboardWidgets";
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
          required_by_dimension: { category: ["transaction_type"], total: ["transaction_type", "granularity"] },
          forbidden_by_dimension: { category: ["granularity"] },
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

  it("returns no configuration for an unknown chart or incompatible saved source", () => {
    expect(getWidgetCapabilities(manifest, "bar")).toBeNull();
    expect(
      getWidgetCapabilities(manifest, "pie", { data_source: "budgets", data_spec: "status" }),
    ).toBeNull();
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
