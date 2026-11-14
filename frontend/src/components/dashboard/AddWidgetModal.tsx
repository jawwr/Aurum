import { useEffect, useState } from "react";
import { BarChart3, LineChart as LineChartIcon, PieChart as PieChartIcon, type LucideIcon } from "lucide-react";
import { Dialog } from "@/components/ui/Dialog";
import { Button } from "@/components/ui/Button";
import { Input, Label, Select } from "@/components/ui/Input";
import { useAccounts } from "@/hooks/useAccounts";
import { useCreateDashboardWidget, useUpdateDashboardWidget, useWidgetTypes } from "@/hooks/useDashboardWidgets";
import { useTranslation, type TranslationKey } from "@/lib/i18n";
import { getWidgetCapabilities } from "@/api/dashboardWidgets";
import type {
  DashboardWidget,
  DashboardWidgetInput,
  TransactionType,
  WidgetDimension,
  WidgetGranularity,
  WidgetMetric,
  WidgetType,
} from "@/types";

interface AddWidgetModalProps {
  open: boolean;
  onClose: () => void;
  year: number;
  month: number;
  /** Present -> edit that widget (same form, pre-filled, PATCH on submit).
   * Absent -> create a new one. */
  widget?: DashboardWidget | null;
}

const CHART_TYPE_ICONS: Record<WidgetType, LucideIcon> = { pie: PieChartIcon, bar: BarChart3, line: LineChartIcon };

const EMPTY_FORM = {
  chartType: null as WidgetType | null,
  title: "",
  dimension: "" as WidgetDimension | "",
  metric: "" as WidgetMetric | "",
  transactionType: "" as TransactionType | "",
  granularity: "" as WidgetGranularity | "",
  accountId: "",
};

/** Progressive disclosure, not a literal multi-step wizard: pick a chart
 * type first, then the field pickers below it appear — driven entirely by
 * the backend DataSpec and compatible Dataset shape, so a dimension the backend wouldn't accept never even
 * shows up as an option. Same form for create and edit — this component
 * never unmounts (DashboardPage renders it unconditionally, Dialog just
 * hides its content), so the fields are (re)populated from `widget` in an
 * effect keyed on `open`, the same pattern TransactionFormModal uses. */
export function AddWidgetModal({ open, onClose, year, month, widget }: AddWidgetModalProps) {
  const { t } = useTranslation();
  const { data: widgetTypes } = useWidgetTypes();
  const { data: accounts } = useAccounts();
  const createWidget = useCreateDashboardWidget(year, month);
  const updateWidget = useUpdateDashboardWidget(year, month);
  const isSaving = createWidget.isPending || updateWidget.isPending;

  const [chartType, setChartType] = useState(EMPTY_FORM.chartType);
  const [dataSource, setDataSource] = useState("");
  const [title, setTitle] = useState(EMPTY_FORM.title);
  const [dimension, setDimension] = useState(EMPTY_FORM.dimension);
  const [metric, setMetric] = useState(EMPTY_FORM.metric);
  const [transactionType, setTransactionType] = useState(EMPTY_FORM.transactionType);
  const [granularity, setGranularity] = useState(EMPTY_FORM.granularity);
  const [accountId, setAccountId] = useState(EMPTY_FORM.accountId);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    if (widget) {
      setDataSource(widget.data_source);
      setChartType(widget.type);
      setTitle(widget.title);
      setDimension(widget.dimension);
      setMetric(widget.metric);
      setTransactionType(widget.transaction_type ?? "");
      setGranularity(widget.granularity ?? "");
      setAccountId(widget.account_id ? String(widget.account_id) : "");
    } else {
      setDataSource("");
      setChartType(EMPTY_FORM.chartType);
      setTitle(EMPTY_FORM.title);
      setDimension(EMPTY_FORM.dimension);
      setMetric(EMPTY_FORM.metric);
      setTransactionType(EMPTY_FORM.transactionType);
      setGranularity(EMPTY_FORM.granularity);
      setAccountId(EMPTY_FORM.accountId);
    }
    setError(null);
  }, [open, widget]);

  const selectedSource = dataSource || widgetTypes?.data_sources[0]?.id || "";
  function getCapabilities(type: WidgetType | null) {
    const source = widgetTypes?.data_sources.find((entry) => entry.id === selectedSource);
    const specs = source?.specifications ?? [];
    const preferredSpec = widget?.data_source === selectedSource ? widget.data_spec : null;
    const orderedSpecs = [...specs].sort((a, b) => Number(b.id === preferredSpec) - Number(a.id === preferredSpec));
    for (const spec of orderedSpecs) {
      const result = getWidgetCapabilities(widgetTypes, type, { data_source: selectedSource, data_spec: spec.id });
      if (result) return result;
    }
    return null;
  }
  const capabilities = getCapabilities(chartType);
  const chartTypes = (widgetTypes?.diagrams ?? [])
    .filter((entry) => getCapabilities(entry.type))
    .map((entry) => entry.type);
  const requiredParameters = [
    ...(capabilities?.spec.required_parameters ?? []),
    ...(capabilities?.spec.required_by_dimension[dimension] ?? []),
  ];
  const needsTransactionType = requiredParameters.includes("transaction_type");
  const needsGranularity = requiredParameters.includes("granularity");
  const supportsAccountFilter = capabilities?.spec.filters.includes("account_id") ?? false;

  function handleClose() {
    onClose();
  }

  function handleSelectChartType(type: WidgetType) {
    setChartType(type);
    // A dimension/metric valid for the previous type may not be valid for
    // the new one (Line only ever offers "total") — clear rather than carry
    // over a now-invalid selection.
    setDimension("");
    setMetric("");
    setGranularity("");
    setError(null);
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    if (!chartType || !dimension || !metric || !capabilities) return;
    if (!capabilities.dimensions.includes(dimension) || !capabilities.metrics.includes(metric)) return;
    if (!title.trim()) {
      setError(t("dashboard.widgets.errorTitle"));
      return;
    }
    if (needsTransactionType && !transactionType) {
      setError(t("dashboard.widgets.errorTransactionType"));
      return;
    }
    if (needsGranularity && !granularity) {
      setError(t("dashboard.widgets.errorGranularity"));
      return;
    }

    const payload: DashboardWidgetInput = {
      data_source: capabilities.data_source,
      data_spec: capabilities.data_spec,
      type: chartType,
      title: title.trim(),
      dimension: dimension as WidgetDimension,
      metric: metric as WidgetMetric,
      transaction_type: needsTransactionType ? (transactionType as TransactionType) : null,
      granularity: needsGranularity ? (granularity as WidgetGranularity) : null,
      account_id: supportsAccountFilter && accountId ? Number(accountId) : null,
    };
    if (widget) {
      await updateWidget.mutateAsync({ id: widget.id, input: payload });
    } else {
      await createWidget.mutateAsync(payload);
    }
    handleClose();
  }

  return (
    <Dialog
      open={open}
      onClose={handleClose}
      title={widget ? t("dashboard.widgets.editModalTitle") : t("dashboard.widgets.modalTitle")}
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <Label htmlFor="widget-data-source">{t("dashboard.widgets.dataSourceLabel")}</Label>
          <Select
            id="widget-data-source"
            value={selectedSource}
            onChange={(event) => {
              setDataSource(event.target.value);
              setChartType(null);
              setDimension("");
              setMetric("");
              setTransactionType("");
              setGranularity("");
              setAccountId("");
              setError(null);
            }}
            required
          >
            {(widgetTypes?.data_sources ?? []).map((source) => (
              <option key={source.id} value={source.id}>{source.id}</option>
            ))}
          </Select>
        </div>
        <div>
          <Label>{t("dashboard.widgets.chartTypeLabel")}</Label>
          <div className="mt-1.5 grid grid-cols-3 gap-2">
            {chartTypes.map((type) => {
              const Icon = CHART_TYPE_ICONS[type];
              const selected = chartType === type;
              return (
                <button
                  key={type}
                  type="button"
                  onClick={() => handleSelectChartType(type)}
                  className={`flex flex-col items-center gap-1.5 rounded-lg border p-3 text-xs transition-colors ${
                    selected
                      ? "border-text-primary bg-surface-2 text-text-primary"
                      : "border-border text-text-muted hover:bg-surface-2"
                  }`}
                >
                  <Icon size={20} />
                  {t(`dashboard.widgets.chartType.${type}` as TranslationKey)}
                </button>
              );
            })}
          </div>
        </div>

        {capabilities && (
          <>
            <div>
              <Label htmlFor="widget-title">{t("dashboard.widgets.titleLabel")}</Label>
              <Input
                id="widget-title"
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                placeholder={t("dashboard.widgets.titlePlaceholder")}
                required
              />
            </div>

            <div>
              <Label htmlFor="widget-dimension">{t("dashboard.widgets.dimensionLabel")}</Label>
              <Select
                id="widget-dimension"
                value={dimension}
                onChange={(event) => setDimension(event.target.value as WidgetDimension)}
                required
              >
                <option value="" disabled>
                  {t("dashboard.widgets.dimensionLabel")}
                </option>
                {capabilities.dimensions.map((dim) => (
                  <option key={dim} value={dim}>
                    {t(`dashboard.widgets.dimension.${dim}` as TranslationKey)}
                  </option>
                ))}
              </Select>
            </div>

            <div>
              <Label htmlFor="widget-metric">{t("dashboard.widgets.metricLabel")}</Label>
              <Select
                id="widget-metric"
                value={metric}
                onChange={(event) => setMetric(event.target.value as WidgetMetric)}
                required
              >
                <option value="" disabled>
                  {t("dashboard.widgets.metricLabel")}
                </option>
                {capabilities.metrics.map((m) => (
                  <option key={m} value={m}>
                    {t(`dashboard.widgets.metric.${m}` as TranslationKey)}
                  </option>
                ))}
              </Select>
            </div>

            {needsTransactionType && (
              <div>
                <Label htmlFor="widget-transaction-type">{t("dashboard.widgets.transactionTypeLabel")}</Label>
                <Select
                  id="widget-transaction-type"
                  value={transactionType}
                  onChange={(event) => setTransactionType(event.target.value as TransactionType)}
                  required
                >
                  <option value="" disabled>
                    {t("dashboard.widgets.transactionTypeLabel")}
                  </option>
                  {(capabilities.spec.filter_options.transaction_type ?? []).map((type) => (
                    <option key={type} value={type}>{t(`transactions.${type}` as TranslationKey)}</option>
                  ))}
                </Select>
              </div>
            )}

            {needsGranularity && (
              <div>
                <Label htmlFor="widget-granularity">{t("dashboard.widgets.granularityLabel")}</Label>
                <Select
                  id="widget-granularity"
                  value={granularity}
                  onChange={(event) => setGranularity(event.target.value as WidgetGranularity)}
                  required
                >
                  <option value="" disabled>
                    {t("dashboard.widgets.granularityLabel")}
                  </option>
                  {(capabilities.spec.filter_options.granularity ?? []).map((value) => (
                    <option key={value} value={value}>{t(`dashboard.widgets.granularity.${value}` as TranslationKey)}</option>
                  ))}
                </Select>
              </div>
            )}

            {supportsAccountFilter && accounts && accounts.length > 0 && (
              <div>
                <Label htmlFor="widget-account">{t("dashboard.widgets.accountFilterLabel")}</Label>
                <Select id="widget-account" value={accountId} onChange={(event) => setAccountId(event.target.value)}>
                  <option value="">{t("dashboard.widgets.allAccountsOption")}</option>
                  {accounts.map((account) => (
                    <option key={account.id} value={account.id}>
                      {account.name}
                    </option>
                  ))}
                </Select>
              </div>
            )}
          </>
        )}

        {error && <p className="text-sm text-danger">{error}</p>}

        <div className="flex justify-end gap-2 pt-1">
          <Button type="button" variant="secondary" onClick={handleClose}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" disabled={!capabilities || !dimension || !metric || isSaving}>
            {widget ? t("dashboard.widgets.saveEditButton") : t("dashboard.widgets.saveButton")}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
