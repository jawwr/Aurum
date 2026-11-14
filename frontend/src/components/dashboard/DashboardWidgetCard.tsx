import { Bar, BarChart, Cell, Legend, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis } from "recharts";
import { Pencil, Trash2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { formatCurrency, getIntlLocale } from "@/lib/format";
import { useTranslation } from "@/lib/i18n";
import type { DashboardWidget, WidgetGranularity, WidgetMetric } from "@/types";

// The dataviz skill's validated 8-color categorical palette (index.css) —
// category/account points already carry their own color from the backend,
// this only kicks in for tag points (Tag has no color of its own) and the
// "by type" breakdown's few series.
const FALLBACK_PALETTE = [
  "var(--series-1)",
  "var(--series-2)",
  "var(--series-3)",
  "var(--series-4)",
  "var(--series-5)",
  "var(--series-6)",
  "var(--series-7)",
  "var(--series-8)",
];

function pointColor(color: string | null, index: number): string {
  return color ?? FALLBACK_PALETTE[index % FALLBACK_PALETTE.length];
}

function formatValue(value: number, metric: WidgetMetric): string {
  return metric === "sum" ? formatCurrency(value) : String(value);
}

/** A line widget's point label is the raw bucket date the backend returns
 * (ISO, e.g. "2026-09-01") — formatted here per the widget's own granularity
 * rather than on the backend, same split as every other date/money value in
 * the app (formatCurrency, formatTransactionDate, ...). */
function formatLineLabel(label: string, granularity: WidgetGranularity | null): string {
  const date = new Date(`${label}T00:00:00`);
  if (granularity === "month") {
    return new Intl.DateTimeFormat(getIntlLocale(), { month: "short", year: "numeric" }).format(date);
  }
  return new Intl.DateTimeFormat(getIntlLocale(), { month: "short", day: "numeric" }).format(date);
}

interface ChartPoint {
  label: string;
  value: number;
  color: string;
}

function WidgetTooltip({
  active,
  payload,
  metric,
}: {
  active?: boolean;
  payload?: Array<{ payload: ChartPoint }>;
  metric: WidgetMetric;
}) {
  if (!active || !payload?.length) return null;
  const point = payload[0].payload;
  return (
    <div className="rounded-lg border border-border bg-surface-1 px-3 py-2 text-sm shadow-md">
      <p className="font-medium text-text-primary">{point.label}</p>
      <p className="text-text-secondary">{formatValue(point.value, metric)}</p>
    </div>
  );
}

interface DashboardWidgetCardProps {
  widget: DashboardWidget;
  onEdit: (widget: DashboardWidget) => void;
  onDelete: (widget: DashboardWidget) => void;
}

/** Legend's default per-series label would just read "value" (the recharts
 * dataKey) for Bar/Line, which have exactly one series — not useful, so it's
 * overridden to the widget's metric name instead. Pie doesn't hit this path:
 * its Legend already lists each slice's own label via nameKey. */
function seriesLegendFormatter(metric: WidgetMetric, t: ReturnType<typeof useTranslation>["t"]) {
  return () => t(metric === "sum" ? "dashboard.widgets.metric.sum" : "dashboard.widgets.metric.count");
}

export function DashboardWidgetCard({ widget, onEdit, onDelete }: DashboardWidgetCardProps) {
  const { t } = useTranslation();
  const hasData = widget.data.points.length > 0;
  const chartData: ChartPoint[] = widget.data.points.map((point, index) => ({
    label: widget.type === "line" ? formatLineLabel(point.label, widget.granularity) : point.label,
    value: Number(point.value),
    color: pointColor(point.color, index),
  }));

  return (
    <Card>
      <CardHeader>
        <CardTitle>{widget.title}</CardTitle>
        <span className="flex shrink-0 gap-1">
          <button
            type="button"
            aria-label={t("dashboard.widgets.editLabel")}
            onClick={() => onEdit(widget)}
            className="rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-text-primary"
          >
            <Pencil size={15} />
          </button>
          <button
            type="button"
            aria-label={t("dashboard.widgets.removeLabel")}
            onClick={() => onDelete(widget)}
            className="rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-danger"
          >
            <Trash2 size={15} />
          </button>
        </span>
      </CardHeader>
      <CardContent>
        {!hasData ? (
          <p className="py-10 text-center text-sm text-text-muted">{t("dashboard.widgets.noData")}</p>
        ) : (
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              {widget.type === "pie" ? (
                <PieChart>
                  <Pie
                    data={chartData}
                    dataKey="value"
                    nameKey="label"
                    innerRadius="55%"
                    outerRadius="100%"
                    paddingAngle={2}
                    stroke="var(--surface-1)"
                    strokeWidth={2}
                    isAnimationActive={false}
                  >
                    {chartData.map((point, index) => (
                      <Cell key={index} fill={point.color} />
                    ))}
                  </Pie>
                  <Tooltip content={<WidgetTooltip metric={widget.metric} />} />
                  <Legend
                    verticalAlign="bottom"
                    iconType="circle"
                    iconSize={8}
                    wrapperStyle={{ fontSize: 11, color: "var(--text-muted)" }}
                  />
                </PieChart>
              ) : widget.type === "bar" ? (
                <BarChart data={chartData} margin={{ top: 8, right: 4, bottom: 0, left: 4 }}>
                  <XAxis
                    dataKey="label"
                    tick={{ fill: "var(--text-muted)", fontSize: 11 }}
                    axisLine={false}
                    tickLine={false}
                    interval={0}
                    angle={-20}
                    textAnchor="end"
                    height={48}
                  />
                  <Tooltip content={<WidgetTooltip metric={widget.metric} />} cursor={{ fill: "var(--surface-2)" }} />
                  <Legend
                    verticalAlign="top"
                    height={24}
                    formatter={seriesLegendFormatter(widget.metric, t)}
                    wrapperStyle={{ fontSize: 11, color: "var(--text-muted)" }}
                  />
                  <Bar dataKey="value" fill="var(--series-1)" radius={[2, 2, 0, 0]} isAnimationActive={false}>
                    {chartData.map((point, index) => (
                      <Cell key={index} fill={point.color} />
                    ))}
                  </Bar>
                </BarChart>
              ) : (
                <LineChart data={chartData} margin={{ top: 8, right: 4, bottom: 0, left: 4 }}>
                  <XAxis
                    dataKey="label"
                    tick={{ fill: "var(--text-muted)", fontSize: 11 }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <Tooltip content={<WidgetTooltip metric={widget.metric} />} />
                  <Legend
                    verticalAlign="top"
                    height={24}
                    formatter={seriesLegendFormatter(widget.metric, t)}
                    wrapperStyle={{ fontSize: 11, color: "var(--text-muted)" }}
                  />
                  <Line type="monotone" dataKey="value" stroke="var(--series-1)" strokeWidth={2} dot={false} isAnimationActive={false} />
                </LineChart>
              )}
            </ResponsiveContainer>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
