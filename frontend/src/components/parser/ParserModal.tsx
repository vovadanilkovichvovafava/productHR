import { useState, useCallback, useRef, useEffect } from 'react';
import { motion } from 'framer-motion';
import { X, Search, Upload, Loader2, AlertCircle, Plus, Briefcase, MessageSquare } from 'lucide-react';
import clsx from 'clsx';
import toast from 'react-hot-toast';
import type { ParsedResume, ParsedVacancy } from '@/services/api';
import {
  parseResumeFromFile,
  createEntity,
  uploadEntityFile,
  getAllVacancies,
  createApplication,
} from '@/services/api';
import { addEntityNote } from '@/services/api/entities';
import ParsedDataPreview from './ParsedDataPreview';
import type { Vacancy } from '@/types';
import { useAuthStore } from '@/stores/authStore';
import { isVacancyParticipant } from '@/utils/vacancy';
import { backdropClose } from '@/utils/backdropClose';
import { useNavigate } from 'react-router-dom';
import {
  ExistingCandidatesPanel,
  checkDuplicateBeforeCreate,
  type DuplicateCheckResult,
} from '@/components/candidates/ExistingCandidatesPanel';

interface ParserModalProps {
  type: 'resume' | 'vacancy';
  onClose: () => void;
  onParsed: (data: ParsedResume | ParsedVacancy) => void;
  /** Callback when background job is started */
  onJobStarted?: (jobId: number, fileName: string) => void;
  /** Callback when resume is attached to existing entity */
  onAttachedToEntity?: (entityId: number) => void;
  /** id созданного кандидата — чтобы страница открыла ИМЕННО его карточку
   *  (просьба Эльвиры 02.10.2026: после добавления по резюме справа оставался
   *  прошлый человек, и статусы на бегу меняли не тому). */
  onCreated?: (entityId: number) => void;
}



export default function ParserModal({ type, onClose, onParsed, onJobStarted: _onJobStarted, onAttachedToEntity, onCreated }: ParserModalProps) {
  const [loading, setLoading] = useState(false);
  const [uploadPct, setUploadPct] = useState<number | null>(null);
  // Фейковый прогресс во время AI-анализа (не быстрее, чем реальный parse, медленно идёт к 100%)
  const [error, setError] = useState<string | null>(null);
  const [parsedData, setParsedData] = useState<ParsedResume | ParsedVacancy | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Candidate matching state
  const [dupCheck, setDupCheck] = useState<DuplicateCheckResult | null>(null);
  const navigate = useNavigate();
  const [isSearchingCandidates, setIsSearchingCandidates] = useState(false);
  const [uploadedFile, setUploadedFile] = useState<File | null>(null);
  const [isAttaching, setIsAttaching] = useState(false);
  const { user } = useAuthStore();
  const isHrAdmin =
    user?.role === 'superadmin' ||
    user?.org_role === 'owner' ||
    user?.org_role === 'admin';

  // Vacancy attachment state — кандидата можно сразу добавить на воронку
  const [vacancyOptions, setVacancyOptions] = useState<Pick<Vacancy, 'id' | 'title'>[]>([]);
  const [selectedVacancyId, setSelectedVacancyId] = useState<number | ''>('');
  // Комментарий рекрутёра при добавлении из файла → уходит в ленту карточки
  // отдельной записью (как коммент из расширения). Это НЕ «Описание» (summary).
  const [comment, setComment] = useState('');
  const [isCreating, setIsCreating] = useState(false);

  // Подгружаем список своих воронок один раз — нужен только в режиме резюме.
  useEffect(() => {
    if (type !== 'resume') return;
    let cancelled = false;
    (async () => {
      try {
        const all = await getAllVacancies({ status: 'open' });
        if (cancelled) return;
        // Схлопываем «заявку + её клон»: если у воронки есть клон
        // (extra_data.cloned_from_request_id == X), оригинал X прячем — иначе одна
        // воронка двоится («Трафик ×2 / Рекрутер тест ×2»).
        const clonedSourceIds = new Set<number>();
        all.forEach((v) => {
          const src = (v.extra_data as Record<string, unknown> | undefined)?.cloned_from_request_id;
          if (typeof src === 'number') clonedSourceIds.add(src);
        });
        const seenTitles = new Set<string>();
        const myOpen: { id: number; title: string }[] = [];
        for (const v of all) {
          // Свои воронки = где участник (создатель/назначенный, минус dismissed) —
          // общая модель 2026-07-02. Невзятые заявки — НЕ цель.
          if (v.status !== 'open') continue;
          if (!isHrAdmin && !(user && isVacancyParticipant(v, user.id))) continue;
          if (clonedSourceIds.has(v.id)) continue; // оригинал, у которого уже есть клон
          const key = (v.title || '').trim().toLowerCase();
          if (seenTitles.has(key)) continue; // дубль по названию
          seenTitles.add(key);
          myOpen.push({ id: v.id, title: v.title });
        }
        setVacancyOptions(myOpen);
      } catch (e) {
        console.warn('Failed to load vacancies for attach picker:', e);
      }
    })();
    return () => { cancelled = true; };
  }, [type, isHrAdmin, user]);

  const isResume = type === 'resume';

  // «Уже есть в базе» — общий матчер дублей (как у расширения), с архивом и
  // «Был отказ» (22.10.2026). Раньше — обычный поиск по имени/почте: архив не
  // видел, рядовой рекрутёр — только своих, статус не показывался.
  useEffect(() => {
    if (!parsedData || type !== 'resume') return;
    const r = parsedData as ParsedResume;
    if (!r.name && !r.email && !r.phone && !r.telegram) return;
    let alive = true;
    setIsSearchingCandidates(true);
    checkDuplicateBeforeCreate({
      full_name: r.name || undefined,
      email: r.email || undefined,
      phone: r.phone || undefined,
      telegram: r.telegram || undefined,
    })
      .then((res) => alive && setDupCheck(res))
      .catch((err) => console.error('Duplicate check failed:', err))
      .finally(() => alive && setIsSearchingCandidates(false));
    return () => {
      alive = false;
    };
  }, [parsedData, type]);

  // «Открыть» найденного: живого — тем же путём, что после «Прикрепить»
  // (страница открывает его карточку), архивного — ссылкой с ?archived=1.
  const openExisting = (entityId: number, archived?: boolean) => {
    if (archived || !onAttachedToEntity) navigate(`/all-candidates?entity=${entityId}${archived ? '&archived=1' : ''}`);
    else onAttachedToEntity(entityId);
    onClose();
  };

  // Attach resume file to existing candidate
  const handleAttachToCandidate = async (candidateId: number) => {
    if (!uploadedFile) return;
    setIsAttaching(true);
    try {
      await uploadEntityFile(candidateId, uploadedFile, 'resume', 'Resume (attached via parser)');
      toast.success('Резюме прикреплено к кандидату');
      onAttachedToEntity?.(candidateId);
      onClose();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Ошибка прикрепления файла';
      toast.error(message);
    } finally {
      setIsAttaching(false);
    }
  };


  const handleFileSelect = async (file: File) => {
    if (!isResume) {
      toast.error('Загрузка файлов доступна только для резюме');
      return;
    }

    // Check file type by MIME type AND extension (some browsers return empty file.type)
    const allowedTypes = ['application/pdf', 'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'text/plain'];
    const allowedExtensions = ['.pdf', '.doc', '.docx', '.txt'];
    const fileExtension = file.name.toLowerCase().slice(file.name.lastIndexOf('.'));
    const isTypeValid = allowedTypes.includes(file.type) || (file.type === '' && allowedExtensions.includes(fileExtension));
    const isExtensionValid = allowedExtensions.includes(fileExtension);

    if (!isTypeValid && !isExtensionValid) {
      const errorMsg = 'Поддерживаются только PDF, DOC, DOCX и TXT файлы';
      setError(errorMsg);
      toast.error(errorMsg);
      return;
    }

    // Check file size (max 10MB)
    if (file.size > 10 * 1024 * 1024) {
      setError('Размер файла не должен превышать 10 МБ');
      return;
    }

    setLoading(true);
    setUploadPct(0);
    setError(null);
    setParsedData(null);
    setUploadedFile(file);
    setDupCheck(null);

    try {
      // Реальный % отправки файла; на 100% сервер начинает AI-разбор → переключаемся на
      // индетерминантную (бегущую) полоса, которую юзер видит в UI.
      const data = await parseResumeFromFile(file, (pct) => setUploadPct(pct >= 100 ? null : pct));
      setParsedData(data);
      toast.success('Резюме распознано');
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Ошибка парсинга файла';
      setError(message);
      toast.error(message);
    } finally {
      setLoading(false);
      setUploadPct(null);
    }
  };

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleFileSelectRef = useRef(handleFileSelect);
  handleFileSelectRef.current = handleFileSelect;

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);

    const files = e.dataTransfer.files;
    if (files.length > 0) {
      handleFileSelectRef.current(files[0]);
    }
  }, []);

  const handleFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      handleFileSelect(files[0]);
    }
  };

  const handleDataChange = (data: ParsedResume | ParsedVacancy) => {
    setParsedData(data);
  };

  const handleCreate = async () => {
    if (!parsedData) return;

    // Validate required fields
    if (type === 'vacancy') {
      const vacancyData = parsedData as ParsedVacancy;
      if (!vacancyData.title?.trim()) {
        toast.error('Название вакансии обязательно');
        return;
      }
      onParsed(parsedData);
      return;
    }

    const resumeData = parsedData as ParsedResume;
    if (!resumeData.name?.trim()) {
      toast.error('Имя контакта обязательно');
      return;
    }

    // Резюме: создаём кандидата здесь же. Раньше onParsed только показывал
    // toast и ничего не создавал — пользователи жаловались «куда этот файл
    // загружается». Теперь либо createEntityFromResume (если есть файл,
    // он же приложит резюме как файл к карточке), либо парент-форма
    // (URL-парс — там нужны доп. поля).
    setIsCreating(true);
    try {
      let createdEntityId: number | null = null;

      if (uploadedFile) {
        // Создаём из ОТРЕДАКТИРОВАННЫХ полей (parsedData), а не повторным парсингом
        // файла — иначе правки пользователя (имя и пр.) терялись. Файл прикрепляем
        // отдельно: upload конвертит PDF в картинки-страницы → чистый просмотр.
        const r = parsedData as ParsedResume;
        const created = await createEntity({
          type: 'candidate',
          name: r.name!.trim(),
          email: r.email?.trim() || undefined,
          phone: r.phone?.trim() || undefined,
          telegram_usernames: r.telegram?.trim() ? [r.telegram.trim().replace(/^@/, '')] : undefined,
          position: r.position?.trim() || undefined,
          company: r.company?.trim() || undefined,
          expected_salary_min: r.salary_min ?? undefined,
          expected_salary_max: r.salary_max ?? undefined,
          expected_salary_currency: r.salary_currency || undefined,
          extra_data: {
            source: 'resume_upload',
            ...(r.location ? { city: r.location, location: r.location } : {}),
            ...(r.experience_years != null ? { experience_years: r.experience_years } : {}),
            ...(r.skills?.length ? { skills: r.skills } : {}),
            ...(r.summary ? { summary: r.summary, resume_text: r.summary } : {}),
          },
        });
        createdEntityId = created.id;
        try {
          await uploadEntityFile(created.id, uploadedFile, 'resume');
        } catch (e) {
          // Раньше сбой здесь глотался молча: кандидат создан, тост «Кандидат
          // добавлен», а резюме в карточке нет — «создаю кандидата, добавляю
          // резюме, он не добавляется к карточке» (Мария, 15.10.2026). Теперь
          // говорим прямо и с причиной от сервера — по ней и разбираемся.
          console.error('attach resume file failed', e);
          const detail = (e as { response?: { data?: { detail?: string } } })
            ?.response?.data?.detail;
          toast.error(
            `Кандидат создан, но резюме не прикрепилось${detail ? `: ${detail}` : ''}. ` +
              'Добавьте файл кнопкой «Файл» в карточке.',
            { duration: 10000 },
          );
        }
      } else {
        // URL-парсинг — оставляем парент-flow (CandidatesDatabase открывает
        // pre-filled CreateCandidateModal). Просто пробрасываем данные.
        onParsed(parsedData);
        return;
      }

      if (!createdEntityId) {
        toast.error('Кандидат не создан — попробуйте ещё раз');
        return;
      }

      // Комментарий рекрутёра → запись в ленте карточки. Через штатный
      // POST /entities/{id}/notes: автора/дату проставляет сервер, формат тот же,
      // что у «Написать комментарий» и у коммента из расширения.
      if (comment.trim()) {
        try {
          await addEntityNote(createdEntityId, {
            text: comment.trim(),
            stage: 'new',
            stage_label: 'Новый',
          });
        } catch (e) {
          console.error('save comment failed', e);
          toast.error('Кандидат создан, но комментарий не сохранился');
        }
      }

      // Опционально цепляем на воронку.
      if (selectedVacancyId) {
        try {
          await createApplication(Number(selectedVacancyId), {
            vacancy_id: Number(selectedVacancyId),
            entity_id: createdEntityId,
            source: 'resume_upload',
          });
          const vacancyTitle = vacancyOptions.find(v => v.id === selectedVacancyId)?.title;
          toast.success(`Кандидат добавлен на воронку «${vacancyTitle ?? '...'}»`);
        } catch (e) {
          console.error('Attach to vacancy failed:', e);
          toast.error('Кандидат создан, но не удалось добавить на воронку');
        }
      } else {
        toast.success('Кандидат добавлен');
      }

      onCreated?.(createdEntityId);
      onParsed(parsedData);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Ошибка создания кандидата';
      toast.error(msg);
    } finally {
      setIsCreating(false);
    }
  };


  // Резюме уже распознано — в окне лежит несохранённая работа (разбор, правки
  // полей, комментарий, выбранная воронка). Молча её терять нельзя: переспросим.
  // Успешное создание закрывает окно через onParsed у родителя, сюда не попадает.
  const requestClose = useCallback(() => {
    if (
      parsedData &&
      !window.confirm('Закрыть окно? Распознанное резюме и комментарий не сохранятся.')
    ) {
      return;
    }
    onClose();
  }, [parsedData, onClose]);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 backdrop-blur-sm z-50 flex items-center justify-center p-4"
      style={{ backgroundColor: 'rgba(0, 0, 0, 0.7)' }}
      {...backdropClose(requestClose)}
      role="dialog"
      aria-modal="true"
      aria-labelledby="parser-modal-title"
    >
      <motion.div
        initial={{ scale: 0.95, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        exit={{ scale: 0.95, opacity: 0 }}
        onClick={(e) => e.stopPropagation()}
        className="bg-white text-slate-900 shadow-xl border border-slate-200 rounded-xl w-full max-w-lg max-h-[95vh] overflow-hidden flex flex-col"
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-slate-200 flex-shrink-0">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-[var(--hf-status-cyan-badge)] rounded-lg">
              <Search className="w-5 h-5 text-[var(--hf-cyan-400)]" aria-hidden="true" />
            </div>
            <h2 id="parser-modal-title" className="text-lg font-semibold">
              {isResume ? 'Парсинг резюме' : 'Парсинг вакансии'}
            </h2>
          </div>
          <button
            onClick={requestClose}
            className="p-2 hover:bg-slate-100 rounded-lg transition-colors"
            aria-label="Закрыть окно"
          >
            <X className="w-5 h-5" aria-hidden="true" />
          </button>
        </div>


        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4 no-scrollbar">
          {!parsedData ? (
            // File upload section
            <div className="space-y-4">
              <div
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    fileInputRef.current?.click();
                  }
                }}
                className={clsx(
                  'border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors',
                  isDragging
                    ? 'border-[color:var(--hf-cyan-500)] bg-[var(--hf-status-cyan-bg)]'
                    : 'border-slate-300 hover:border-slate-400 hover:bg-slate-100'
                )}
                role="button"
                tabIndex={0}
                aria-label="Область для загрузки файла. Перетащите файл или нажмите для выбора"
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".pdf,.doc,.docx,.txt"
                  onChange={handleFileInputChange}
                  className="hidden"
                  aria-label="Выбрать файл резюме"
                />
                <Upload className={clsx(
                  'w-10 h-10 mx-auto mb-4',
                  isDragging ? 'text-[var(--hf-cyan-400)]' : 'text-slate-400'
                )} aria-hidden="true" />
                <p className="text-slate-500 mb-2">
                  {isDragging
                    ? 'Отпустите файл для загрузки'
                    : 'Перетащите файл сюда или нажмите для выбора'
                  }
                </p>
                <p className="text-xs text-slate-400">
                  PDF, DOC, DOCX или TXT (максимум 10 МБ)
                </p>
                {error && (
                  <p className="text-xs text-[var(--hf-status-red)] mt-4 flex items-center justify-center gap-1" role="alert">
                    <AlertCircle className="w-3 h-3" aria-hidden="true" />
                    {error}
                  </p>
                )}
              </div>

              {/* Loading indicator — реальный % загрузки, затем индетерминантный AI-анализ */}
              {loading && (
                <div className="py-4 space-y-2" role="status" aria-live="polite">
                  <div className="flex items-center justify-center gap-2 text-[var(--hf-cyan-400)]">
                    <Loader2 className="w-5 h-5 animate-spin" aria-hidden="true" />
                    <span>{uploadPct !== null ? `Загрузка файла… ${uploadPct}%` : 'AI анализирует резюме…'}</span>
                  </div>
                  <div className="h-1.5 bg-[var(--hf-white-alpha-10)] rounded-full overflow-hidden">
                    {uploadPct !== null ? (
                      <div className="h-full bg-[var(--hf-cyan-400)] rounded-full transition-all duration-200" style={{ width: `${uploadPct}%` }} />
                    ) : (
                      <motion.div
                        className="h-full w-1/3 bg-[var(--hf-cyan-400)] rounded-full"
                        animate={{ x: ['-100%', '300%'] }}
                        transition={{ duration: 1.1, repeat: Infinity, ease: 'easeInOut' }}
                      />
                    )}
                  </div>
                </div>
              )}
            </div>
          ) : (
            // Preview section
            <div className="space-y-4">
              <ParsedDataPreview
                type={type}
                data={parsedData}
                onDataChange={handleDataChange}
              />

              {/* Комментарий рекрутёра — ОТДЕЛЬНОЕ поле, не «Описание».
                  «Описание» выше — это summary самого кандидата («Обо мне»),
                  которое достаёт парсер; в ленту оно не идёт. Рекрутёры писали
                  свой коммент туда и не находили его потом. Здесь — настоящий
                  комментарий: уходит в ленту карточки, как из расширения. */}
              {isResume && uploadedFile && (
                <div className="border-t border-slate-200 pt-4">
                  <label className="block text-sm font-medium text-slate-600 mb-2 flex items-center gap-2">
                    <MessageSquare className="w-4 h-4" />
                    Комментарий (опционально)
                  </label>
                  <textarea
                    value={comment}
                    onChange={(e) => setComment(e.target.value)}
                    rows={2}
                    disabled={isCreating}
                    placeholder="Появится в ленте карточки — например, откуда кандидат"
                    className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm resize-none focus:outline-none focus:border-[color:var(--hf-cyan-500)]"
                  />
                </div>
              )}

              {/* Vacancy attach picker — только для резюме с загруженным файлом.
                  Для URL-резюме сначала открывается форма редактирования карточки,
                  поэтому пикер тут не имеет смысла. */}
              {isResume && uploadedFile && (
                <div className="border-t border-slate-200 pt-4">
                  <label className="block text-sm font-medium text-slate-600 mb-2 flex items-center gap-2">
                    <Briefcase className="w-4 h-4" />
                    Добавить на воронку (опционально)
                  </label>
                  <select
                    value={selectedVacancyId}
                    onChange={(e) => setSelectedVacancyId(e.target.value ? Number(e.target.value) : '')}
                    className="w-full px-3 py-2.5 bg-slate-50 border border-slate-200 rounded-lg text-sm focus:outline-none focus:border-[color:var(--hf-cyan-500)]"
                    disabled={isCreating}
                  >
                    <option value="">— без воронки —</option>
                    {vacancyOptions.map(v => (
                      <option key={v.id} value={v.id}>{v.title}</option>
                    ))}
                  </select>
                  {vacancyOptions.length === 0 && (
                    <p className="text-xs text-slate-400 mt-1.5">У вас нет открытых воронок</p>
                  )}
                </div>
              )}

              {/* «Уже есть в базе» — до «Создать нового кандидата» */}
              {isResume && (isSearchingCandidates || dupCheck) && (
                <div className="border-t border-slate-200 pt-4">
                  <ExistingCandidatesPanel
                    result={dupCheck}
                    loading={isSearchingCandidates}
                    onOpen={openExisting}
                    onAttach={handleAttachToCandidate}
                    attaching={isAttaching}
                  />
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 p-4 border-t border-slate-200 flex-shrink-0">
          <button
            onClick={requestClose}
            className="px-4 py-2 text-slate-500 hover:text-slate-900 transition-colors"
          >
            Отмена
          </button>
          {parsedData && (
            <button
              onClick={handleCreate}
              disabled={isCreating}
              className="flex items-center gap-2 px-4 py-2 bg-[var(--hf-cyan-600)] hover:bg-[var(--hf-cyan-500)] disabled:opacity-50 disabled:cursor-not-allowed text-slate-900 rounded-lg transition-colors"
            >
              {isCreating ? (
                <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
              ) : (
                <Plus className="w-4 h-4" aria-hidden="true" />
              )}
              {isResume
                ? (selectedVacancyId ? 'Создать и добавить на воронку' : 'Создать нового кандидата')
                : 'Создать вакансию'}
            </button>
          )}
        </div>
      </motion.div>
    </motion.div>
  );
}
