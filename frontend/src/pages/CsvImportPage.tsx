import { useState, useCallback, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Upload,
  FileSpreadsheet,
  ChevronRight,
  ChevronLeft,
  Loader2,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  ChevronDown,
  ChevronUp,
  RotateCcw,
  Users,
  X,
  Files,
} from 'lucide-react';
import clsx from 'clsx';
import { useNavigate } from 'react-router-dom';
import { splitCsvByPerson } from '@/utils/csvSplit';

// ---------- types ----------

interface PreviewResponse {
  headers: string[];
  rows: string[][];
  suggested_mapping: Record<string, string>;
  row_count: number;
}

interface ImportedFileSummary {
  name: string;
  rows: number;
  accepted: boolean;
  reason?: string | null;
}

interface ImportResult {
  imported: number;
  skipped: number;
  replaced?: number;
  auto_merged?: number;
  skipped_details?: { row: number; name: string; reason: string }[];
  errors: { row: number; reason: string }[];
  files?: ImportedFileSummary[];
}

interface Vacancy {
  id: number;
  title: string;
}

// ---------- constants ----------

const FIELD_OPTIONS: { value: string; label: string }[] = [
  { value: '', label: '(пропустить)' },
  { value: 'name', label: 'Имя' },
  { value: 'email', label: 'Email' },
  { value: 'phone', label: 'Телефон' },
  { value: 'position', label: 'Должность' },
  { value: 'company', label: 'Компания' },
  { value: 'status', label: 'Статус' },
  { value: 'tags', label: 'Теги' },
  { value: 'telegram', label: 'Telegram' },
  { value: 'source', label: 'Источник' },
  { value: 'comment', label: 'Комментарий' },
];

const stepVariants = {
  enter: { opacity: 0, x: 40 },
  center: { opacity: 1, x: 0 },
  exit: { opacity: 0, x: -40 },
};

// ---------- helpers ----------

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// Один огромный файл (реальный кейс: 81 МБ / 8956 строк / 234 колонки) молча
// умирает на прокси/таймауте/памяти — многофайловый путь уже безопасно бьёт на
// пачки. Поэтому такой файл режем ПРЯМО В БРАУЗЕРЕ по границам людей
// (splitCsvByPerson — union-find по сильным ключам, зеркало бэкенда) и отдаём
// части в уже существующий мультифайловый путь.
const AUTO_SPLIT_THRESHOLD_BYTES = 25 * 1024 * 1024; // 25 МБ
const AUTO_SPLIT_TARGET_BYTES = 20 * 1024 * 1024; // целевой размер части ~20 МБ

// Части, произведённые сплиттером, помечены суффиксом `_partN.csv` — по нему
// отличаем «уже разрезанный файл» от «свежевыбранного большого файла», чтобы
// эффект авто-сплита не пытался резать один и тот же файл повторно (в т.ч. на
// редком крае, когда единственная огромная группа-человек сама больше цели и
// сплиттер вернул всего 1 часть — она всё ещё может превышать порог).
const isSplitPartFile = (name: string) => /_part\d+\.csv$/i.test(name);

// ---------- component ----------

export default function CsvImportPage() {
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Wizard step: 1=upload, 2=preview+mapping, 3=results
  const [step, setStep] = useState(1);

  // Step 1: files (мультивыбор — можно залить сразу пачку)
  const [files, setFiles] = useState<File[]>([]);
  const [dragActive, setDragActive] = useState(false);
  const isBulk = files.length > 1;
  const fileKey = (f: File) => `${f.name}:${f.size}`;
  // Статус каждого файла во время пачки: ждёт → грузится → готов/пропущен/ошибка.
  type FileStat = 'pending' | 'loading' | 'done' | 'skipped' | 'error';
  const [fileStatus, setFileStatus] = useState<Record<string, FileStat>>({});

  // Авто-сплит одного огромного файла на части по границам людей (см. константы
  // выше). Busy-состояние + результат/ошибка — отдельно от остального импорта,
  // т.к. происходит ДО перехода к шагу 2 (прямо в момент выбора файла).
  const [splitBusy, setSplitBusy] = useState(false);
  const [splitNotice, setSplitNotice] = useState<string | null>(null);
  const [splitError, setSplitError] = useState('');

  useEffect(() => {
    if (files.length !== 1) return;
    const file = files[0];
    if (file.size <= AUTO_SPLIT_THRESHOLD_BYTES) return;
    if (isSplitPartFile(file.name)) return; // уже результат сплита — не резать повторно

    let cancelled = false;
    (async () => {
      setSplitBusy(true);
      setSplitError('');
      setSplitNotice(null);
      try {
        const text = await file.text();
        const { parts, groups, records } = splitCsvByPerson(text, AUTO_SPLIT_TARGET_BYTES);
        if (cancelled) return;
        const baseName = file.name.replace(/\.csv$/i, '');
        const partFiles = parts.map(
          (part, i) =>
            new File([part], `${baseName}_part${i + 1}.csv`, { type: 'text/csv' }),
        );
        setFiles(partFiles);
        setSplitNotice(
          `Файл ${formatFileSize(file.size)} разбит на ${partFiles.length} ` +
            `${partFiles.length === 1 ? 'часть' : 'частей'} по границам кандидатов ` +
            `(${groups} чел., ${records} строк) — строки одного человека не разъехались.`,
        );
      } catch (err) {
        // Раньше большой файл падал МОЛЧА (прокси/таймаут/память) — здесь любая
        // ошибка сплиттера обязана быть видимой, а не проглоченной.
        if (!cancelled) {
          setSplitError(
            err instanceof Error
              ? `Не удалось разбить файл: ${err.message}`
              : 'Не удалось разбить файл на части',
          );
        }
      } finally {
        if (!cancelled) setSplitBusy(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [files]);

  // Step 2: preview + mapping
  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [columnMapping, setColumnMapping] = useState<Record<string, string>>({});
  // Грид маппинга скрыт по умолчанию (автоопределение надёжно для ClickUp);
  // раскрывается кнопкой «Изменить» или автоматически, если не нашли «Имя».
  const [showMapping, setShowMapping] = useState(false);
  const [vacancyId, setVacancyId] = useState<string>('');
  const [vacancies, setVacancies] = useState<Vacancy[]>([]);
  // Выбор дублей запоминается между импортами/файлами/перезагрузками — иначе при
  // заливке многих файлов приходилось переставлять галочки каждый раз.
  const [skipDuplicates, setSkipDuplicates] = useState(
    () => localStorage.getItem('csvImport.skipDuplicates') !== 'false',
  );
  const [replaceExisting, setReplaceExisting] = useState(
    () => localStorage.getItem('csvImport.replaceExisting') === 'true',
  );
  useEffect(() => {
    localStorage.setItem('csvImport.skipDuplicates', String(skipDuplicates));
  }, [skipDuplicates]);
  useEffect(() => {
    localStorage.setItem('csvImport.replaceExisting', String(replaceExisting));
  }, [replaceExisting]);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState('');

  // Step 3: results
  const [importing, setImporting] = useState(false);
  // Прогресс пакетной заливки (батчи по размеру): сколько файлов уже обработано.
  const [bulkProgress, setBulkProgress] = useState<{ done: number; total: number } | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [importError, setImportError] = useState('');
  const [errorsExpanded, setErrorsExpanded] = useState(false);
  const [skippedExpanded, setSkippedExpanded] = useState(false);

  // ClickUp-выгрузка (combine-путь в архив) — только для неё есть смысл в
  // «перезаписать начисто» (детект по сигнатурным колонкам, как на бэкенде).
  const isClickupFile =
    !!preview &&
    preview.headers.includes('task_id') &&
    preview.headers.some((h) => h.startsWith('funnel_'));

  // ---- drag-and-drop handlers ----
  const handleDrag = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  }, []);

  // Добавляем .csv к списку, дедупим по имени+размеру (повторный выбор не двоит).
  const addFiles = useCallback((incoming: File[]) => {
    const csv = incoming.filter((f) => f.name.toLowerCase().endsWith('.csv'));
    if (!csv.length) return;
    setSplitNotice(null);
    setSplitError('');
    setFiles((prev) => {
      const seen = new Set(prev.map((f) => `${f.name}:${f.size}`));
      return [...prev, ...csv.filter((f) => !seen.has(`${f.name}:${f.size}`))];
    });
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    addFiles(Array.from(e.dataTransfer.files || []));
  }, [addFiles]);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    addFiles(Array.from(e.target.files || []));
    e.target.value = ''; // разрешаем повторный выбор тех же файлов
  };

  const removeFile = (idx: number) =>
    setFiles((prev) => prev.filter((_, i) => i !== idx));

  // ---- step transitions ----
  // Кнопка «Далее»: один файл → мастер с маппингом; несколько → сразу опции пачки.
  const goNext = () => {
    if (!files.length || splitBusy) return;
    if (files.length === 1) {
      void goToPreview();
    } else {
      setPreviewError('');
      setStep(2);
    }
  };

  const goToPreview = async () => {
    const file = files[0];
    if (!file) return;
    setPreviewLoading(true);
    setPreviewError('');

    try {
      // Fetch preview
      const formData = new FormData();
      formData.append('file', file);
      const res = await fetch('/api/import/preview', { method: 'POST', body: formData });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Server error' }));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      const data: PreviewResponse = await res.json();
      setPreview(data);

      // Apply suggested mapping
      const mapping: Record<string, string> = {};
      for (const header of data.headers) {
        mapping[header] = data.suggested_mapping[header] || '';
      }
      setColumnMapping(mapping);
      // Раскрываем грид только если автоопределение не нашло колонку «Имя».
      setShowMapping(!Object.values(mapping).includes('name'));

      // Fetch vacancies for optional dropdown
      try {
        const vacRes = await fetch('/api/magic-button/vacancies');
        if (vacRes.ok) {
          const vacData = await vacRes.json();
          setVacancies(Array.isArray(vacData) ? vacData : []);
        }
      } catch {
        // vacancies are optional
      }

      setStep(2);
    } catch (err) {
      setPreviewError(err instanceof Error ? err.message : 'Failed to preview file');
    } finally {
      setPreviewLoading(false);
    }
  };

  const executeImport = async () => {
    const file = files[0];
    if (!file) return;
    setImporting(true);
    setImportError('');
    setResult(null);

    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('column_mapping', JSON.stringify(columnMapping));
      formData.append('skip_duplicates', String(skipDuplicates));
      formData.append('replace_existing', String(replaceExisting));
      if (vacancyId) formData.append('vacancy_id', vacancyId);

      const res = await fetch('/api/import/execute', { method: 'POST', body: formData });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Server error' }));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      const data: ImportResult = await res.json();
      setResult(data);
      setStep(3);
    } catch (err) {
      setImportError(err instanceof Error ? err.message : 'Import failed');
    } finally {
      setImporting(false);
    }
  };

  // Пакетная заливка батчами по РАЗМЕРУ: один запрос на пачку ≤ MAX_BATCH_BYTES
  // (под лимитом nginx client_max_body_size и proxy_read_timeout — иначе большой
  // одиночный запрос отваливается по таймауту/размеру). Между запросами дедуп
  // сохраняется: каждый следующий видит уже созданные карточки. Прогресс — по
  // файлам; результаты агрегируются.
  const MAX_BATCH_BYTES = 40 * 1024 * 1024; // 40 МБ

  const executeBulkImport = async () => {
    if (!files.length) return;
    setImporting(true);
    setImportError('');
    setResult(null);
    setBulkProgress({ done: 0, total: files.length });
    // Все файлы стартуют как «ждёт».
    setFileStatus(Object.fromEntries(files.map((f) => [fileKey(f), 'pending' as FileStat])));

    // Режем на батчи по кумулятивному размеру (в каждом ≥ 1 файл).
    const batches: File[][] = [];
    let cur: File[] = [];
    let curBytes = 0;
    for (const f of files) {
      if (cur.length && curBytes + f.size > MAX_BATCH_BYTES) {
        batches.push(cur);
        cur = [];
        curBytes = 0;
      }
      cur.push(f);
      curBytes += f.size;
    }
    if (cur.length) batches.push(cur);

    const agg: ImportResult = {
      imported: 0, skipped: 0, replaced: 0, auto_merged: 0, errors: [], files: [],
    };
    let done = 0;
    let anyOk = false;

    // Падение одного батча (напр. слишком большой файл) не должно рушить всю
    // заливку — записываем ошибку и продолжаем с остальными.
    for (const batch of batches) {
      // Файлы этого батча — «грузятся».
      setFileStatus((prev) => {
        const n = { ...prev };
        batch.forEach((f) => { n[fileKey(f)] = 'loading'; });
        return n;
      });
      try {
        const formData = new FormData();
        batch.forEach((f) => formData.append('files', f));
        formData.append('skip_duplicates', String(skipDuplicates));
        // Пачка шлётся батчами (несколько запросов), поэтому «перезаписать
        // начисто» здесь НЕ поддерживается: один человек может попасть в разные
        // батчи, и replace во втором стёр бы прохождения из первого. Идемпотентное
        // дополнение безопасно накапливает людей/прохождения/комментарии.
        formData.append('replace_existing', 'false');
        if (vacancyId) formData.append('vacancy_id', vacancyId);

        const res = await fetch('/api/import/execute-bulk', { method: 'POST', body: formData });
        if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: 'Server error' }));
          throw new Error(err.detail || `HTTP ${res.status}`);
        }
        const data: ImportResult = await res.json();
        agg.imported += data.imported || 0;
        agg.skipped += data.skipped || 0;
        agg.replaced = (agg.replaced || 0) + (data.replaced || 0);
        agg.auto_merged = (agg.auto_merged || 0) + (data.auto_merged || 0);
        agg.errors.push(...(data.errors || []));
        agg.files!.push(...(data.files || []));
        anyOk = true;
        // По ответу помечаем каждый файл готовым/пропущенным.
        const byName = new Map((data.files || []).map((s) => [s.name, s]));
        setFileStatus((prev) => {
          const n = { ...prev };
          batch.forEach((f) => {
            const s = byName.get(f.name);
            n[fileKey(f)] = s && !s.accepted ? 'skipped' : 'done';
          });
          return n;
        });
      } catch (err) {
        const msg = err instanceof Error ? err.message : 'ошибка';
        const label = batch.map((f) => f.name).join(', ');
        agg.errors.push({ row: 0, reason: `Пачка [${label.slice(0, 80)}]: ${msg}` });
        setFileStatus((prev) => {
          const n = { ...prev };
          batch.forEach((f) => { n[fileKey(f)] = 'error'; });
          return n;
        });
      }
      done += batch.length;
      setBulkProgress({ done, total: files.length });
    }

    setImporting(false);
    setBulkProgress(null);
    if (!anyOk) {
      setImportError(agg.errors[0]?.reason || 'Не удалось загрузить ни одной пачки');
    } else {
      setResult(agg);
      setStep(3);
    }
  };

  const restart = () => {
    setStep(1);
    setFiles([]);
    setFileStatus({});
    setSplitBusy(false);
    setSplitNotice(null);
    setSplitError('');
    setPreview(null);
    setColumnMapping({});
    setVacancyId('');
    // skipDuplicates / replaceExisting НЕ сбрасываем — они запоминаются между
    // импортами (иначе при заливке многих файлов бесит переставлять галочки).
    setResult(null);
    setImportError('');
    setPreviewError('');
    setErrorsExpanded(false);
  };

  // ---------- render ----------

  return (
    <div className="h-full w-full max-w-full overflow-y-auto overflow-x-hidden p-6">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="max-w-4xl mx-auto space-y-6 w-full"
      >
        {/* Header */}
        <div>
          <div className="flex items-center gap-3 mb-2">
            <FileSpreadsheet className="w-6 h-6 text-accent-500" />
            <h1 className="text-2xl font-bold">Импорт CSV</h1>
          </div>
          <p className="text-dark-400">
            Загрузите CSV-файл с кандидатами, настройте маппинг колонок и импортируйте данные.
          </p>
        </div>

        {/* Step indicator */}
        <div className="flex items-center gap-2">
          {[
            { num: 1, label: 'Загрузка' },
            { num: 2, label: 'Маппинг' },
            { num: 3, label: 'Результат' },
          ].map((s, i) => (
            <div key={s.num} className="flex items-center gap-2">
              {i > 0 && <div className={clsx('w-8 h-px', step >= s.num ? 'bg-accent-500' : 'bg-white/10')} />}
              <div
                className={clsx(
                  'flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors',
                  step === s.num
                    ? 'bg-accent-500/20 text-accent-400'
                    : step > s.num
                      ? 'bg-green-500/20 text-green-400'
                      : 'bg-white/[0.04] text-white/30'
                )}
              >
                <span className="w-5 h-5 rounded-full flex items-center justify-center text-xs border border-current">
                  {step > s.num ? <CheckCircle2 className="w-3.5 h-3.5" /> : s.num}
                </span>
                {s.label}
              </div>
            </div>
          ))}
        </div>

        {/* Step content */}
        <AnimatePresence mode="wait">
          {/* ===== STEP 1: Upload ===== */}
          {step === 1 && (
            <motion.div
              key="step1"
              variants={stepVariants}
              initial="enter"
              animate="center"
              exit="exit"
              transition={{ duration: 0.25 }}
              className="space-y-4"
            >
              <div
                onDragEnter={handleDrag}
                onDragLeave={handleDrag}
                onDragOver={handleDrag}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
                className={clsx(
                  'border-2 border-dashed rounded-2xl p-12 flex flex-col items-center gap-4 cursor-pointer transition-all duration-200',
                  dragActive
                    ? 'border-accent-500 bg-accent-500/10'
                    : files.length
                      ? 'border-green-500/40 bg-green-500/5'
                      : 'border-white/10 bg-white/[0.02] hover:border-white/20 hover:bg-white/[0.04]'
                )}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".csv"
                  multiple
                  onChange={handleFileSelect}
                  className="hidden"
                />
                <div
                  className={clsx(
                    'w-16 h-16 rounded-2xl flex items-center justify-center',
                    files.length ? 'bg-green-500/20' : 'bg-white/[0.06]'
                  )}
                >
                  {isBulk ? (
                    <Files className={clsx('w-8 h-8', 'text-green-400')} />
                  ) : (
                    <Upload className={clsx('w-8 h-8', files.length ? 'text-green-400' : 'text-white/40')} />
                  )}
                </div>
                <div className="text-center">
                  <p className="text-white/60 font-medium">
                    {files.length
                      ? 'Перетащите ещё или нажмите, чтобы добавить'
                      : 'Перетащите CSV-файлы сюда'}
                  </p>
                  <p className="text-dark-400 text-sm mt-1">
                    {files.length
                      ? `Выбрано файлов: ${files.length}`
                      : 'можно выбрать сразу несколько'}
                  </p>
                </div>
              </div>

              {/* Список выбранных файлов */}
              {files.length > 0 && (
                <div className="rounded-xl border border-white/[0.06] divide-y divide-white/[0.04]">
                  {files.map((f, i) => (
                    <div key={`${f.name}:${f.size}:${i}`} className="flex items-center gap-3 px-4 py-2.5">
                      <FileSpreadsheet className="w-4 h-4 text-white/40 flex-shrink-0" />
                      <span className="flex-1 min-w-0 truncate text-sm text-white/80">{f.name}</span>
                      <span className="text-xs text-dark-400 flex-shrink-0">{formatFileSize(f.size)}</span>
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          removeFile(i);
                        }}
                        className="text-white/30 hover:text-red-400 transition-colors flex-shrink-0"
                        title="Убрать файл"
                      >
                        <X className="w-4 h-4" />
                      </button>
                    </div>
                  ))}
                </div>
              )}

              {splitBusy && (
                <div className="flex items-center gap-2 p-3 rounded-xl bg-accent-500/10 border border-accent-500/20 text-accent-400 text-sm">
                  <Loader2 className="w-4 h-4 flex-shrink-0 animate-spin" />
                  Готовим файл… режем на части по границам кандидатов, строки одного
                  человека не разъедутся.
                </div>
              )}

              {!splitBusy && splitNotice && (
                <div className="flex items-center gap-2 p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-sm">
                  <CheckCircle2 className="w-4 h-4 flex-shrink-0" />
                  {splitNotice}
                </div>
              )}

              {splitError && (
                <div className="flex items-center gap-2 p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
                  <XCircle className="w-4 h-4 flex-shrink-0" />
                  {splitError}
                </div>
              )}

              {previewError && (
                <div className="flex items-center gap-2 p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
                  <XCircle className="w-4 h-4 flex-shrink-0" />
                  {previewError}
                </div>
              )}

              <div className="flex justify-end">
                <button
                  onClick={goNext}
                  disabled={!files.length || previewLoading || splitBusy}
                  className={clsx(
                    'flex items-center gap-2 px-6 py-2.5 rounded-xl text-sm font-medium transition-all duration-200',
                    files.length && !previewLoading && !splitBusy
                      ? 'bg-gradient-to-r from-accent-500 to-accent-600 text-white hover:from-accent-600 hover:to-accent-700 shadow-lg shadow-accent-500/20'
                      : 'bg-white/[0.06] text-white/30 cursor-not-allowed'
                  )}
                >
                  {previewLoading || splitBusy ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <>
                      Далее
                      <ChevronRight className="w-4 h-4" />
                    </>
                  )}
                </button>
              </div>
            </motion.div>
          )}

          {/* ===== STEP 2: Preview & Mapping ===== */}
          {step === 2 && !isBulk && preview && (
            <motion.div
              key="step2"
              variants={stepVariants}
              initial="enter"
              animate="center"
              exit="exit"
              transition={{ duration: 0.25 }}
              className="space-y-6"
            >
              {/* Preview table */}
              <div>
                <h2 className="text-sm font-semibold text-white/60 uppercase tracking-wider mb-3">
                  Предпросмотр ({preview.row_count} строк)
                </h2>
                <div className="overflow-x-auto rounded-xl border border-white/[0.06]">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-white/[0.06]">
                        {preview.headers.map((h) => (
                          <th
                            key={h}
                            className="px-3 py-2.5 text-left text-xs font-semibold text-white/40 uppercase tracking-wider bg-white/[0.02]"
                          >
                            {h}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {preview.rows.map((row, ri) => (
                        <tr
                          key={ri}
                          className="border-b border-white/[0.03] hover:bg-white/[0.02]"
                        >
                          {row.map((cell, ci) => (
                            <td key={ci} className="px-3 py-2 text-white/70 truncate max-w-[200px]">
                              {cell || <span className="text-white/20">—</span>}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Column mapping — определяется автоматически; по умолчанию свёрнут,
                  редактируется по кнопке (нужно лишь для нестандартных файлов). */}
              {(() => {
                const fieldLabel: Record<string, string> = Object.fromEntries(
                  FIELD_OPTIONS.map((o) => [o.value, o.label]),
                );
                const mapped = preview.headers
                  .filter((h) => columnMapping[h])
                  .map((h) => ({
                    header: h,
                    label: fieldLabel[columnMapping[h]] || columnMapping[h],
                  }));
                const hasName = preview.headers.some(
                  (h) => columnMapping[h] === 'name',
                );
                return (
                  <div>
                    <div className="flex items-center justify-between mb-3">
                      <h2 className="text-sm font-semibold text-white/60 uppercase tracking-wider">
                        Маппинг колонок
                      </h2>
                      <button
                        type="button"
                        onClick={() => setShowMapping((v) => !v)}
                        className="flex items-center gap-1 text-xs font-medium text-accent-400 hover:text-accent-300 transition-colors"
                      >
                        {showMapping ? (
                          <>
                            <ChevronUp className="w-3.5 h-3.5" />
                            Свернуть
                          </>
                        ) : (
                          <>
                            <ChevronDown className="w-3.5 h-3.5" />
                            Изменить
                          </>
                        )}
                      </button>
                    </div>

                    {!hasName && (
                      <div className="flex items-center gap-2 p-3 mb-3 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-400 text-sm">
                        <AlertTriangle className="w-4 h-4 flex-shrink-0" />
                        Не определена колонка с именем — выберите её вручную («Имя»), иначе кандидаты не загрузятся.
                      </div>
                    )}

                    {!showMapping ? (
                      <div className="p-4 rounded-xl bg-white/[0.03] border border-white/[0.06] space-y-2">
                        <div className="flex items-center gap-2 text-sm text-emerald-400">
                          <CheckCircle2 className="w-4 h-4 flex-shrink-0" />
                          Колонки определены автоматически
                        </div>
                        <div className="flex flex-wrap gap-2 pt-1">
                          {mapped.map((m) => (
                            <span
                              key={m.header}
                              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-white/[0.05] border border-white/[0.08] text-xs text-white/70"
                            >
                              <span className="text-white/90 font-medium">{m.label}</span>
                              <span className="text-white/30">←</span>
                              <span className="text-white/50 truncate max-w-[160px]">{m.header}</span>
                            </span>
                          ))}
                        </div>
                        <p className="text-xs text-white/40 pt-1">
                          Остальные колонки сохранятся в карточку кандидата и будут видны в анкете.
                        </p>
                      </div>
                    ) : (
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        {preview.headers.map((header) => (
                          <div
                            key={header}
                            className="flex items-center gap-3 p-3 rounded-xl bg-white/[0.03] border border-white/[0.06]"
                          >
                            <span className="text-sm text-white/60 font-medium min-w-[100px] truncate">
                              {header}
                            </span>
                            <ChevronRight className="w-4 h-4 text-white/20 flex-shrink-0" />
                            <select
                              value={columnMapping[header] || ''}
                              onChange={(e) =>
                                setColumnMapping((prev) => ({ ...prev, [header]: e.target.value }))
                              }
                              className="flex-1 bg-white/[0.04] border border-white/[0.08] rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:border-accent-500/50 transition-colors"
                            >
                              {FIELD_OPTIONS.map((opt) => (
                                <option key={opt.value} value={opt.value}>
                                  {opt.label}
                                </option>
                              ))}
                            </select>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })()}

              {/* Settings */}
              <div>
                <h2 className="text-sm font-semibold text-white/60 uppercase tracking-wider mb-3">
                  Настройки импорта
                </h2>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  {/* Импорт идёт в архив со статусами из CSV — общий дефолт не нужен */}
                  <div className="p-4 rounded-xl bg-amber-50 border border-amber-300 sm:col-span-2">
                    <p className="text-xs text-amber-900 leading-relaxed">
                      Кандидаты импортируются в <b>архив</b> со статусами из колонки CSV
                      («отказ», «на рассмотрении» и т.д.). Архив виден суперадмину в
                      разделе «Архив кандидатов».
                    </p>
                  </div>

                  {/* Vacancy (optional) */}
                  <div className="p-4 rounded-xl bg-white/[0.03] border border-white/[0.06]">
                    <label className="block text-xs text-white/40 mb-2 font-medium">
                      Привязать к вакансии (опционально)
                    </label>
                    <select
                      value={vacancyId}
                      onChange={(e) => setVacancyId(e.target.value)}
                      className="w-full bg-white/[0.04] border border-white/[0.08] rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-accent-500/50 transition-colors"
                    >
                      <option value="">Не привязывать</option>
                      {vacancies.map((v) => (
                        <option key={v.id} value={v.id}>
                          {v.title}
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* Skip duplicates */}
                  <div className="p-4 rounded-xl bg-white/[0.03] border border-white/[0.06] sm:col-span-2">
                    <label className="flex items-center gap-3 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={skipDuplicates}
                        onChange={(e) => setSkipDuplicates(e.target.checked)}
                        className="w-4 h-4 rounded border-white/20 bg-white/[0.04] text-accent-500 focus:ring-accent-500 focus:ring-offset-0"
                      />
                      <span className="text-sm text-white/70">
                        Пропускать дубликаты (по телефону / Telegram / email)
                      </span>
                    </label>
                  </div>

                  {/* Replace existing — только для ClickUp-выгрузки (combine-путь в архив) */}
                  {isClickupFile && (
                    <div className="p-4 rounded-xl bg-amber-500/[0.06] border border-amber-500/20 sm:col-span-2">
                      <label className="flex items-start gap-3 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={replaceExisting}
                          onChange={(e) => setReplaceExisting(e.target.checked)}
                          className="mt-0.5 w-4 h-4 rounded border-white/20 bg-white/[0.04] text-amber-500 focus:ring-amber-500 focus:ring-offset-0"
                        />
                        <span className="text-sm text-white/70">
                          <span className="font-medium text-amber-300">Перезаписать существующих начисто</span>
                          <br />
                          Кто уже есть в архиве и присутствует в файле — их карточки
                          полностью пересобираются из этого файла (старые прохождения не
                          наслаиваются). Активных кандидатов в воронках не трогает.
                        </span>
                      </label>
                    </div>
                  )}
                </div>
              </div>

              {importError && (
                <div className="flex items-center gap-2 p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
                  <XCircle className="w-4 h-4 flex-shrink-0" />
                  {importError}
                </div>
              )}

              {/* Actions */}
              <div className="flex items-center justify-between">
                <button
                  onClick={() => setStep(1)}
                  className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium text-white/50 hover:text-white/80 hover:bg-white/[0.04] transition-all duration-200"
                >
                  <ChevronLeft className="w-4 h-4" />
                  Назад
                </button>
                <button
                  onClick={executeImport}
                  disabled={importing || !Object.values(columnMapping).includes('name')}
                  className={clsx(
                    'flex items-center gap-2 px-6 py-2.5 rounded-xl text-sm font-medium transition-all duration-200',
                    !importing && Object.values(columnMapping).includes('name')
                      ? 'bg-gradient-to-r from-accent-500 to-accent-600 text-white hover:from-accent-600 hover:to-accent-700 shadow-lg shadow-accent-500/20'
                      : 'bg-white/[0.06] text-white/30 cursor-not-allowed'
                  )}
                >
                  {importing ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      Импортируется...
                    </>
                  ) : (
                    <>
                      <Upload className="w-4 h-4" />
                      Импортировать
                    </>
                  )}
                </button>
              </div>
            </motion.div>
          )}

          {/* ===== STEP 2 (пачка): опции для нескольких файлов ===== */}
          {step === 2 && isBulk && (
            <motion.div
              key="step2bulk"
              variants={stepVariants}
              initial="enter"
              animate="center"
              exit="exit"
              transition={{ duration: 0.25 }}
              className="space-y-6"
            >
              <div className="flex items-center gap-3 p-4 rounded-xl bg-accent-500/[0.06] border border-accent-500/20">
                <Files className="w-5 h-5 text-accent-400 flex-shrink-0" />
                <p className="text-sm text-white/70">
                  К заливке <b className="text-white">{files.length}</b> файлов. Колонки
                  определятся автоматически, люди из разных файлов/воронок склеятся в одну карточку.
                </p>
              </div>

              {/* Список файлов со статусом заливки */}
              <div className="rounded-xl border border-white/[0.06] divide-y divide-white/[0.04] max-h-64 overflow-y-auto">
                {files.map((f, i) => {
                  const st = fileStatus[fileKey(f)];
                  return (
                    <div key={`${fileKey(f)}:${i}`} className="flex items-center gap-3 px-4 py-2.5">
                      <span className="flex-shrink-0 w-4 h-4 flex items-center justify-center">
                        {st === 'loading' ? (
                          <Loader2 className="w-4 h-4 text-accent-400 animate-spin" />
                        ) : st === 'done' ? (
                          <CheckCircle2 className="w-4 h-4 text-green-400" />
                        ) : st === 'skipped' ? (
                          <AlertTriangle className="w-4 h-4 text-yellow-400" />
                        ) : st === 'error' ? (
                          <XCircle className="w-4 h-4 text-red-400" />
                        ) : (
                          <FileSpreadsheet className="w-4 h-4 text-white/30" />
                        )}
                      </span>
                      <span className={clsx(
                        'flex-1 min-w-0 truncate text-sm',
                        st === 'done' ? 'text-white/50' : 'text-white/80',
                      )}>
                        {f.name}
                      </span>
                      <span className="text-xs text-dark-400 flex-shrink-0 w-20 text-right">
                        {st === 'loading' ? 'грузится…'
                          : st === 'done' ? 'готово'
                          : st === 'skipped' ? 'пропущен'
                          : st === 'error' ? 'ошибка'
                          : formatFileSize(f.size)}
                      </span>
                      {!importing && (
                        <button
                          type="button"
                          onClick={() => removeFile(i)}
                          className="text-white/30 hover:text-red-400 transition-colors flex-shrink-0"
                          title="Убрать файл"
                        >
                          <X className="w-4 h-4" />
                        </button>
                      )}
                    </div>
                  );
                })}
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="p-4 rounded-xl bg-amber-50 border border-amber-300 sm:col-span-2">
                  <p className="text-xs text-amber-900 leading-relaxed">
                    Кандидаты импортируются в <b>архив</b> со статусами из CSV. Не-ClickUp и
                    пустые файлы будут пропущены (покажем в отчёте).
                  </p>
                </div>

                <div className="p-4 rounded-xl bg-white/[0.03] border border-white/[0.06]">
                  <label className="block text-xs text-white/40 mb-2 font-medium">
                    Привязать к вакансии (опционально)
                  </label>
                  <select
                    value={vacancyId}
                    onChange={(e) => setVacancyId(e.target.value)}
                    className="w-full bg-white/[0.04] border border-white/[0.08] rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-accent-500/50 transition-colors"
                  >
                    <option value="">Не привязывать</option>
                    {vacancies.map((v) => (
                      <option key={v.id} value={v.id}>
                        {v.title}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="p-4 rounded-xl bg-white/[0.03] border border-white/[0.06] sm:col-span-2">
                  <label className="flex items-center gap-3 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={skipDuplicates}
                      onChange={(e) => setSkipDuplicates(e.target.checked)}
                      className="w-4 h-4 rounded border-white/20 bg-white/[0.04] text-accent-500 focus:ring-accent-500 focus:ring-offset-0"
                    />
                    <span className="text-sm text-white/70">
                      Пропускать дубликаты (по телефону / Telegram / email)
                    </span>
                  </label>
                </div>

                <div className="p-4 rounded-xl bg-white/[0.03] border border-white/[0.06] sm:col-span-2">
                  <p className="text-xs text-white/50 leading-relaxed">
                    Повторная заливка безопасно <b className="text-white/70">дополняет</b>:
                    добавляет новых людей, недостающие прохождения и комментарии — ничего
                    не теряется. «Перезаписать начисто» в пачке недоступно (файлы льются
                    батчами) — для полной пересборки одной карточки используйте импорт
                    одиночного файла.
                  </p>
                </div>
              </div>

              {importError && (
                <div className="flex items-center gap-2 p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
                  <XCircle className="w-4 h-4 flex-shrink-0" />
                  {importError}
                </div>
              )}

              <div className="flex items-center justify-between">
                <button
                  onClick={() => setStep(1)}
                  className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium text-white/50 hover:text-white/80 hover:bg-white/[0.04] transition-all duration-200"
                >
                  <ChevronLeft className="w-4 h-4" />
                  Назад
                </button>
                <button
                  onClick={executeBulkImport}
                  disabled={importing}
                  className={clsx(
                    'flex items-center gap-2 px-6 py-2.5 rounded-xl text-sm font-medium transition-all duration-200',
                    !importing
                      ? 'bg-gradient-to-r from-accent-500 to-accent-600 text-white hover:from-accent-600 hover:to-accent-700 shadow-lg shadow-accent-500/20'
                      : 'bg-white/[0.06] text-white/30 cursor-not-allowed'
                  )}
                >
                  {importing ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      {bulkProgress
                        ? `Импортируется… ${bulkProgress.done} из ${bulkProgress.total}`
                        : 'Импортируется…'}
                    </>
                  ) : (
                    <>
                      <Upload className="w-4 h-4" />
                      Импортировать {files.length} файлов
                    </>
                  )}
                </button>
              </div>
            </motion.div>
          )}

          {/* ===== STEP 3: Results ===== */}
          {step === 3 && result && (
            <motion.div
              key="step3"
              variants={stepVariants}
              initial="enter"
              animate="center"
              exit="exit"
              transition={{ duration: 0.25 }}
              className="space-y-6"
            >
              {/* Stats */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div className="p-5 rounded-2xl bg-green-500/10 border border-green-500/20">
                  <div className="flex items-center gap-3 mb-2">
                    <CheckCircle2 className="w-5 h-5 text-green-400" />
                    <span className="text-sm text-green-400 font-medium">Импортировано</span>
                  </div>
                  <p className="text-3xl font-bold text-green-300">{result.imported}</p>
                </div>
                {!!result.replaced && (
                  <div className="p-5 rounded-2xl bg-amber-500/10 border border-amber-500/20">
                    <div className="flex items-center gap-3 mb-2">
                      <CheckCircle2 className="w-5 h-5 text-amber-400" />
                      <span className="text-sm text-amber-400 font-medium">Перезаписано</span>
                    </div>
                    <p className="text-3xl font-bold text-amber-300">{result.replaced}</p>
                  </div>
                )}
                {/* Авто-склейка «разъехавшихся»: сработала прямо при заливке,
                    руками ничего нажимать не нужно. */}
                {!!result.auto_merged && (
                  <div className="p-5 rounded-2xl bg-violet-500/10 border border-violet-500/20">
                    <div className="flex items-center gap-3 mb-2">
                      <CheckCircle2 className="w-5 h-5 text-violet-400" />
                      <span className="text-sm text-violet-400 font-medium">Склеено дублей</span>
                    </div>
                    <p className="text-3xl font-bold text-violet-300">{result.auto_merged}</p>
                  </div>
                )}
                {/* ClickUp-импорт (пачка или одиночный): «skipped» — это НЕ
                    проигнорировано, а «уже был в архиве → дополнен прохождениями
                    и комментариями». Показываем как «Обновлено» (не тревожно). */}
                {isBulk || isClickupFile ? (
                  <div className="p-5 rounded-2xl bg-blue-500/10 border border-blue-500/20">
                    <div className="flex items-center gap-3 mb-2">
                      <RotateCcw className="w-5 h-5 text-blue-400" />
                      <span className="text-sm text-blue-400 font-medium">Обновлено</span>
                    </div>
                    <p className="text-3xl font-bold text-blue-300">{result.skipped}</p>
                    <p className="text-[11px] text-blue-300/60 mt-1 leading-snug">
                      уже были в архиве — дополнены прохождениями и комментариями
                    </p>
                  </div>
                ) : (
                  <div className="p-5 rounded-2xl bg-yellow-500/10 border border-yellow-500/20">
                    <div className="flex items-center gap-3 mb-2">
                      <AlertTriangle className="w-5 h-5 text-yellow-400" />
                      <span className="text-sm text-yellow-400 font-medium">Пропущено</span>
                    </div>
                    <p className="text-3xl font-bold text-yellow-300">{result.skipped}</p>
                  </div>
                )}
                <div className="p-5 rounded-2xl bg-red-500/10 border border-red-500/20">
                  <div className="flex items-center gap-3 mb-2">
                    <XCircle className="w-5 h-5 text-red-400" />
                    <span className="text-sm text-red-400 font-medium">Ошибки</span>
                  </div>
                  <p className="text-3xl font-bold text-red-300">{result.errors.length}</p>
                </div>
              </div>

              {/* Разбивка по файлам (пакетная заливка) */}
              {result.files && result.files.length > 0 && (
                <div>
                  <h2 className="text-sm font-semibold text-white/60 uppercase tracking-wider mb-3">
                    Файлы ({result.files.length})
                  </h2>
                  <div className="rounded-xl border border-white/[0.06] divide-y divide-white/[0.04]">
                    {result.files.map((f, i) => (
                      <div key={`${f.name}:${i}`} className="flex items-center gap-3 px-4 py-2.5">
                        {f.accepted ? (
                          <CheckCircle2 className="w-4 h-4 text-green-400 flex-shrink-0" />
                        ) : (
                          <AlertTriangle className="w-4 h-4 text-yellow-400 flex-shrink-0" />
                        )}
                        <span className="flex-1 min-w-0 truncate text-sm text-white/80">{f.name}</span>
                        <span className="text-xs text-dark-400 flex-shrink-0">
                          {f.accepted ? `${f.rows} строк` : (f.reason || 'пропущен')}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Error details (expandable) */}
              {result.errors.length > 0 && (
                <div className="rounded-xl border border-red-500/20 overflow-hidden">
                  <button
                    onClick={() => setErrorsExpanded(!errorsExpanded)}
                    className="w-full flex items-center justify-between px-4 py-3 bg-red-500/5 hover:bg-red-500/10 transition-colors"
                  >
                    <span className="text-sm font-medium text-red-400">
                      Детали ошибок ({result.errors.length})
                    </span>
                    {errorsExpanded ? (
                      <ChevronUp className="w-4 h-4 text-red-400" />
                    ) : (
                      <ChevronDown className="w-4 h-4 text-red-400" />
                    )}
                  </button>
                  <AnimatePresence>
                    {errorsExpanded && (
                      <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.2 }}
                        className="overflow-hidden"
                      >
                        <div className="max-h-64 overflow-y-auto">
                          <table className="w-full text-sm">
                            <thead>
                              <tr className="border-b border-white/[0.06]">
                                <th className="px-4 py-2 text-left text-xs font-semibold text-white/40 uppercase tracking-wider bg-white/[0.02] w-24">
                                  Строка
                                </th>
                                <th className="px-4 py-2 text-left text-xs font-semibold text-white/40 uppercase tracking-wider bg-white/[0.02]">
                                  Причина
                                </th>
                              </tr>
                            </thead>
                            <tbody>
                              {result.errors.map((err, i) => (
                                <tr
                                  key={i}
                                  className="border-b border-white/[0.03] hover:bg-white/[0.02]"
                                >
                                  <td className="px-4 py-2 text-white/50 font-mono">
                                    {err.row}
                                  </td>
                                  <td className="px-4 py-2 text-red-300/80">
                                    {err.reason}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              )}

              {/* Skipped details (expandable) */}
              {!!result.skipped_details?.length && (
                <div className="rounded-xl border border-yellow-500/20 overflow-hidden">
                  <button
                    onClick={() => setSkippedExpanded(!skippedExpanded)}
                    className="w-full flex items-center justify-between px-4 py-3 bg-yellow-500/5 hover:bg-yellow-500/10 transition-colors"
                  >
                    <span className="text-sm font-medium text-yellow-400">
                      Детали пропущенных ({result.skipped_details.length})
                    </span>
                    {skippedExpanded ? (
                      <ChevronUp className="w-4 h-4 text-yellow-400" />
                    ) : (
                      <ChevronDown className="w-4 h-4 text-yellow-400" />
                    )}
                  </button>
                  <AnimatePresence>
                    {skippedExpanded && (
                      <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.2 }}
                        className="overflow-hidden"
                      >
                        <div className="max-h-64 overflow-y-auto">
                          <table className="w-full text-sm">
                            <thead>
                              <tr className="border-b border-white/[0.06]">
                                <th className="px-4 py-2 text-left text-xs font-semibold text-white/40 uppercase tracking-wider bg-white/[0.02] w-24">
                                  Строка
                                </th>
                                <th className="px-4 py-2 text-left text-xs font-semibold text-white/40 uppercase tracking-wider bg-white/[0.02]">
                                  Имя
                                </th>
                                <th className="px-4 py-2 text-left text-xs font-semibold text-white/40 uppercase tracking-wider bg-white/[0.02]">
                                  Причина
                                </th>
                              </tr>
                            </thead>
                            <tbody>
                              {result.skipped_details.map((s, i) => (
                                <tr
                                  key={i}
                                  className="border-b border-white/[0.03] hover:bg-white/[0.02]"
                                >
                                  <td className="px-4 py-2 text-white/50 font-mono">
                                    {s.row}
                                  </td>
                                  <td className="px-4 py-2 text-white/70">
                                    {s.name}
                                  </td>
                                  <td className="px-4 py-2 text-yellow-300/80">
                                    {s.reason}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              )}

              {/* Actions */}
              <div className="flex items-center gap-3">
                <button
                  onClick={restart}
                  className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-medium bg-white/[0.06] text-white/70 hover:bg-white/[0.1] hover:text-white transition-all duration-200"
                >
                  <RotateCcw className="w-4 h-4" />
                  Импортировать ещё
                </button>
                <button
                  onClick={() => navigate('/all-candidates')}
                  className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-medium bg-gradient-to-r from-accent-500 to-accent-600 text-white hover:from-accent-600 hover:to-accent-700 shadow-lg shadow-accent-500/20 transition-all duration-200"
                >
                  <Users className="w-4 h-4" />
                  К кандидатам
                </button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>
    </div>
  );
}
