import { Archive, ExternalLink, Loader2, Upload, UserCheck } from 'lucide-react';
import api from '@/services/api/client';
import { STAGE_CHIP_BRIGHT_BY_STAGE } from '@/constants/hrStages';
import { PriorRejectionBanner, type PriorRejection } from './priorRejection';

// «Уже есть в базе» ДО создания карточки — окна «Загрузка из файла» и «Новый
// кандидат» (22.10.2026). Сервер — POST /entities/check-duplicate: тот же
// матчер и тот же ответ, что у расширения (активные с этапами по воронкам,
// архив, «возможно тот же», «Был отказ»). Раньше окно загрузки искало похожих
// обычным поиском по имени (без архива; рядовой рекрутёр — только своих), а
// ручная форма не проверяла ничего — так на проде и копились вторые карточки.

export interface DuplicateCheckResult {
  is_duplicate: boolean;
  duplicates: Array<{
    entity_id: number;
    name: string;
    email?: string | null;
    phone?: string | null;
    status: string;
    status_key?: string;
    applications: Array<{ vacancy_title: string; stage: string; stage_key?: string }>;
  }>;
  has_archive_match: boolean;
  archive_match_id?: number | null;
  soft_match: boolean;
  soft_confidence: number;
  soft_reasons: string[];
  soft_match_id?: number | null;
  prior_rejection?: PriorRejection | null;
}

export async function checkDuplicateBeforeCreate(data: {
  full_name?: string;
  email?: string;
  phone?: string;
  telegram?: string;
  source_url?: string;
}): Promise<DuplicateCheckResult> {
  const { data: res } = await api.post<DuplicateCheckResult>('/entities/check-duplicate', data);
  return res;
}

export function hasAnyMatch(r: DuplicateCheckResult | null): boolean {
  return !!r && (r.duplicates.length > 0 || r.has_archive_match || r.soft_match || !!r.prior_rejection);
}

export function ExistingCandidatesPanel({
  result,
  loading,
  onOpen,
  onAttach,
  attaching,
}: {
  result: DuplicateCheckResult | null;
  loading?: boolean;
  /** Открыть карточку (archived — архивная, по ссылке с ?archived=1). */
  onOpen: (entityId: number, archived?: boolean) => void;
  /** Окно загрузки: прикрепить резюме к найденной карточке вместо новой. */
  onAttach?: (entityId: number) => void;
  attaching?: boolean;
}) {
  if (loading) {
    return (
      <div className="flex items-center gap-2 text-slate-400 text-sm py-2">
        <Loader2 className="w-4 h-4 animate-spin" />
        Проверяем, нет ли его уже в базе…
      </div>
    );
  }
  if (!result || !hasAnyMatch(result)) return null;
  const softShown = result.soft_match && !result.is_duplicate && result.soft_match_id;
  return (
    <div className="space-y-2">
      <h3 className="text-sm font-medium text-slate-600 flex items-center gap-2">
        <UserCheck className="w-4 h-4" />
        Уже есть в базе
      </h3>
      {result.prior_rejection && (
        <PriorRejectionBanner
          items={[result.prior_rejection]}
          onOpenCard={(id) => onOpen(id, result.prior_rejection?.archived)}
        />
      )}
      {result.duplicates.map((d) => (
        <div key={d.entity_id} className="flex items-start justify-between gap-3 p-3 bg-slate-50 rounded-lg">
          <div className="min-w-0">
            <p className="text-sm font-medium text-slate-900 truncate">{d.name}</p>
            {(d.email || d.phone) && (
              <p className="text-xs text-slate-400 truncate">{[d.email, d.phone].filter(Boolean).join(' · ')}</p>
            )}
            <div className="mt-1 flex flex-wrap gap-1">
              {(d.applications.length ? d.applications : [{ vacancy_title: '', stage: d.status, stage_key: d.status_key }])
                .slice(0, 3)
                .map((a, i) => (
                  <span key={i} className="inline-flex items-center gap-1 text-[11px] text-slate-500">
                    <span
                      className={`rounded-[20px] px-[6px] py-[1px] font-semibold ${
                        STAGE_CHIP_BRIGHT_BY_STAGE[a.stage_key || ''] || 'bg-[var(--hf-status-gray)] text-[#111827]'
                      }`}
                    >
                      {a.stage}
                    </span>
                    {a.vacancy_title}
                  </span>
                ))}
            </div>
          </div>
          <div className="flex shrink-0 flex-col gap-1.5">
            {onAttach && (
              <button
                type="button"
                onClick={() => onAttach(d.entity_id)}
                disabled={attaching}
                className="px-3 py-1.5 text-xs font-medium bg-[var(--hf-green-600)] hover:bg-[var(--hf-green-500)] text-slate-900 rounded-lg transition-colors disabled:opacity-50 flex items-center gap-1.5"
              >
                {attaching ? <Loader2 className="w-3 h-3 animate-spin" /> : <Upload className="w-3 h-3" />}
                Прикрепить
              </button>
            )}
            <button
              type="button"
              onClick={() => onOpen(d.entity_id)}
              className="px-3 py-1.5 text-xs font-medium border border-slate-200 rounded-lg text-slate-700 hover:bg-white flex items-center gap-1.5"
            >
              <ExternalLink className="w-3 h-3" />
              Открыть
            </button>
          </div>
        </div>
      ))}
      {softShown && (
        <button
          type="button"
          onClick={() => onOpen(result.soft_match_id as number)}
          className="w-full text-left p-3 rounded-lg text-xs"
          style={{ background: '#fef3c7', color: '#92400e' }}
        >
          <b>Возможно, тот же человек · {Math.round(result.soft_confidence)}%</b>
          {result.soft_reasons.length > 0 && ` — ${result.soft_reasons.join(', ')}`}
          <span className="underline ml-1">открыть</span>
        </button>
      )}
      {result.has_archive_match && result.archive_match_id && (
        <button
          type="button"
          onClick={() => onOpen(result.archive_match_id as number, true)}
          className="w-full text-left p-3 rounded-lg text-xs bg-slate-100 text-slate-600 flex items-center gap-2"
        >
          <Archive className="w-3.5 h-3.5 shrink-0" />
          Похожий кандидат есть в архиве <span className="underline">открыть</span>
        </button>
      )}
    </div>
  );
}
