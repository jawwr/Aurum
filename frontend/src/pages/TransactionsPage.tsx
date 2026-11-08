import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { FileUp, Plus, Search, X } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input, Select } from "@/components/ui/Input";
import { MonthSelector } from "@/components/layout/MonthSelector";
import { YearSelector } from "@/components/layout/YearSelector";
import { TransactionsTable } from "@/components/transactions/TransactionsTable";
import { TransactionFormModal } from "@/components/transactions/TransactionFormModal";
import { useTransactions, useDeleteTransaction, useTransactionYears } from "@/hooks/useTransactions";
import { useCategories } from "@/hooks/useCategories";
import { useTags } from "@/hooks/useTags";
import { TRANSACTION_SORTS, type TransactionSort } from "@/api/transactions";
import { usePageParams } from "@/hooks/usePageParams";
import { useTranslation } from "@/lib/i18n";
import { buildHierarchicalCategories, translateCategoryName } from "@/lib/categoryLabels";
import { enumParam, monthParam, optionalIntParam, pageParam, stringParam, yearParam } from "@/lib/pageParams";
import type { Transaction, TransactionType } from "@/types";

const PAGE_SIZE = 20;

const TRANSACTION_TYPES: ReadonlyArray<TransactionType | ""> = ["", "expense", "income", "transfer"];

// Query params mirror what the transactions request sends; also kept in
// localStorage. The Dashboard's "All transactions" link deep-links here with
// just ?year=&month= — the URL wins, everything else falls back to defaults.
const PARAM_SCHEMA = {
  year: yearParam(),
  month: monthParam(),
  type: enumParam<TransactionType | "">(TRANSACTION_TYPES, ""),
  category: optionalIntParam(),
  tag: optionalIntParam(),
  sort: enumParam<TransactionSort>(TRANSACTION_SORTS, "date_desc"),
  page: pageParam(),
  search: stringParam(),
};

export function TransactionsPage() {
  const { t, language } = useTranslation();
  const now = new Date();
  const [{ year, month, type, category, tag, sort, page, search }, setParams] = usePageParams(
    "transactions",
    PARAM_SCHEMA
  );
  const categoryId = category ?? "";
  const tagId = tag ?? "";

  // Raw text follows every keystroke; the debounced value (the `search`
  // query param) is what actually drives the query, so we're not refetching
  // on every character typed. Starts from the param so a restored/deep-linked
  // search shows up in the box.
  const [searchInput, setSearchInput] = useState(search);
  useEffect(() => {
    const timeout = setTimeout(() => {
      const trimmed = searchInput.trim();
      // Functional patch: no-op when nothing changed, so mounting with a
      // restored search doesn't reset the restored page back to 1.
      setParams((prev) => (prev.search === trimmed ? {} : { search: trimmed, page: 1 }));
    }, 300);
    return () => clearTimeout(timeout);
  }, [searchInput, setParams]);
  const isSearching = search.length > 0;

  const [modalOpen, setModalOpen] = useState(false);
  const [editingTransaction, setEditingTransaction] = useState<Transaction | null>(null);

  const { data: categories } = useCategories();
  const { data: tags } = useTags();
  const { data: years } = useTransactionYears();
  const { data, isLoading, isError } = useTransactions({
    // A search looks for a purchase from an unknown month, so it must span
    // every period instead of being boxed into the currently selected one.
    year: isSearching ? undefined : year,
    month: isSearching ? undefined : month,
    search: isSearching ? search : undefined,
    type: type || undefined,
    category_id: category ?? undefined,
    tag_id: tag ?? undefined,
    sort,
    page,
    page_size: PAGE_SIZE,
  });
  const deleteTransaction = useDeleteTransaction();

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;
  // Grouped by kind and hierarchical within each group (a subcategory right
  // under its own parent, indented) — a bare "Sweets" option next to
  // top-level categories reads as if it were one itself.
  const expenseCategoryOptions = buildHierarchicalCategories(
    (categories ?? []).filter((category) => category.kind === "expense"),
    language
  );
  const incomeCategoryOptions = buildHierarchicalCategories(
    (categories ?? []).filter((category) => category.kind === "income"),
    language
  );

  function openCreateModal() {
    setEditingTransaction(null);
    setModalOpen(true);
  }

  function openEditModal(transaction: Transaction) {
    setEditingTransaction(transaction);
    setModalOpen(true);
  }

  function handleDelete(transaction: Transaction) {
    if (window.confirm(t("transactions.confirmDelete", { description: transaction.description }))) {
      deleteTransaction.mutate(transaction.id);
    }
  }

  /** Leaves search mode and switches the month/year selectors to whichever
   * month the picked transaction is in, so the user lands back in the normal
   * browsing view with it in context instead of a flat result list. */
  function handleJumpToMonth(transaction: Transaction) {
    const date = new Date(`${transaction.date}T00:00:00`);
    setSearchInput("");
    setParams({ year: date.getFullYear(), month: date.getMonth() + 1, search: "", page: 1 });
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 flex-1 items-center gap-3">
          <div className={`min-w-0 flex-1 ${isSearching ? "pointer-events-none opacity-50" : ""}`}>
            <MonthSelector
              month={month}
              onChange={(value) => setParams({ month: value, page: 1 })}
            />
          </div>
          <div className={isSearching ? "pointer-events-none opacity-50" : ""}>
            <YearSelector
              years={years ?? [now.getFullYear()]}
              year={year}
              onChange={(value) => setParams({ year: value, page: 1 })}
            />
          </div>
        </div>
        <div className="flex gap-2">
          <Link to="/transactions/import" className="flex-1 sm:flex-none">
            <Button variant="secondary" className="w-full sm:w-auto">
              <FileUp size={16} />
              {t("transactions.importButton")}
            </Button>
          </Link>
          <Button onClick={openCreateModal} className="flex-1 sm:w-auto">
            <Plus size={16} />
            {t("transactions.addButton")}
          </Button>
        </div>
      </div>

      <div className="relative">
        <Search size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
        <Input
          value={searchInput}
          onChange={(event) => setSearchInput(event.target.value)}
          placeholder={t("transactions.searchPlaceholder")}
          className="pl-9 pr-9"
        />
        {searchInput && (
          <button
            type="button"
            aria-label={t("common.clear")}
            onClick={() => {
              setSearchInput("");
              setParams({ search: "", page: 1 });
            }}
            className="absolute right-2 top-1/2 -translate-y-1/2 rounded-md p-1 text-text-muted hover:bg-surface-2 hover:text-text-primary"
          >
            <X size={15} />
          </button>
        )}
      </div>
      {isSearching && <p className="text-xs text-text-muted">{t("transactions.searchAcrossAllTime")}</p>}

      <div className="flex flex-col gap-3 sm:flex-row">
        <Select
          value={type}
          onChange={(event) => setParams({ type: event.target.value as TransactionType | "", page: 1 })}
          className="sm:w-48"
        >
          <option value="">{t("transactions.allTypes")}</option>
          <option value="expense">{t("transactions.expense")}</option>
          <option value="income">{t("transactions.income")}</option>
          <option value="transfer">{t("transactions.transfer")}</option>
        </Select>
        <Select
          value={categoryId}
          onChange={(event) =>
            setParams({ category: event.target.value ? Number(event.target.value) : null, page: 1 })
          }
          className="sm:w-56"
        >
          <option value="">{t("transactions.allCategories")}</option>
          {expenseCategoryOptions.length > 0 && (
            <optgroup label={t("reports.expenseGroup")}>
              {expenseCategoryOptions.map((category) => (
                <option key={category.id} value={category.id}>
                  {category.indented ? `    ↳ ` : ""}
                  {translateCategoryName(category.name)}
                </option>
              ))}
            </optgroup>
          )}
          {incomeCategoryOptions.length > 0 && (
            <optgroup label={t("reports.incomeGroup")}>
              {incomeCategoryOptions.map((category) => (
                <option key={category.id} value={category.id}>
                  {category.indented ? `    ↳ ` : ""}
                  {translateCategoryName(category.name)}
                </option>
              ))}
            </optgroup>
          )}
        </Select>
        {tags && tags.length > 0 && (
          <Select
            value={tagId}
            onChange={(event) => setParams({ tag: event.target.value ? Number(event.target.value) : null, page: 1 })}
            className="sm:w-48"
          >
            <option value="">{t("transactions.allTags")}</option>
            {tags.map((tag) => (
              <option key={tag.id} value={tag.id}>
                {tag.name}
              </option>
            ))}
          </Select>
        )}
        <Select
          value={sort}
          onChange={(event) => setParams({ sort: event.target.value as TransactionSort, page: 1 })}
          className="sm:w-56"
        >
          <option value="date_desc">{t("transactions.sortDateDesc")}</option>
          <option value="amount_desc">{t("transactions.sortAmountDesc")}</option>
          <option value="amount_asc">{t("transactions.sortAmountAsc")}</option>
        </Select>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{t("nav.transactions")}</CardTitle>
          {data && <span className="text-xs text-text-muted">{t("common.totalCount", { count: data.total })}</span>}
        </CardHeader>
        <CardContent>
          {isError && <p className="py-6 text-center text-sm text-danger">{t("transactions.failedToLoad")}</p>}
          {isLoading ? (
            <p className="py-12 text-center text-sm text-text-muted">{t("common.loading")}</p>
          ) : (
            <TransactionsTable
              items={data?.items ?? []}
              onEdit={openEditModal}
              onDelete={handleDelete}
              onJumpToMonth={isSearching ? handleJumpToMonth : undefined}
            />
          )}

          {totalPages > 1 && (
            <div className="mt-4 flex items-center justify-center gap-3 text-sm">
              <Button variant="secondary" disabled={page <= 1} onClick={() => setParams({ page: page - 1 })}>
                {t("common.back")}
              </Button>
              <span className="text-text-muted">{t("common.pageOf", { page, total: totalPages })}</span>
              <Button variant="secondary" disabled={page >= totalPages} onClick={() => setParams({ page: page + 1 })}>
                {t("common.next")}
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      <TransactionFormModal open={modalOpen} onClose={() => setModalOpen(false)} transaction={editingTransaction} />
    </div>
  );
}
