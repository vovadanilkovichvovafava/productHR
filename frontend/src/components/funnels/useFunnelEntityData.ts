import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { KanbanCard } from "@/services/api/candidates";
import {
  getEntity,
  getEntityActivity,
  getEntityFiles,
  type EntityFile,
  type VacancyActivityBlock as ActivityBlockData,
} from "@/services/api/entities";
import { buildResumeSources } from "@/components/entities/candidateDetail/model";

// Данные кандидата, открытого в воронке: лента по воронкам, файлы, extra_data,
// карточка для баннера дублей, источники резюме и тихий опрос раз в 15с
// (вынесено из RecruiterFunnelsPage, 20.10.2026, без изменения поведения).

export function useFunnelEntityData(
  entityId: number | null,
  fetchVacancies: (silent?: boolean) => unknown,
) {
  // Лента активности ПРИВЯЗАНА к кандидату, для которого загружена. Раньше это был
  // голый массив: при переключении кандидата в нём до ответа сервера (или навсегда,
  // если опоздавший ответ прошлого кандидата прилетал позже) лежала лента ДРУГОГО
  // человека, и карточка брала оттуда application_id — «Отказ» уходил чужой заявке
  // в той же воронке, а комментарий «Этап: Отказ» — выбранному (2026-09-15, Мария:
  // «поставила отказ, а висит в Выполняет ТЗ»).
  const [activityState, setActivityState] = useState<{ entityId: number | null; blocks: ActivityBlockData[] }>({ entityId: null, blocks: [] });
  const activityEntityRef = useRef<number | null>(null);
  const [dupCard, setDupCard] = useState<KanbanCard | null>(null);
  const [entityFiles, setEntityFiles] = useState<EntityFile[]>([]);
  const [filesLoading, setFilesLoading] = useState(false);
  const [entityExtraData, setEntityExtraData] = useState<Record<string, unknown> | null>(null);

  // Load cross-vacancy activity feed when entity changes
  useEffect(() => {
    const eid = entityId;
    activityEntityRef.current = eid;
    setActivityState({ entityId: eid, blocks: [] });
    if (!eid) return;
    getEntityActivity(eid)
      .then((blocks) => {
        if (activityEntityRef.current !== eid) return; // опоздавший ответ прошлого кандидата
        setActivityState({ entityId: eid, blocks: Array.isArray(blocks) ? blocks : [] });
      })
      .catch(() => {});
  }, [entityId]);

  // Перезагрузка ленты активности после мутации в карточке вакансии +
  // обновление счётчиков досок.
  const refreshActivity = useCallback(async () => {
    const eid = entityId;
    if (eid) {
      try {
        const blocks = await getEntityActivity(eid);
        if (activityEntityRef.current === eid) {
          setActivityState({ entityId: eid, blocks: Array.isArray(blocks) ? blocks : [] });
        }
      } catch {
        /* ignore — оставляем прежнюю ленту */
      }
    }
    fetchVacancies();
  }, [entityId, fetchVacancies]);

  // Открытая карточка в воронке тоже должна оживать сама: комменты и этап,
  // изменённые на «Все кандидаты» или коллегой, раньше появлялись только после
  // F5 (2026-09-17). Тикаем раз в 15с и сразу при возврате на вкладку.
  useEffect(() => {
    const eid = entityId;
    if (!eid) return;
    const poll = () => {
      if (document.visibilityState !== 'visible') return;
      void refreshActivity();
      getEntity(eid)
        .then((fresh) => {
          if (activityEntityRef.current === eid && fresh?.extra_data) {
            setEntityExtraData(fresh.extra_data as Record<string, unknown>);
          }
        })
        .catch(() => {});
    };
    const id = window.setInterval(poll, 15000);
    const onVisible = () => {
      if (document.visibilityState === 'visible') poll();
    };
    document.addEventListener('visibilitychange', onVisible);
    window.addEventListener('focus', onVisible);
    return () => {
      window.clearInterval(id);
      document.removeEventListener('visibilitychange', onVisible);
      window.removeEventListener('focus', onVisible);
    };
  }, [entityId, refreshActivity]);

  // Load entity files (resumes) when candidate selected
  useEffect(() => {
    if (!entityId) {
      setEntityFiles([]);
      return;
    }
    setFilesLoading(true);
    getEntityFiles(entityId)
      .then(files => setEntityFiles(files))
      .catch(() => setEntityFiles([]))
      .finally(() => setFilesLoading(false));
  }, [entityId]);

  // Load entity extra_data for resume text view + дедуп-баннер в воронке.
  // silent=true (поллинг) не сбрасывает в null перед запросом — иначе фон
  // мигал бы пустотой каждые 15с.
  const loadEntityExtra = useCallback((entityId: number, silent = false) => {
    if (!silent) { setEntityExtraData(null); setDupCard(null); }
    return getEntity(entityId)
      .then(entity => {
        setEntityExtraData(entity.extra_data || null);
        // Карточка для ShadowDuplicateBanner — чтобы баннер «Похожий кандидат»
        // работал и в воронке, а не только в «Все кандидаты».
        const ed = (entity.extra_data || {}) as Record<string, any>;
        setDupCard({
          id: entity.id,
          name: entity.name || '',
          email: entity.email || undefined,
          phone: entity.phone || undefined,
          telegram_username: entity.telegram_usernames?.[0],
          position: entity.position || undefined,
          company: entity.company || undefined,
          created_at: entity.created_at || '',
          tags: (entity.tags as string[]) || [],
          city: ed.city,
          age: ed.age != null ? String(ed.age) : undefined,
          salary: ed.salary != null ? String(ed.salary) : undefined,
          total_experience: ed.total_experience != null ? String(ed.total_experience) : undefined,
          source: ed.source,
          source_url: ed.source_url,
          extra_data: entity.extra_data || undefined,
        });
      })
      .catch(() => { if (!silent) { setEntityExtraData(null); setDupCard(null); } });
  }, []);

  useEffect(() => {
    if (!entityId) {
      setEntityExtraData(null);
      setDupCard(null);
      return;
    }
    loadEntityExtra(entityId, false);
  }, [entityId, loadEntityExtra]);

  // Молчаливый поллинг entity_id — та же причина, что и у доски/анкет: WS на
  // проде ненадёжен. Без этого коммент, оставленный на ЭТОМ ЖЕ кандидате в
  // «Все кандидаты», не появлялся в воронке без переоткрытия карточки (Мария).
  useEffect(() => {
    if (!entityId) return;
    const id = setInterval(() => {
      if (document.visibilityState === 'visible') loadEntityExtra(entityId, true);
    }, 15000);
    return () => clearInterval(id);
  }, [entityId, loadEntityExtra]);

  // Resume: original document (PDF or DOC/DOCX) + page images (JPEG renders from backend)
  const resumeOriginal = useMemo(
    () => entityFiles.find(f => f.file_type === 'resume' && f.mime_type !== 'image/jpeg') || null,
    [entityFiles],
  );
  const resumePages = useMemo(
    () => entityFiles
      .filter(f => f.file_type === 'resume' && f.mime_type === 'image/jpeg')
      .sort((a, b) => {
        // Sort by page number extracted from file_name "Резюме стр. N.jpg"
        const numA = parseInt(a.file_name.match(/(\d+)/)?.[1] || '0');
        const numB = parseInt(b.file_name.match(/(\d+)/)?.[1] || '0');
        return numA - numB;
      }),
    [entityFiles],
  );
  const hasResume = resumeOriginal !== null || resumePages.length > 0;

  // Источники резюме (по одному на влитый профиль/PDF) — та же чистая модель,
  // что и «Все кандидаты». Вкладки «Резюме» рисуем на верхнем уровне (паритет),
  // а ResumeViewer переключаем по resumeIndex в управляемом режиме.
  const resumeSources = useMemo(
    () => buildResumeSources(entityFiles, entityExtraData ?? undefined),
    [entityFiles, entityExtraData],
  );
  const [resumeIndex, setResumeIndex] = useState(0);
  // Сброс активной вкладки резюме при переключении кандидата.
  useEffect(() => { setResumeIndex(0); }, [entityId]);

  return {
    activityState, refreshActivity,
    entityFiles, setEntityFiles, filesLoading,
    entityExtraData, setEntityExtraData, dupCard, setDupCard,
    hasResume, resumeSources, resumeIndex, setResumeIndex,
  };
}
