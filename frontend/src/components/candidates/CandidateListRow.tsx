import clsx from "clsx";
import { Archive, Check } from "lucide-react";
import type { KanbanCard, KanbanColumn } from "@/services/api/candidates";
import { APPLICATION_STAGE_LABELS } from "@/types";
import { HeadlineTagChip } from "@/components/entities/headlineTags";
import { buildListRowStages, type CandidateListFields } from "@/components/entities/candidateDetail/model";
import { STAGE_CHIP_BRIGHT_BY_STAGE } from "@/constants/hrStages";
import { formatDateFull, formatDateShort } from "@/components/candidates/candidateFormat";
import { PriorRejectionChip } from "@/components/candidates/priorRejection";
import { avatarThumbUrl } from "@/utils/avatarThumb";

// Строка списка «Все кандидаты»: аватар/галочка выбора, имя с тегами, должность,
// этапы по воронкам, компания/дата и поля из настроек списка
// (вынесено из AllCandidatesPage, 20.10.2026).

export function CandidateListRow({
  card,
  status,
  columns,
  fields,
  isSelected,
  isChecked,
  onOpen,
  onToggleCheck,
}: {
  card: KanbanCard;
  status: string;
  columns: KanbanColumn[];
  fields: CandidateListFields;
  isSelected: boolean;
  isChecked: boolean;
  onOpen: () => void;
  onToggleCheck: () => void;
}) {
  // Дата в строке — это дата ПЕРЕВОДА на текущий статус (Мария, 20.10.2026:
  // «видим статус „оффер принят“ и дату его перевода на этот статус»). Раньше
  // здесь стояла дата ДОБАВЛЕНИЯ карточки, и рядом со статусом она выглядела
  // случайной. Перевода в истории может не быть (статус выставили правкой
  // карточки) — тогда прежнее поведение: дата добавления, и только если место
  // не занято последней компанией.
  // Дата есть у КАЖДОГО (Мария, 20.10.2026: «у некоторых кандидатов вообще
  // даты нет»): перевода на текущий этап, а без такой записи — добавления.
  // Раньше при указанной компании дата добавления пряталась ради места.
  const rowDate = card.status_changed_at || card.created_at;
  const rowDateTitle = rowDate
    ? `${card.status_changed_at ? "Переведён на текущий этап" : "Добавлен"}: ${formatDateFull(rowDate)}`
    : undefined;
  // Подпись воронки: та, по которой сейчас показан статус
  // кандидата (см. status_vacancy_name на бэке). Кандидат в
  // нескольких воронках получает «+N» — видно, что есть ещё
  // (запрос юзера 17.09).
  const listFunnelName =
    card.status_vacancy_name || card.vacancy_name;
  // Этапы по воронкам прямо в строке: «Выполняет ТЗ · Трафик,
  // Отказ · UAM» (решение юзера 17.09 — видно всё, не открывая
  // карточку). Больше трёх — прячем под «+N».
  // Кандидат вне воронок раньше оставался в строке БЕЗ чипа
  // этапа — по списку было не понять, где человек (запрос
  // владельца 23.09.2026). Теперь у таких показываем их
  // общий статус, без названия воронки.
  const listRowStages = buildListRowStages(
    card.funnels,
    status,
    columns,
    APPLICATION_STAGE_LABELS as Record<string, string>,
  );
  const listFunnels = listRowStages.slice(0, 3);
  const listFunnelsHidden = Math.max(
    listRowStages.length - listFunnels.length,
    0,
  );
  const listExtraFunnels = Math.max(
    (card.funnel_count || 0) - 1,
    0,
  );
  const listMetaPrimary =
    (fields.lastCompany ? card.company : undefined) ||
    (listFunnels.length ? undefined : listFunnelName);
  return (
    <div
      key={card.id}
      onClick={onOpen}
      className={clsx(
        "hf-candidate-row",
        isChecked || isSelected
          ? "hf-candidate-row-selected"
          : "hf-candidate-row-idle",
      )}
    >
      {/* Avatar / checkmark zone (LEFT) — hover ONLY on avatar shows checkmark and cancels card border */}
      <div
        onClick={(e) => {
          e.stopPropagation();
          onToggleCheck();
        }}
        className="hf-candidate-avatar-zone"
      >
        {isChecked ? (
          card.photo_url ? (
            <div className="hf-candidate-avatar-check">
              <img
                src={avatarThumbUrl(card.photo_url)}
                alt={card.name}
                referrerPolicy="no-referrer"
                className="hf-candidate-avatar-check-img"
                onError={(e) => {
                  (
                    e.currentTarget as HTMLImageElement
                  ).style.display = "none";
                }}
              />
              <div className="hf-candidate-avatar-check-overlay">
                <Check className="hf-candidate-check-icon" />
              </div>
            </div>
          ) : (
            <div className="hf-candidate-avatar-check">
              <Check className="hf-candidate-check-icon" />
            </div>
          )
        ) : (
          <>
            {card.photo_url ? (
              <img
                src={avatarThumbUrl(card.photo_url)}
                alt={card.name}
                loading="lazy"
                decoding="async"
                referrerPolicy="no-referrer"
                className="hf-candidate-avatar"
                onError={(e) => {
                  (
                    e.currentTarget as HTMLImageElement
                  ).style.display = "none";
                }}
              />
            ) : (
              <div className="hf-candidate-avatar-fallback">
                <span className="hf-candidate-avatar-head" />
                <span className="hf-candidate-avatar-body" />
              </div>
            )}
            <div className="hf-candidate-avatar-hover">
              <Check className="hf-candidate-check-icon" />
            </div>
          </>
        )}
      </div>
      {/* Text column (RIGHT) — name, position, company/date */}
      <div className="hf-candidate-row-copy">
        <div className="flex flex-wrap items-center gap-1.5 min-w-0">
          <div className="hf-candidate-row-name" title={card.name}>
            {card.name}
          </div>
          {/* Яркие теги-ярлыки у имени (HR вписывает сам) —
              read-only в списке, редактируются в карточке.
              Показываем ВСЕ (запрос HR 16.09: «чтобы все метки
              рядом с кандидатом подсвечивались»); не влезли —
              переносятся на следующую строку, имя не сжимается. */}
          {(card.headline_tags || []).map((t, i) => (
            <span key={i} className="shrink-0">
              <HeadlineTagChip tag={t} small />
            </span>
          ))}
          {/* Из теневой базы: попадает в список ТОЛЬКО при поиске.
              Метим явно, чтобы не путать с активными. */}
          {card.is_archived && (
            <span
              className="shrink-0 inline-flex items-center gap-1 rounded px-1.5 py-[1px] text-[10px] font-medium leading-[14px] bg-[color:var(--hf-main-200)] text-[var(--hf-main-700)] hf-dark-disabled:bg-[color:var(--hf-white-alpha-12)] hf-dark-disabled:text-[color:var(--hf-white-alpha-70)]"
              title="Кандидат из архива (теневая база) — найден поиском"
            >
              <Archive className="w-[9px] h-[9px]" />
              Архив
            </span>
          )}
        </div>
        {fields.lastPosition && card.position && (
          <div className="hf-candidate-row-subtitle">
            {card.position}
          </div>
        )}
        {listFunnels.length > 0 && (
          <div className="mt-[2px] flex flex-wrap items-center gap-x-[6px] gap-y-[2px]">
            {listFunnels.map((f, i) => (
              <span
                key={`${f.vacancyTitle ?? "own"}-${i}`}
                className="inline-flex max-w-full items-center gap-[4px] text-[length:var(--hf-fs-2xs)] text-[color:var(--hf-alpha-600)] hf-dark-disabled:text-[color:var(--hf-white-alpha-45)]"
                title={
                  f.vacancyTitle
                    ? `${f.label} · ${f.vacancyTitle}`
                    : `${f.label} · кандидат ни в одной воронке`
                }
              >
                <span
                  className={clsx(
                    "inline-flex shrink-0 items-center rounded-[20px] px-[6px] py-[1px] font-semibold",
                    STAGE_CHIP_BRIGHT_BY_STAGE[f.stage] ||
                      "bg-[var(--hf-status-gray)] text-[#111827]",
                  )}
                >
                  {f.label}
                </span>
                {f.vacancyTitle && (
                  <span className="truncate">{f.vacancyTitle}</span>
                )}
              </span>
            ))}
            {listFunnelsHidden > 0 && (
              <span className="text-[length:var(--hf-fs-2xs)] text-[color:var(--hf-accent)]">
                +{listFunnelsHidden}
              </span>
            )}
          </div>
        )}
        {/* «Был отказ» — человек уже отклонён в другой своей карточке или в
            архиве (владелец, 22.10.2026): видно, не открывая карточку. */}
        {card.prior_rejection && (
          <div className="mt-[3px] flex min-w-0">
            <PriorRejectionChip pr={card.prior_rejection} />
          </div>
        )}
        <div className="hf-candidate-row-meta">
          {listMetaPrimary && (
            <span
              className="hf-candidate-row-meta-text"
              title={listMetaPrimary}
            >
              {listMetaPrimary}
            </span>
          )}
          {listFunnels.length === 0 && listExtraFunnels > 0 && (
            <span
              className="hf-candidate-row-meta-text shrink-0 text-[color:var(--hf-accent)]"
              title={`Кандидат ещё в ${listExtraFunnels} воронке(ах) — этапы видны в карточке`}
            >
              +{listExtraFunnels}
            </span>
          )}
          {listMetaPrimary &&
            rowDate && (
              <span className="hf-candidate-row-meta-dot">
                ·
              </span>
            )}
          {rowDate && (
            <span className="hf-candidate-row-date" title={rowDateTitle}>
              {formatDateShort(rowDate)}
            </span>
          )}
        </div>
        {/* F7: доп. поля списка по настройке (если есть в данных карточки) */}
        {(() => {
          const extras = [
            fields.desiredSalary && card.salary,
            fields.age && card.age,
            fields.experience && card.total_experience,
            fields.source && card.source,
          ].filter(Boolean) as string[];
          if (!extras.length) return null;
          return (
            <div className="hf-candidate-row-meta">
              {extras.map((t, ei) => (
                <span key={ei} className="hf-candidate-row-meta-text" title={t}>{t}</span>
              ))}
            </div>
          );
        })()}
        {fields.tags && card.tags && card.tags.length > 0 && (
          <div className="hf-candidate-row-meta" style={{ flexWrap: "wrap" }}>
            {card.tags.slice(0, 6).map((tag, ti) => (
              <span key={ti} className="hf-candidate-row-meta-text">#{tag}</span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
