import { PillSelector } from "@/components/layout/PillSelector";
import { YearRangeSelector } from "@/components/layout/YearSelector";
import { CashFlowChart } from "@/components/cashflow/CashFlowChart";
import { useCashFlow } from "@/hooks/useCashFlow";
import { useTransactionYears } from "@/hooks/useTransactions";
import { computeRange, type CustomYearRange, type RangePreset } from "@/lib/dateRange";
import { useTranslation } from "@/lib/i18n";
import { useQueryState } from "@/hooks/useQueryState";

export function CashFlowPage() {
  const { t } = useTranslation();
  const now = new Date();
  const { data: years } = useTransactionYears();
  const [range, setRange] = useQueryState<RangePreset>("range", "this_year");
  const [customRangeFrom, setCustomRangeFrom] = useQueryState("custom_from", now.getFullYear());
  const [customRangeTo, setCustomRangeTo] = useQueryState("custom_to", now.getFullYear());

  const RANGE_OPTIONS: Array<{ value: RangePreset; label: string }> = [
    { value: "all", label: t("reports.rangeAll") },
    { value: "this_year", label: t("reports.rangeThisYear") },
    { value: "5y", label: t("reports.range5y") },
    { value: "custom", label: t("reports.rangeCustom") },
  ];

  const { startDate, endDate } = computeRange(range, {
    fromYear: Number(customRangeFrom),
    toYear: Number(customRangeTo),
  });
  const { data: cashFlow, isLoading } = useCashFlow(startDate, endDate);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-end gap-2">
        <PillSelector options={RANGE_OPTIONS} value={range} onChange={setRange} />
        {range === "custom" && (
          <YearRangeSelector
            years={years ?? [now.getFullYear()]}
            fromYear={Number(customRangeFrom)}
            toYear={Number(customRangeTo)}
            onChange={(range) => {
              setCustomRangeFrom(range.fromYear);
              setCustomRangeTo(range.toYear);
            }}
          />
        )}
      </div>

      <CashFlowChart cashFlow={cashFlow} isLoading={isLoading} />
    </div>
  );
}
