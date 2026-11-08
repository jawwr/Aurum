import { useState } from "react";
import { Plus } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { RecurringList } from "@/components/recurring/RecurringList";
import { RecurringFormModal } from "@/components/recurring/RecurringFormModal";
import { RecurringPostModal } from "@/components/recurring/RecurringPostModal";
import { useDeleteRecurring, usePostRecurring, useRecurring } from "@/hooks/useRecurring";
import { useTranslation } from "@/lib/i18n";
import type { RecurringTransaction } from "@/types";

export function RecurringPage() {
  const { t } = useTranslation();
  const { data: items, isLoading } = useRecurring();
  const deleteRecurring = useDeleteRecurring();
  const postRecurring = usePostRecurring();

  const [modalOpen, setModalOpen] = useState(false);
  const [editingItem, setEditingItem] = useState<RecurringTransaction | null>(null);
  const [postingItem, setPostingItem] = useState<RecurringTransaction | null>(null);

  function openCreateModal() {
    setEditingItem(null);
    setModalOpen(true);
  }

  function openEditModal(item: RecurringTransaction) {
    setEditingItem(item);
    setModalOpen(true);
  }

  function handleDelete(item: RecurringTransaction) {
    if (window.confirm(t("recurring.confirmDelete", { name: item.description }))) {
      deleteRecurring.mutate(item.id);
    }
  }

  function handlePost(item: RecurringTransaction) {
    setPostingItem(item);
  }

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <CardTitle>{t("nav.recurring")}</CardTitle>
          <Button onClick={openCreateModal}>
            <Plus size={16} />
            {t("common.add")}
          </Button>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <p className="py-10 text-center text-sm text-text-muted">{t("common.loading")}</p>
          ) : (
            <RecurringList
              items={items ?? []}
              onPost={handlePost}
              onEdit={openEditModal}
              onDelete={handleDelete}
              isPosting={postRecurring.isPending}
            />
          )}
        </CardContent>
      </Card>

      <RecurringFormModal open={modalOpen} onClose={() => setModalOpen(false)} recurring={editingItem} />
      <RecurringPostModal
        open={postingItem !== null}
        onClose={() => setPostingItem(null)}
        recurring={postingItem}
      />
    </div>
  );
}
