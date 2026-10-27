import { useEffect, useMemo, useState } from "react";
import { ExternalLink, Lock, MapPin, RotateCcw, Trash2 } from "lucide-react";
import clsx from "clsx";
import {
  downloadTrashFile,
  getTrashCard,
  type TrashCardView,
  type TrashItem,
} from "@/services/api/entities";
import CandidateVacancyCard from "@/components/entities/CandidateVacancyCard";
import {
  buildStageContainers,
  readSystemHrTags,
  resolveContainerStatusLabel,
} from "@/components/entities/candidateDetail/model";
import { HuntflowInfoRow as InfoRow } from "@/components/hr/HuntflowControls";
import { formatPhoneDisplay, getInitials } from "@/components/candidates/candidateFormat";
import { parseServerDate } from "@/utils/date";

// Удалённый кандидат «как обычная карточка» (владелец, 23.10.2026: «нельзя ли
// открывать удалённые карточки, чтобы их просмотреть»; «пусть открывается как
// обычная карточка»). Данные — из слепка корзины (`/entities/trash/{id}/card`),
// вид — те же части, что у живой карточки: шапка с контактами, блоки воронок
// (`CandidateVacancyCard`) с историей и комментариями, файлы. Только чтение:
// менять нечего, кандидата нет — сверху плашка «Удалён(а) … · Вернуть».

const fmt = (iso?: string | null) =>
  iso
    ? parseServerDate(iso).toLocaleString("ru", {
        day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
      })
    : "—";

const noop = () => undefined;

function Value({ children }: { children: React.ReactNode }) {
  return (
    <span className="text-[var(--hf-main-900)] hf-dark-disabled:text-[var(--hf-dark-200)]">{children}</span>
  );
}

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

  const containers = useMemo(() => {
    if (!view) return [];
    const card = view.card;
    return buildStageContainers({
      card,
      status: card.status || "",
      liveApplicationId: view.blocks[0]?.application_id ?? 0,
      liveEvents: view.blocks[0]?.events,
      liveVacancyTitle: view.blocks[0]?.vacancy_title ?? null,
      liveBlocks: view.blocks,
      allEntityFiles: view.files,
      livePinnedEntryKey: (card.extra_data?.pinned_entry_key as string | undefined) ?? null,
    });
  }, [view]);

  if (error) {
    return <div className="py-16 text-center text-dark-400">{error}</div>;
  }
  if (!view) {
    return (
      <div className="py-16 flex justify-center">
        <div className="w-8 h-8 border-2 border-accent-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  const { card, trash } = view;
  const isApp = trash.kind === "application";
  const summary = typeof card.extra_data?.summary === "string" ? card.extra_data.summary.trim() : "";
  const hrTags = readSystemHrTags(card.extra_data);

  return (
    <div className="hf-profile-panel">
      {/* Что случилось и можно ли вернуть — вместо ряда действий живой карточки. */}
      <div
        className="mb-4 flex items-center gap-3 rounded-xl border-[1.5px] px-3.5 py-2.5 text-[13px]"
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

      {/* Шапка — те же строки, что у живой карточки, без правки. */}
      <div className="hf-profile-summary">
        <div className="hf-profile-summary-copy">
          <h2 className="hf-profile-title">{card.name}</h2>
          {(card.position || card.company) && (
            <p className="hf-profile-subtitle">
              {card.position}
              {card.position && card.company && <span className="mx-1.5 opacity-50">&bull;</span>}
              {card.company}
            </p>
          )}
          {card.phone && <InfoRow label="Телефон"><Value>{formatPhoneDisplay(card.phone)}</Value></InfoRow>}
          {card.email && <InfoRow label="Эл. почта"><Value>{card.email}</Value></InfoRow>}
          {card.telegram_username && <InfoRow label="Telegram"><Value>{card.telegram_username}</Value></InfoRow>}
          {card.age && <InfoRow label="Возраст"><Value>{card.age}</Value></InfoRow>}
          {card.city && (
            <InfoRow label="Город">
              <span className="inline-flex items-center gap-1 text-[var(--hf-main-900)]">
                <MapPin className="w-3.5 h-3.5 text-[var(--hf-main-500)]" />
                {card.city}
              </span>
            </InfoRow>
          )}
          {card.salary && <InfoRow label="Зарплата"><Value>{card.salary}</Value></InfoRow>}
          {card.total_experience && <InfoRow label="Опыт"><Value>{card.total_experience}</Value></InfoRow>}
          {(card.source || card.source_url) && (
            <InfoRow label="Источник">
              {card.source_url ? (
                <a href={card.source_url} target="_blank" rel="noopener noreferrer"
                  className="text-[var(--hf-cyan-700)] inline-flex items-center gap-1 hover:underline">
                  {card.source || "Ссылка"} <ExternalLink className="w-3 h-3" />
                </a>
              ) : (
                <Value>{card.source}</Value>
              )}
            </InfoRow>
          )}
          {summary && (
            <InfoRow label="О себе">
              <span className="whitespace-pre-wrap break-words text-[var(--hf-main-900)]">{summary}</span>
            </InfoRow>
          )}
          {(hrTags.length > 0 || (card.tags || []).length > 0) && (
            <InfoRow label="Метки">
              <div className="flex flex-wrap items-center gap-1.5">
                {hrTags.map((hr) => (
                  <span key={`hr-${hr.hr_id}-${hr.vacancy_id ?? ""}`}
                    className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-[var(--hf-bg-panel)] text-[var(--hf-main-900)] border border-[color:var(--hf-main-200)]">
                    <Lock className="w-3 h-3 opacity-50" />
                    HR: {hr.name}{hr.vacancy_title ? ` · ${hr.vacancy_title}` : ""}
                  </span>
                ))}
                {(card.tags || []).map((t) => (
                  <span key={t} className="px-2 py-0.5 rounded-full text-xs font-medium bg-[var(--hf-cyan-50)] text-[var(--hf-cyan-700)] border border-[var(--hf-cyan-200)]">
                    {t}
                  </span>
                ))}
              </div>
            </InfoRow>
          )}
        </div>
        {card.photo_url ? (
          <img
            src={card.photo_url}
            alt={card.name}
            referrerPolicy="no-referrer"
            className="hf-profile-photo"
            onError={(e) => {
              const el = e.currentTarget as HTMLImageElement;
              el.style.display = "none";
              el.nextElementSibling?.classList.remove("hidden");
            }}
          />
        ) : null}
        <div className={clsx("hf-profile-photo", !card.photo_url && "hf-profile-photo-fallback", card.photo_url && "hidden")}>
          {getInitials(card.name)}
        </div>
      </div>

      {/* Воронки с историей и комментариями — тем же блоком, что в живой
          карточке, только без действий. */}
      {containers.map((c) => (
        <CandidateVacancyCard
          key={`${c.origin}-${c.applicationId}`}
          card={card}
          applicationId={c.applicationId}
          vacancyTitle={c.vacancyTitle}
          currentStage={c.status}
          notes={c.notes}
          events={c.events}
          addedAt={c.addedAt}
          recruiter={c.recruiter}
          readonly
          dimmed={c.origin === "merged"}
          snapshot={c.origin === "merged"}
          stageOptions={[]}
          getStageLabel={(stage) => resolveContainerStatusLabel(stage, [])}
          onChangeStage={noop}
          onComment={async () => false}
          onDeleteHistory={noop}
          onUploadFile={noop}
          pinnedEntryKey={c.pinnedEntryKey}
          files={c.files}
          downloadFile={(fileId) => downloadTrashFile(trashId, fileId)}
          fileUrlOf={(fileId) => `/api/entities/trash/${trashId}/files/${fileId}`}
        />
      ))}
    </div>
  );
}
