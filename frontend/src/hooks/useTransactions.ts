import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  bulkCreateTransactions,
  createTransaction,
  deleteTransaction,
  fetchAllTransactionsInRange,
  fetchTransactions,
  fetchTransactionYears,
  fetchTransactionsTotal,
  updateTransaction,
  type TransactionFilters,
  type TransactionTotalFilters,
} from "@/api/transactions";
import type { TransactionInput } from "@/types";

function useInvalidateAfterTransactionChange() {
  const queryClient = useQueryClient();
  return () => {
    queryClient.invalidateQueries({ queryKey: ["transactions"] });
    // Linking, unlinking or deleting a linked transaction changes whether
    // its recurring payment counts as paid.
    queryClient.invalidateQueries({ queryKey: ["recurring"] });
    // Without this, a second CSV import of the same date range within
    // staleTime (see main.tsx) would check for duplicates against a cached
    // list from *before* the first import finished — and find none, which
    // is exactly the case the duplicate check exists to catch.
    queryClient.invalidateQueries({ queryKey: ["transactions-duplicate-check"] });
    queryClient.invalidateQueries({ queryKey: ["transaction-years"] });
    queryClient.invalidateQueries({ queryKey: ["transactions-total"] });
    queryClient.invalidateQueries({ queryKey: ["dashboard-summary"] });
    queryClient.invalidateQueries({ queryKey: ["net-worth-summary"] });
    queryClient.invalidateQueries({ queryKey: ["category-spending-report"] });
    queryClient.invalidateQueries({ queryKey: ["category-ranking"] });
    queryClient.invalidateQueries({ queryKey: ["budget-status"] });
    queryClient.invalidateQueries({ queryKey: ["financial-alerts"] });
    queryClient.invalidateQueries({ queryKey: ["advice"] });
    queryClient.invalidateQueries({ queryKey: ["cash-flow"] });
  };
}

export function useTransactions(filters: TransactionFilters) {
  return useQuery({
    queryKey: ["transactions", filters],
    queryFn: () => fetchTransactions(filters),
  });
}

/** Net total of every transaction matching the current filters (income
 * +, expense -, transfer 0). The filters object intentionally omits page
 * and sort — the total doesn't depend on them, so react-query refetches
 * only when the period/type/category/tag/search filters change, not on
 * every page flip or sort toggle. */
export function useTransactionsTotal(filters: TransactionTotalFilters) {
  return useQuery({
    queryKey: ["transactions-total", filters],
    queryFn: () => fetchTransactionsTotal(filters),
  });
}

/** CSV import's duplicate check (see pages/CsvImportPage.tsx) — every
 * existing transaction for one account within the imported date range, so
 * re-importing an overlapping bank export can be told apart from new rows. */
export function useTransactionsForDuplicateCheck(
  accountId: number | null,
  startDate: string | null,
  endDate: string | null
) {
  return useQuery({
    queryKey: ["transactions-duplicate-check", accountId, startDate, endDate],
    queryFn: () => fetchAllTransactionsInRange({ account_id: accountId!, start_date: startDate!, end_date: endDate! }),
    enabled: accountId !== null && startDate !== null && endDate !== null,
  });
}

export function useTransactionYears() {
  return useQuery({
    queryKey: ["transaction-years"],
    queryFn: fetchTransactionYears,
  });
}

export function useCreateTransaction() {
  const invalidate = useInvalidateAfterTransactionChange();
  return useMutation({
    mutationFn: (input: TransactionInput) => createTransaction(input),
    onSuccess: invalidate,
  });
}

export function useUpdateTransaction() {
  const invalidate = useInvalidateAfterTransactionChange();
  return useMutation({
    mutationFn: ({ id, input }: { id: number; input: Partial<TransactionInput> }) =>
      updateTransaction(id, input),
    onSuccess: invalidate,
  });
}

export function useBulkCreateTransactions() {
  const invalidate = useInvalidateAfterTransactionChange();
  return useMutation({
    mutationFn: (items: TransactionInput[]) => bulkCreateTransactions(items),
    onSuccess: invalidate,
  });
}

export function useDeleteTransaction() {
  const invalidate = useInvalidateAfterTransactionChange();
  return useMutation({
    mutationFn: (id: number) => deleteTransaction(id),
    onSuccess: invalidate,
  });
}
