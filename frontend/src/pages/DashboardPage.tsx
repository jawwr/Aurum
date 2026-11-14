import {useEffect, useMemo, useState} from "react";
import {MonthSelector} from "@/components/layout/MonthSelector";
import {YearSelector} from "@/components/layout/YearSelector";
import {Plus} from "lucide-react";
import {Button} from "@/components/ui/Button";
import {StatCard} from "@/components/dashboard/StatCard";
import {SpendingByCategoryCard} from "@/components/dashboard/SpendingByCategoryCard";
import {RecentTransactionsCard} from "@/components/dashboard/RecentTransactionsCard";
import {DashboardWidgetCard} from "@/components/dashboard/DashboardWidgetCard";
import {AddWidgetModal} from "@/components/dashboard/AddWidgetModal";
import {AlertBanner} from "@/components/insights/AlertBanner";
import {useDashboardSummary} from "@/hooks/useDashboard";
import {usePageParams} from "@/hooks/usePageParams";
import {useTransactionYears} from "@/hooks/useTransactions";
import {useDashboardWidgets, useSaveDashboardWidgets} from "@/hooks/useDashboardWidgets";
import {formatCurrency, formatSignedCurrency} from "@/lib/format";
import {useTranslation} from "@/lib/i18n";
import {monthParam, yearParam} from "@/lib/pageParams";
import type {DashboardWidget, DashboardWidgetConfig, DashboardWidgetInput} from "@/types";

// Query params mirror what the summary request sends; also kept in localStorage.
const PARAM_SCHEMA = {year: yearParam(), month: monthParam()};

/** Share of income left over after spending (net / real_income). `null` when
 * there was no income to take a share of, rather than a misleading 0%. */
function savingsRate(realIncome: number, net: number): number | null {
    return realIncome > 0 ? (net / realIncome) * 100 : null;
}

function formatPercent(value: number): string {
    const sign = value > 0 ? "+" : "";
    return `${sign}${value.toFixed(0)}%`;
}

export function DashboardPage() {
    const {t} = useTranslation();
    const now = new Date();
    const [{year, month}, setParams] = usePageParams("dashboard", PARAM_SCHEMA);
    const {data: years} = useTransactionYears();

    const {data, isLoading, isError} = useDashboardSummary(year, month);
    const rate = data ? savingsRate(Number(data.real_income), Number(data.net)) : null;

    const [widgetModalOpen, setWidgetModalOpen] = useState(false);
    const [editingWidget, setEditingWidget] = useState<DashboardWidgetConfig | null>(null);
    const widgetState = useDashboardWidgets(year, month);
    const saveWidgets = useSaveDashboardWidgets(year, month);
    const [saveError, setSaveError] = useState(false);
    const {draftConfig, isDirty, updateDraft, discardChanges} = widgetState;

    useEffect(() => {
        if (!isDirty) return;
        const handleBeforeUnload = (event: BeforeUnloadEvent) => {
            event.preventDefault();
            event.returnValue = "";
        };
        window.addEventListener("beforeunload", handleBeforeUnload);
        return () => window.removeEventListener("beforeunload", handleBeforeUnload);
    }, [isDirty]);


    function openCreateWidgetModal() {
        setEditingWidget(null);
        setWidgetModalOpen(true);
    }

    function openEditWidgetModal(widget: DashboardWidget) {
        setEditingWidget(draftConfig?.widgets.find((item) => item.id === widget.id) ?? null);
        setWidgetModalOpen(true);
    }

    function handleDeleteWidget(widget: DashboardWidget) {
        if (window.confirm(t("dashboard.widgets.confirmDelete", {title: widget.title}))) {
            updateDraft((current) => ({...current, widgets: current.widgets.filter((item) => item.id !== widget.id)}));
        }
    }

    function handleWidgetSubmit(input: DashboardWidgetInput) {
        setSaveError(false);
        updateDraft((current) => {
            const widget: DashboardWidgetConfig = {
                id: editingWidget?.id ?? crypto.randomUUID(),
                title: input.title,
                data_source: input.data_source,
                data_spec: input.data_spec,
                query: {
                    dimension: input.dimension,
                    metric: input.metric,
                    filters: {transaction_type: input.transaction_type, account_id: input.account_id},
                    granularity: input.granularity,
                },
                visualization: {type: input.type, options: {}},
            };
            return {...current, widgets: editingWidget
                ? current.widgets.map((item) => item.id === editingWidget.id ? widget : item)
                : [...current.widgets, widget]};
        });
        setWidgetModalOpen(false);
    }

    async function handleSave() {
        if (!draftConfig) return;
        setSaveError(false);
        try {
            await saveWidgets.mutateAsync(draftConfig);
            const refreshed = await widgetState.refetch();
            if (refreshed.data) widgetState.commitSavedConfig(refreshed.data.config);
        } catch {
            // Keep the draft intact so the user can correct and retry it.
            setSaveError(true);
        }
    }

    const displayWidgets = useMemo(() => {
        const dataById = new Map((widgetState.data?.widgets ?? []).map((item) => [item.id, item.data]));
        return (draftConfig?.widgets ?? []).map((widget) => ({
            id: widget.id,
            data_source: widget.data_source,
            data_spec: widget.data_spec,
            type: widget.visualization.type,
            title: widget.title,
            dimension: widget.query.dimension,
            metric: widget.query.metric,
            transaction_type: widget.query.filters.transaction_type,
            granularity: widget.query.granularity,
            account_id: widget.query.filters.account_id,
            data: dataById.get(widget.id) ?? {points: []},
        } satisfies DashboardWidget));
    }, [draftConfig, widgetState.data]);

    return (
        <div className="space-y-5">
            <AlertBanner excludeKeys={["risky_allocation_exceeded"]}/>

            <div className="flex items-center gap-3">
                <div className="min-w-0 flex-1">
                    <MonthSelector month={month} onChange={(value) => setParams({month: value})}/>
                </div>
                <YearSelector years={years ?? [now.getFullYear()]} year={year}
                              onChange={(value) => setParams({year: value})}/>
            </div>

            {isError && (
                <p className="rounded-lg border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">
                    {t("dashboard.errorLoading")}
                </p>
            )}

            <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
                <StatCard
                    label={t("dashboard.statRealIncomeLabel")}
                    value={isLoading ? "…" : formatCurrency(data?.real_income ?? 0)}
                    caption={t("dashboard.statRealIncomeCaption")}
                    tone="success"
                />
                <StatCard
                    label={t("dashboard.statSpentLabel")}
                    value={isLoading ? "…" : formatCurrency(data?.spent ?? 0)}
                    caption={t("dashboard.statSpentCaption")}
                    tone="danger"
                />
                <StatCard
                    label={t("dashboard.statNetLabel")}
                    value={isLoading ? "…" : formatSignedCurrency(data?.net ?? 0)}
                    caption={t("dashboard.statNetCaption")}
                    tone={Number(data?.net ?? 0) >= 0 ? "success" : "danger"}
                />
                <StatCard
                    label={t("dashboard.statSavingsRateLabel")}
                    value={isLoading ? "…" : rate === null ? "—" : formatPercent(rate)}
                    caption={t("dashboard.statSavingsRateCaption")}
                    tone={rate === null ? "default" : rate >= 0 ? "success" : "danger"}
                />
            </div>

            <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1.4fr_1fr]">
                <SpendingByCategoryCard items={data?.spending_by_category ?? []}/>
                <RecentTransactionsCard year={year} month={month}/>
            </div>

            <div className="flex items-center justify-between">
                <h2 className="text-xs font-semibold uppercase tracking-wide text-text-muted">
                    {t("dashboard.widgets.sectionTitle")}
                </h2>
                 <div className="flex items-center gap-2">
                     {isDirty && <span className="text-xs text-text-muted">{t("dashboard.widgets.dirty")}</span>}
                     <Button variant="secondary" onClick={discardChanges} disabled={!isDirty}>{t("dashboard.widgets.revertButton")}</Button>
                     <Button onClick={handleSave} disabled={!isDirty || saveWidgets.isPending}>{t("dashboard.widgets.saveDashboardButton")}</Button>
                     <Button variant="secondary" onClick={openCreateWidgetModal}><Plus size={16}/>{t("dashboard.widgets.addButton")}</Button>
                 </div>
             </div>
             {saveError && <p className="text-sm text-danger">{t("dashboard.widgets.saveError")}</p>}

             {displayWidgets.length > 0 && (
                <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                     {displayWidgets.map((widget) => (
                        <DashboardWidgetCard
                            key={widget.id}
                            widget={widget}
                            onEdit={openEditWidgetModal}
                            onDelete={handleDeleteWidget}
                        />
                    ))}
                </div>
            )}

            <AddWidgetModal
                open={widgetModalOpen}
                onClose={() => setWidgetModalOpen(false)}
                 widget={editingWidget}
                 onSubmit={handleWidgetSubmit}
            />
        </div>
    );
}
