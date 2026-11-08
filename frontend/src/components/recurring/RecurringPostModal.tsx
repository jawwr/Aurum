import { useEffect, useState } from "react";
import { Dialog } from "@/components/ui/Dialog";
import { Button } from "@/components/ui/Button";
import { TransactionPicker } from "@/components/recurring/TransactionPicker";
import { usePostRecurring } from "@/hooks/useRecurring";
import { useTranslation } from "@/lib/i18n";
import type { RecurringTransaction } from "@/types";

interface RecurringPostModalProps {
  open: boolean;
  onClose: () => void;
  recurring: RecurringTransaction | null;
}

export function RecurringPostModal({ open, onClose, recurring }: RecurringPostModalProps) {
  const { t } = useTranslation();
  const postRecurring = usePostRecurring();
  const [step, setStep] = useState<"choose" | "pick">("choose");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setStep("choose");
    setError(null);
  }, [open, recurring]);

  if (!recurring) return null;

  async function post(item: RecurringTransaction, transactionId: number | null) {
    setError(null);
    try {
      await postRecurring.mutateAsync({ id: item.id, transactionId });
      onClose();
    } catch {
      setError(t("recurring.post.error"));
    }
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={step === "choose" ? t("recurring.post.title") : t("recurring.post.pickTitle")}
      className={step === "pick" ? "sm:max-w-2xl" : undefined}
    >
      {step === "choose" ? (
        <div className="space-y-3">
          <p className="text-sm text-text-muted">{recurring.description}</p>
          <Button className="w-full" disabled={postRecurring.isPending} onClick={() => post(recurring, null)}>
            {t("recurring.post.createNew")}
          </Button>
          <Button
            variant="secondary"
            className="w-full"
            disabled={postRecurring.isPending}
            onClick={() => setStep("pick")}
          >
            {t("recurring.post.addExisting")}
          </Button>
        </div>
      ) : (
        <div className="space-y-3">
          <TransactionPicker
            disabled={postRecurring.isPending}
            onPick={(transaction) => post(recurring, transaction.id)}
          />
          <div className="flex justify-start">
            <Button type="button" variant="ghost" onClick={() => setStep("choose")}>
              {t("common.back")}
            </Button>
          </div>
        </div>
      )}
      {error && <p className="mt-3 text-sm text-danger">{error}</p>}
    </Dialog>
  );
}
