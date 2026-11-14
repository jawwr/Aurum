import type { LucideIcon } from "lucide-react";
import { getCategoryIcon } from "@/lib/icons";
import { formatSignedCurrency, getValueColor } from "@/lib/format";
import type { DiagramPoint, WidgetMetric } from "@/types";

export interface WidgetListRow {
  key: string;
  label: string;
  formattedValue: string;
  valueColor: string;
  color: string;
  icon: LucideIcon;
}

export function formatListValue(value: number, metric: WidgetMetric): string {
  return metric === "sum" ? formatSignedCurrency(value) : String(Math.round(value));
}

/** Maps backend list points to display rows — no sorting and no limiting:
 * the backend's ListDiagram already applied the widget's sort and limit, and
 * a "none" sort must show the DataSource's own order, so reordering here
 * would silently violate the saved configuration. */
export function buildListRows(points: DiagramPoint[], metric: WidgetMetric): WidgetListRow[] {
  return points.map((point) => ({
    key: point.key,
    label: point.label,
    formattedValue: formatListValue(Number(point.value), metric),
    valueColor: getValueColor(point.value),
    // Same fallback as RecentTransactionsCard's rows: entities without a
    // color of their own (tags, "Other") render in the muted text tone.
    color: point.color ?? "var(--text-muted)",
    icon: getCategoryIcon(point.icon),
  }));
}

/** The List widget's body: a vertical table-like list without column
 * headers — icon, name, aggregated value per row, rows separated by
 * horizontal dividers (visual reference: RecentTransactionsCard). */
export function WidgetListBody({ points, metric }: { points: DiagramPoint[]; metric: WidgetMetric }) {
  const rows = buildListRows(points, metric);
  return (
    <ul className="divide-y divide-gridline">
      {rows.map((row) => (
        <li key={row.key} className="flex items-center gap-3 py-2.5 first:pt-0 last:pb-0">
          <span
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full"
            style={{ backgroundColor: `${row.color}26` }}
          >
            <row.icon size={15} style={{ color: row.color }} />
          </span>
          <span className="min-w-0 flex-1 truncate text-sm text-text-primary">{row.label}</span>
          <span className="shrink-0 text-sm font-medium tabular-nums" style={{ color: row.valueColor }}>
            {row.formattedValue}
          </span>
        </li>
      ))}
    </ul>
  );
}
