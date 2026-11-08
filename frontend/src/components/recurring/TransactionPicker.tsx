import { useEffect, useState } from "react";
import { Check } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Input, Select } from "@/components/ui/Input";
import { MonthSelector } from "@/components/layout/MonthSelector";
import { YearSelector } from "@/components/layout/YearSelector";
import { useCategories } from "@/hooks/useCategories";
import { useTags } from "@/hooks/useTags";
import { useTransactions, useTransactionYears } from "@/hooks/useTransactions";
import { TRANSACTION_SORTS, type TransactionSort } from "@/api/transactions";
import { useTranslation } from "@/lib/i18n";
import { buildHierarchicalCategories, translateCategoryName } from "@/lib/categoryLabels";
import { formatCurrency, formatTransactionDate } from "@/lib/format";
import type { Transaction, TransactionType } from "@/types";

const PAGE_SIZE = 20;

interface TransactionPickerProps {
  disabled: boolean;
  onPick: (transaction: Transaction) => void;
}

/** The transactions page's filters (month/year, search, type, category, tag,
 * sort) with a check button per row instead of edit/delete. State is local —
 * unlike the page itself it must not rewrite the URL or localStorage. */
export function TransactionPicker({ disabled, onPick }: TransactionPickerProps) {
  const { t, language } = useTranslation();
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [type, setType] = useState<TransactionType | "">("");
  const [category, setCategory] = useState("");
  const [tag, setTag] = useState("");
  const [sort, setSort] = useState<TransactionSort>("date_desc");
  const [page, setPage] = useState(1);
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");

  // Same idea as the transactions page: the query follows the trimmed text
  // only after the user stops typing for 300 ms.
  useEffect(() => {
    const timeout = setTimeout(() => {
      const trimmed = searchInput.trim();
      if (trimmed === search) return;
      setSearch(trimmed);
      setPage(1);
    }, 300);
    return () => clearTimeout(timeout);
  }, [searchInput, search]);

  const isSearching = search.length > 0;

  const { data: categories } = useCategories();
  const { data: tags } = useTags();
  const { data: years } = useTransactionYears();
  const { data, isLoading, isError } = useTransactions({
    // A search spans every period, exactly like on the transactions page.
    year: isSearching ? undefined : year,
    month: isSearching ? undefined : month,
    search: isSearching ? search : undefined,
    type: type || undefined,
    category_id: category ? Number(category) : undefined,
    tag_id: tag ? Number(tag) : undefined,
    sort,
    page,
    page_size: PAGE_SIZE,
  });

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;
  const expenseCategoryOptions = buildHierarchicalCategories(
    (categories ?? []).filter((item) => item.kind === "expense"),
    language
  );
  const incomeCategoryOptions = buildHierarchicalCategories(
    (categories ?? []).filter((item) => item.kind === "income"),
    language
  );

  return (
    <div className="space-y-3">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className={`min-w-0 flex-1 ${isSearching ? "pointer-events-none opacity-50" : ""}`}>
          <MonthSelector
            month={month}
            onChange={(value) => {
              setMonth(value);
              setPage(1);
            }}
          />
        </div>
        <div className={isSearching ? "pointer-events-none opacity-50" : ""}>
          <YearSelector
            years={years ?? [now.getFullYear()]}
            year={year}
            onChange={(value) => {
              setYear(value);
              setPage(1);
            }}
          />
        </div>
      </div>

      <Input
        value={searchInput}
        onChange={(event) => setSearchInput(event.target.value)}
        placeholder={t("transactions.searchPlaceholder")}
      />
      {isSearching && <p className="text-xs text-text-muted">{t("transactions.searchAcrossAllTime")}</p>}

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        <Select
          value={type}
          onChange={(event) => {
            setType(event.target.value as TransactionType | "");
            setPage(1);
          }}
        >
          <option value="">{t("transactions.allTypes")}</option>
          <option value="expense">{t("transactions.expense")}</option>
          <option value="income">{t("transactions.income")}</option>
          <option value="transfer">{t("transactions.transfer")}</option>
        </Select>
        <Select
          value={category}
          onChange={(event) => {
            setCategory(event.target.value);
            setPage(1);
          }}
        >
          <option value="">{t("transactions.allCategories")}</option>
          {expenseCategoryOptions.length > 0 && (
            <optgroup label={t("reports.expenseGroup")}>
              {expenseCategoryOptions.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.indented ? `    ↳ ` : ""}
                  {translateCategoryName(option.name)}
                </option>
              ))}
            </optgroup>
          )}
          {incomeCategoryOptions.length > 0 && (
            <optgroup label={t("reports.incomeGroup")}>
              {incomeCategoryOptions.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.indented ? `    ↳ ` : ""}
                  {translateCategoryName(option.name)}
                </option>
              ))}
            </optgroup>
          )}
        </Select>
        {tags && tags.length > 0 && (
          <Select
            value={tag}
            onChange={(event) => {
              setTag(event.target.value);
              setPage(1);
            }}
          >
            <option value="">{t("transactions.allTags")}</option>
            {tags.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </Select>
        )}
        <Select
          value={sort}
          onChange={(event) => {
            setSort(event.target.value as TransactionSort);
            setPage(1);
          }}
        >
          {TRANSACTION_SORTS.map((value) => (
            <option key={value} value={value}>
              {value === "date_desc"
                ? t("transactions.sortDateDesc")
                : value === "amount_desc"
                  ? t("transactions.sortAmountDesc")
                  : t("transactions.sortAmountAsc")}
            </option>
          ))}
        </Select>
      </div>

      {isError && <p className="py-4 text-center text-sm text-danger">{t("transactions.failedToLoad")}</p>}
      {isLoading ? (
        <p className="py-8 text-center text-sm text-text-muted">{t("common.loading")}</p>
      ) : data && data.items.length === 0 ? (
        <p className="py-8 text-center text-sm text-text-muted">{t("transactions.noneFound")}</p>
      ) : (
        <ul className="max-h-[40vh] divide-y divide-gridline overflow-y-auto">
          {data?.items.map((transaction) => (
            <li key={transaction.id} className="flex items-center gap-3 py-2">
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium text-text-primary">
                  {transaction.description}
                </span>
                <span className="block truncate text-xs text-text-muted">
                  {formatTransactionDate(transaction.date, isSearching)} · {transaction.account.name}
                </span>
              </span>
              <span className="shrink-0 text-sm font-medium tabular-nums text-text-primary">
                {formatCurrency(transaction.amount)}
              </span>
              <button
                type="button"
                aria-label={t("recurring.post.pickTransaction")}
                disabled={disabled}
                onClick={() => onPick(transaction)}
                className="shrink-0 rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-success disabled:opacity-50"
              >
                <Check size={15} />
              </button>
            </li>
          ))}
        </ul>
      )}

      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-3 text-sm">
          <Button type="button" variant="secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>
            {t("common.back")}
          </Button>
          <span className="text-text-muted">{t("common.pageOf", { page, total: totalPages })}</span>
          <Button type="button" variant="secondary" disabled={page >= totalPages} onClick={() => setPage(page + 1)}>
            {t("common.next")}
          </Button>
        </div>
      )}
    </div>
  );
}

