import { useEffect, useMemo, useState } from "react";
import { RotateCcw, Trash2 } from "lucide-react";
import {
  downloadTrashFile,
  getTrashCard,
  type TrashCardView,
  type TrashItem,
} from "@/services/api/entities";
import {
  InfoTab,
  type DeletedCardSource,
} from "@/components/entities/candidateDetail/CandidateInfoPanel";
import {
  EntityFilesContext,
  type EntityFilesSource,
} from "@/components/entities/candidateDetail/ResumeTab";
import type { DetailSection } from "@/components/entities/candidateDetail/model";
import { parseServerDate } from "@/utils/date";

// Удалённый кандидат «как обычная карточка» (владелец, 23.10.2026: «пусть
// открывается как обычная карточка»; 06.11.2026: «должно быть 1 в 1 как и в
// обычной карточке кандидата»). Поэтому здесь не своя вёрстка, а ТА ЖЕ панель,
// что справа на «Все кандидаты» (`InfoTab`), в режиме `deleted`: данные — из
// слепка корзины (`/entities/trash/{id}/card`), файлы — из него же. Правка
// обычной карточки появляется здесь сама. Сверху — плашка «Удалён … · Вернуть».

const fmt = (iso?: string | null) =>
  iso
    ? parseServerDate(iso).toLocaleString("ru", {
        day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
      })
    : "—";

const noop = () => undefined;

export function DeletedCandidateCard({
  trashId,
  onRestore,
  restoring,
}: {
  trashId: number;
  onRestore?: (item: TrashItem) => void;
  restoring?: boolean;
}) {
  const [view, setView] = useState<TrashCardView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [detailTab, setDetailTab] = useState<DetailSection>("resume");

  useEffect(() => {
    let alive = true;
    setView(null);
    setError(null);
    getTrashCard(trashId)
      .then((v) => alive && setView(v))
      .catch((e) => {
        if (!alive) return;
        const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
        setError(detail || "Не удалось открыть карточку");
      });
    return () => {
      alive = false;
    };
  }, [trashId]);

  // Один объект на загрузку: панель следит за ним в эффектах.
  const deleted = useMemo<DeletedCardSource | null>(
    () =>
      view && {
        blocks: view.blocks,
        dispatches: view.dispatches ?? [],
        tags: view.tags ?? [],
        nameTags: view.name_tags ?? [],
      },
    [view],
  );
  const files = useMemo<EntityFilesSource | null>(
    () =>
      view && {
        list: async () => view.files,
        download: (_entityId, fileId) => downloadTrashFile(trashId, fileId),
        url: (_entityId, fileId) => `/api/entities/trash/${trashId}/files/${fileId}`,
      },
    [view, trashId],
  );

  if (error) {
    return <div className="py-16 text-center text-dark-400">{error}</div>;
  }
  if (!view || !deleted || !files) {
    return (
      <div className="py-16 flex justify-center">
        <div className="w-8 h-8 border-2 border-accent-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  const { card, trash } = view;
  const isApp = trash.kind === "application";

  return (
    <div className="bg-[var(--hf-white)] hf-dark-disabled:bg-[var(--hf-bg-dark)] rounded-hf-l overflow-hidden">
      {/* Что случилось и можно ли вернуть — над карточкой. */}
      <div className="px-[24px] pt-[24px]">
        <div
          className="flex items-center gap-3 rounded-xl border-[1.5px] px-3.5 py-2.5 text-[13px]"
          style={{ background: "#f4f4f5", borderColor: "#d4d4d8", color: "#27272a" }}
        >
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-zinc-600 text-white">
            <Trash2 className="h-4 w-4" aria-hidden="true" />
          </span>
          <div className="min-w-0 flex-1">
            <div className="text-[14px] font-bold">
              {isApp ? `Убран(а) из воронки «${trash.vacancy_title || "—"}»` : "Кандидат удалён"}
            </div>
            <div className="text-[12px] text-zinc-600">
              {trash.deleted_by_name || "—"} · {fmt(trash.deleted_at)}
              {trash.restored_at
                ? ` · возвращён: ${trash.restored_by_name || "—"}, ${fmt(trash.restored_at)}`
                : trash.restorable
                  ? ` · вернуть можно до ${fmt(trash.restorable_until)}`
                  : " · срок хранения истёк"}
              {" · только просмотр"}
            </div>
          </div>
          {trash.restorable && !trash.restored_at && onRestore && (
            <button
              type="button"
              onClick={() => onRestore(trash)}
              disabled={restoring}
              className="flex shrink-0 items-center gap-2 rounded-lg bg-accent-500 px-3.5 py-1.5 text-[12.5px] font-semibold text-white hover:bg-accent-600 disabled:opacity-50"
            >
              <RotateCcw className="h-4 w-4" />
              {restoring ? "Возвращаем…" : "Вернуть"}
            </button>
          )}
        </div>
      </div>

      <EntityFilesContext.Provider value={files}>
        <InfoTab
          card={card}
          status={card.status || ""}
          columns={[]}
          detailSection={detailTab}
          onDetailSectionChange={setDetailTab}
          onStatusChange={noop}
          onAddToVacancy={noop}
          onEdit={noop}
          deleted={deleted}
        />
      </EntityFilesContext.Provider>
    </div>
  );
}
