import { PillSelector } from "@/components/layout/PillSelector";
import { YearRangeSelector } from "@/components/layout/YearSelector";
import { CashFlowChart } from "@/components/cashflow/CashFlowChart";
import { useCashFlow } from "@/hooks/useCashFlow";
import { usePageParams } from "@/hooks/usePageParams";
import { useTransactionYears } from "@/hooks/useTransactions";
import { computeRange, type CustomYearRange, type RangePreset } from "@/lib/dateRange";
import { useTranslation } from "@/lib/i18n";
import { rangePresetParam, yearParam } from "@/lib/pageParams";

// Query params mirror what the cash-flow request sends; also kept in localStorage.
const PARAM_SCHEMA = { range: rangePresetParam("this_year"), from: yearParam(), to: yearParam() };

export function CashFlowPage() {
  const { t } = useTranslation();
  const now = new Date();
  const { data: years } = useTransactionYears();
  const [{ range, from, to }, setParams] = usePageParams("cash-flow", PARAM_SCHEMA);
  const customRange: CustomYearRange = { fromYear: from, toYear: to };

  const RANGE_OPTIONS: Array<{ value: RangePreset; label: string }> = [
    { value: "all", label: t("reports.rangeAll") },
    { value: "this_year", label: t("reports.rangeThisYear") },
    { value: "5y", label: t("reports.range5y") },
    { value: "custom", label: t("reports.rangeCustom") },
  ];

  const { startDate, endDate } = computeRange(range, customRange);
  const { data: cashFlow, isLoading } = useCashFlow(startDate, endDate);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-end gap-2">
        <PillSelector options={RANGE_OPTIONS} value={range} onChange={(value: RangePreset) => setParams({ range: value })} />
        {range === "custom" && (
          <YearRangeSelector
            years={years ?? [now.getFullYear()]}
            fromYear={customRange.fromYear}
            toYear={customRange.toYear}
            onChange={(value) => setParams({ from: value.fromYear, to: value.toYear })}
          />
        )}
      </div>

      <CashFlowChart cashFlow={cashFlow} isLoading={isLoading} />
    </div>
  );
}
