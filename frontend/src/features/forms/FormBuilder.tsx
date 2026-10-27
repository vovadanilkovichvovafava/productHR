import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Plus,
  Trash2,
  Eye,
  Save,
  ArrowLeft,
  ArrowUp,
  ArrowDown,
  FileText,
  Mail,
  Phone,
  AlignLeft,
  List,
  CheckSquare,
  CircleDot,
  Upload,
  ExternalLink,
  ToggleLeft,
  ToggleRight,
  Star,
  Pencil,
  Copy,
  Link2,
  Loader2,
  Check,
  Calendar,
} from 'lucide-react';
import toast from 'react-hot-toast';
import clsx from 'clsx';
import {
  getForm,
  updateForm,
} from '@/services/api/forms';
import { escapeHtml } from '@/utils/linkify';
import { useLinkPrompt, wrapRangeWithLink } from '@/components/hr/LinkPrompt';
import type { FormField } from '@/services/api/forms';
import { FieldRenderer } from './FieldRenderer';
import { formProblem, normalizeFields } from './formValidation';
import HrConfirm from '@/components/hr/HrConfirm';

// ============================================================
// Field type config
// ============================================================

export const FIELD_TYPES: { type: FormField['type']; label: string; icon: React.ElementType }[] = [
  { type: 'text', label: 'Текст', icon: FileText },
  { type: 'email', label: 'Email', icon: Mail },
  { type: 'phone', label: 'Телефон', icon: Phone },
  { type: 'textarea', label: 'Текстовое поле', icon: AlignLeft },
  { type: 'select', label: 'Выбор одного', icon: List },
  { type: 'multiselect', label: 'Множественный выбор', icon: CheckSquare },
  { type: 'radio', label: 'Радио-кнопки', icon: CircleDot },
  { type: 'file', label: 'Файл', icon: Upload },
  { type: 'url', label: 'Ссылка (URL)', icon: ExternalLink },
  { type: 'scale', label: 'Шкала', icon: Star },
  { type: 'date', label: 'Дата', icon: Calendar },
];

export const TYPE_LABELS: Record<string, string> = {
  text: 'Текст',
  email: 'Email',
  phone: 'Телефон',
  textarea: 'Текстовое поле',
  select: 'Выбор одного',
  multiselect: 'Множественный выбор',
  radio: 'Радио-кнопки',
  file: 'Файл',
  url: 'Ссылка (URL)',
  scale: 'Шкала',
  date: 'Дата',
};

// Type-picker groups (Survio-style sections)
const TYPE_GROUPS: { title: string; types: FormField['type'][] }[] = [
  { title: 'Базовые',   types: ['text', 'textarea', 'radio', 'multiselect', 'select'] },
  { title: 'Открытые',  types: ['email', 'phone', 'url', 'file', 'date'] },
  { title: 'Оценочные', types: ['scale'] },
];

let fieldCounter = 0;
export function nextFieldId(): string {
  fieldCounter += 1;
  return `f${Date.now()}_${fieldCounter}`;
}

// ============================================================
// Word helpers
// ============================================================

export function fieldWord(n: number): string {
  const mod = n % 10;
  const mod100 = n % 100;
  if (mod100 >= 11 && mod100 <= 19) return 'полей';
  if (mod === 1) return 'поле';
  if (mod >= 2 && mod <= 4) return 'поля';
  return 'полей';
}

export function submissionWord(n: number): string {
  const mod = n % 10;
  const mod100 = n % 100;
  if (mod100 >= 11 && mod100 <= 19) return 'ответов';
  if (mod === 1) return 'ответ';
  if (mod >= 2 && mod <= 4) return 'ответа';
  return 'ответов';
}

// Мини rich-text редактор для описания анкеты (contentEditable + execCommand,
// как RichTextField в VacancyForm, но лёгкий Tailwind-стиль под светлую тему
// конструктора форм). Значение хранится как HTML — санитайзится при рендере
// на публичной странице (PublicFormPage, sanitizeHtml). Нужен, чтобы ссылки в
// «О компании» были кликабельны и чтобы можно было превращать в ссылку любое
// выделенное слово, а не только вставлять голый URL.
function DescriptionEditor({
  value,
  onChange,
  placeholder,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [isEmpty, setIsEmpty] = useState(!value);

  useEffect(() => {
    const el = ref.current;
    if (el && el.innerHTML !== (value || '')) el.innerHTML = value || '';
    setIsEmpty(!value);
  }, [value]);

  const sync = () => {
    const html = ref.current?.innerHTML || '';
    onChange(html);
    setIsEmpty(!ref.current?.textContent?.trim());
  };

  // Кнопка «Ссылка» без браузерного окна — общий порядок в LinkPrompt
  // (выделенный адрес → адрес из буфера → наше окно), владелец 05.10.2026.
  const savedRangeRef = useRef<Range | null>(null);

  const applyLink = (href: string) => {
    ref.current?.focus();
    const selection = window.getSelection();
    const range = savedRangeRef.current;
    if (range) {
      selection?.removeAllRanges();
      selection?.addRange(range);
    }
    if (range && !range.collapsed) {
      wrapRangeWithLink(range, href);
    } else {
      document.execCommand('insertHTML', false, `<a href="${escapeHtml(href)}">${escapeHtml(href)}</a>`);
    }
    savedRangeRef.current = null;
    sync();
  };

  const { requestLink, linkModal } = useLinkPrompt(applyLink);

  const addLink = () => {
    const selection = window.getSelection();
    savedRangeRef.current =
      selection && selection.rangeCount ? selection.getRangeAt(0).cloneRange() : null;
    void requestLink(selection?.toString() || '');
  };

  return (
    <div className="border border-gray-300 rounded-lg focus-within:border-blue-500 focus-within:ring-2 focus-within:ring-blue-500/20 transition-colors overflow-hidden">
      {linkModal}
      <div className="flex items-center px-2 py-1.5 border-b border-gray-200 bg-gray-50">
        <button
          type="button"
          title="Выделите текст и нажмите, чтобы сделать его ссылкой — или вставьте новую"
          className="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium bg-blue-50 text-blue-600 hover:bg-blue-100 border border-blue-200 transition-colors"
          onMouseDown={(e) => { e.preventDefault(); addLink(); }}
        >
          <Link2 className="w-3.5 h-3.5" />
          Вставить ссылку
        </button>
      </div>
      <div className="relative">
        {isEmpty && placeholder && (
          <span className="absolute left-3 top-2 text-sm text-gray-400 pointer-events-none">
            {placeholder}
          </span>
        )}
        <div
          ref={ref}
          contentEditable
          suppressContentEditableWarning
          role="textbox"
          aria-multiline="true"
          onInput={sync}
          onPaste={(e) => {
            const text = e.clipboardData.getData('text/plain');
            e.preventDefault();
            // Голая ссылка, вставленная целиком, — сразу делаем кликабельной
            // (самый частый кейс: «Сайт: https://...»). Остальной текст —
            // как есть, без превращения каждого URL в тексте автоматически,
            // чтобы не удивлять при вставке большого абзаца.
            if (/^https?:\/\/\S+$/i.test(text.trim())) {
              document.execCommand('insertHTML', false, `<a href="${escapeHtml(text.trim())}">${escapeHtml(text.trim())}</a>`);
            } else {
              document.execCommand('insertText', false, text);
            }
            sync();
          }}
          className="w-full px-3 py-2 text-sm text-gray-700 outline-none min-h-[38px] [&_a]:text-blue-600 [&_a]:underline"
        />
      </div>
    </div>
  );
}

// Сравнение «как на сервере» ↔ «как сейчас». Пробелы по краям и пустые
// варианты не считаются правкой: при сохранении они всё равно срезаются.
function snapshotOf(title: string, description: string, fields: FormField[], isActive: boolean, vacancyIds: number[]): string {
  return JSON.stringify([title.trim(), description.trim(), normalizeFields(fields), isActive, [...vacancyIds].sort((a, b) => a - b)]);
}

// Non-interactive preview value for each field type
function previewValue(field: FormField): unknown {
  if (field.type === 'multiselect') return [];
  if (field.type === 'scale') return null;
  return '';
}

// ============================================================
// FormBuilder component
// ============================================================

// saveAsTemplate по умолчанию TRUE: любое «Сохранить» (из «Конструктора форм»
// или из карточки кандидата) кладёт форму в «Шаблоны» (is_template=true), чтобы
// её можно было переиспользовать. Передай saveAsTemplate={false} для разовой
// формы, которая НЕ должна попадать в библиотеку шаблонов.
/** Для «Отправить кандидату» у разовой анкеты: проверить, что есть сейчас на
 *  экране, и досохранить правку, не дожидаясь автосейва. Текст проблемы или null. */
export type FormBuilderHandle = { flush: () => Promise<string | null> };

export function FormBuilder({ formId, onClose, saveAsTemplate = true, autosave = false, handleRef, inDialog = false }: {
  formId: number;
  /** Конструктор внутри выдвижной панели «Анкета» (окна — внутри неё). */
  inDialog?: boolean;
  onClose: () => void;
  saveAsTemplate?: boolean;
  autosave?: boolean;
  handleRef?: React.MutableRefObject<FormBuilderHandle | null>;
}) {
  const [form, setForm] = useState<import('@/services/api/forms').FormTemplate | null>(null);
  const [fields, setFields] = useState<FormField[]>([]);
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [isActive, setIsActive] = useState(true);
  const [saving, setSaving] = useState(false);
  // Состояние автосейва (только при autosave): индикатор вместо кнопки «Сохранить».
  const [autoSaveState, setAutoSaveState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
  const [loading, setLoading] = useState(true);
  const [editingFieldId, setEditingFieldId] = useState<string | null>(null);
  const [selectedVacancyIds, setSelectedVacancyIds] = useState<number[]>([]);
  const [vacancies, setVacancies] = useState<{ id: number; title: string }[]>([]);

  // WYSIWYG type-picker state
  const [showTypePicker, setShowTypePicker] = useState(false);
  const [insertIndex, setInsertIndex] = useState<number>(0);

  // Что сохранено на сервере — чтобы «Назад» не терял правки молча. Раньше
  // шаблон с несохранёнными вопросами закрывался без единого слова (20.10.2026).
  const savedSnapshotRef = useRef<string | null>(null);
  const [confirmLeave, setConfirmLeave] = useState(false);

  useEffect(() => {
    // Load vacancies for multi-select
    import('@/services/api').then(api => {
      api.getAllVacancies().then((vacs: { id: number; title: string; extra_data?: Record<string, unknown> }[]) => {
        // Дедуп клонов: «Взять в работу» создаёт клон вакансии с тем же названием
        // (extra_data.cloned_from_request_id), а заявка-оригинал остаётся видимой.
        // Прячем заявку, если у неё есть клон — иначе «Привязанные воронки»
        // показывают один и тот же фид дважды (как и чинили в «Взять на вакансию»).
        const clonedSourceIds = new Set<number>();
        vacs.forEach((v) => {
          const src = v.extra_data?.cloned_from_request_id;
          if (typeof src === 'number') clonedSourceIds.add(src);
        });
        setVacancies(vacs.filter((v) => !clonedSourceIds.has(v.id)));
      });
    });
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const data = await getForm(formId);
        setForm(data);
        setTitle(data.title);
        setDescription(data.description || '');
        setIsActive(data.is_active);
        setFields(data.fields || []);
        const vids = data.vacancy_ids || (data.vacancy_id ? [data.vacancy_id] : []);
        setSelectedVacancyIds(vids);
        savedSnapshotRef.current = snapshotOf(data.title, data.description || '', data.fields || [], data.is_active, vids);
      } catch {
        toast.error('Форма не найдена');
        onClose();
      } finally {
        setLoading(false);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- onClose is an unstable caller closure (() => setStep/navigate); depend only on formId, else this effect loops forever and freezes the page
  }, [formId]);

  const isDirty = () =>
    !autosave &&
    savedSnapshotRef.current !== null &&
    savedSnapshotRef.current !== snapshotOf(title, description, fields, isActive, selectedVacancyIds);

  const handleBack = () => {
    if (isDirty()) setConfirmLeave(true);
    else onClose();
  };

  const handleSave = async (): Promise<boolean> => {
    // Проверяем то, на чём кандидат потом застрял бы (formValidation.ts).
    const problem = formProblem(title, fields);
    if (problem) {
      toast.error(problem, { duration: 6000 });
      return false;
    }
    setSaving(true);
    try {
      const updated = await updateForm(formId, {
        title: title.trim(),
        description: description.trim() || undefined,
        fields: normalizeFields(fields),
        is_active: isActive,
        vacancy_ids: selectedVacancyIds,
        ...(saveAsTemplate ? { is_template: true } : {}),
      });
      setForm(updated);
      setFields(updated.fields || normalizeFields(fields));
      savedSnapshotRef.current = snapshotOf(title.trim(), description.trim(), updated.fields || normalizeFields(fields), isActive, selectedVacancyIds);
      toast.success(saveAsTemplate ? 'Сохранено в шаблоны' : 'Форма сохранена');
      return true;
    } catch (error) {
      // Жёсткая защита от дублей названия шаблонов — бэкенд (update_form)
      // возвращает 409 с конкретным текстом («Шаблон с названием «X» уже
      // существует»), показываем его вместо общей ошибки.
      const detail = (error as { response?: { status?: number; data?: { detail?: string } } })?.response;
      toast.error(detail?.status === 409 && detail.data?.detail ? detail.data.detail : 'Ошибка сохранения');
      return false;
    } finally {
      setSaving(false);
    }
  };

  // ── Автосейв (разовые анкеты «с нуля»): любое изменение полей/названия/etc.
  //    сохраняется в этом окне с дебаунсом, БЕЗ is_template (не попадает в
  //    библиотеку шаблонов). Кнопка «Сохранить» при autosave скрыта. ──
  const autoSaveTimer = useRef<number | null>(null);
  // Последние несохранённые данные — их досылаем при закрытии окна. Раньше
  // закрытие в первые 0,7 с после правки просто сбрасывало таймер, и правка
  // терялась (20.10.2026).
  const pendingAutoSave = useRef<Parameters<typeof updateForm>[1] | null>(null);
  useEffect(() => () => {
    if (pendingAutoSave.current) {
      void updateForm(formId, pendingAutoSave.current).catch(() => {});
      pendingAutoSave.current = null;
    }
  }, [formId]);
  // Пропускаем самый первый прогон эффекта (популяция стейта при загрузке формы),
  // чтобы не сохранять сразу после открытия.
  const skipFirstAutoSave = useRef(true);
  useEffect(() => {
    if (!autosave || loading) return;
    if (skipFirstAutoSave.current) {
      skipFirstAutoSave.current = false;
      return;
    }
    if (autoSaveTimer.current) window.clearTimeout(autoSaveTimer.current);
    setAutoSaveState('saving');
    const payload = {
      title: title.trim() || 'Без названия',
      description: description.trim() || undefined,
      fields: normalizeFields(fields),
      is_active: isActive,
      vacancy_ids: selectedVacancyIds,
      // is_template НЕ передаём — разовая анкета не попадает в шаблоны.
    };
    pendingAutoSave.current = payload;
    autoSaveTimer.current = window.setTimeout(async () => {
      try {
        await updateForm(formId, payload);
        if (pendingAutoSave.current === payload) pendingAutoSave.current = null;
        setAutoSaveState('saved');
      } catch {
        setAutoSaveState('error');
      }
    }, 700);
    return () => {
      if (autoSaveTimer.current) window.clearTimeout(autoSaveTimer.current);
    };
  }, [autosave, loading, formId, title, description, fields, isActive, selectedVacancyIds]);

  if (handleRef) {
    handleRef.current = {
      flush: async () => {
        const problem = formProblem(title, fields);
        if (problem) return problem;
        const payload = pendingAutoSave.current;
        if (payload) {
          if (autoSaveTimer.current) window.clearTimeout(autoSaveTimer.current);
          try {
            await updateForm(formId, payload);
            if (pendingAutoSave.current === payload) pendingAutoSave.current = null;
            setAutoSaveState('saved');
          } catch {
            setAutoSaveState('error');
            return 'Не удалось сохранить анкету — проверьте интернет и попробуйте ещё раз';
          }
        }
        return null;
      },
    };
  }

  const openTypePicker = (index: number) => {
    setInsertIndex(index);
    setShowTypePicker(true);
  };

  const addFieldAt = (index: number, type: FormField['type']) => {
    const newField: FormField = {
      id: nextFieldId(),
      type,
      label: TYPE_LABELS[type] || type,
      required: false,
    };
    if (['select', 'multiselect', 'radio'].includes(type)) {
      newField.options = ['Вариант 1', 'Вариант 2'];
    }
    if (type === 'scale') {
      newField.min = 1;
      newField.max = 10;
    }
    setFields(prev => {
      const next = [...prev];
      next.splice(index, 0, newField);
      return next;
    });
    setEditingFieldId(newField.id);
    setShowTypePicker(false);
  };

  const duplicateField = (id: string) => {
    setFields(prev => {
      const i = prev.findIndex(f => f.id === id);
      if (i === -1) return prev;
      const copy: FormField = {
        ...prev[i],
        id: nextFieldId(),
        options: prev[i].options ? [...prev[i].options!] : undefined,
      };
      const next = [...prev];
      next.splice(i + 1, 0, copy);
      return next;
    });
  };

  const moveField = (id: string, dir: -1 | 1) => {
    setFields(prev => {
      const i = prev.findIndex(f => f.id === id);
      const j = i + dir;
      if (i === -1 || j < 0 || j >= prev.length) return prev;
      const next = [...prev];
      [next[i], next[j]] = [next[j], next[i]];
      return next;
    });
  };

  const removeField = (id: string) => {
    setFields(prev => prev.filter(f => f.id !== id));
    if (editingFieldId === id) setEditingFieldId(null);
  };

  const updateField = (id: string, updates: Partial<FormField>) => {
    setFields(prev => prev.map(f => f.id === id ? { ...f, ...updates } : f));
  };

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center bg-gray-50">
        <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (!form) return null;

  // Только для предпросмотра (?preview=1): отправка по общему адресу отключена.
  // encodeURIComponent — у старых анкет в адресе бывает пробел.
  const publicUrl = `${window.location.origin}/form/${encodeURIComponent(form.slug)}`;

  return (
    <div className="min-h-full bg-gray-50 text-gray-900">
      {confirmLeave && (
        <HrConfirm
          title="Сохранить изменения в анкете?"
          subtitle={`«${title.trim() || 'Без названия'}»`}
          confirmLabel="Сохранить и выйти"
          secondary={{ label: 'Выйти без сохранения', onClick: () => { setConfirmLeave(false); onClose(); } }}
          busy={saving}
          inDialog={inDialog}
          onCancel={() => setConfirmLeave(false)}
          onConfirm={async () => {
            if (await handleSave()) {
              setConfirmLeave(false);
              onClose();
            } else {
              setConfirmLeave(false);
            }
          }}
        />
      )}
      {/* Header (light bar) */}
      <div className="sticky top-0 z-20 bg-white border-b border-gray-200">
        {/* На телефоне кнопки не помещались в строку, «Сохранить» уезжал за край
            (24.10.2026): подсказка прячется, у «Предпросмотра» остаётся значок. */}
        <div className="max-w-4xl mx-auto px-3 sm:px-6 py-3 flex items-center gap-2 sm:gap-3">
          <button
            onClick={handleBack}
            className="p-2 rounded-lg hover:bg-gray-100 text-gray-500 hover:text-gray-900 transition-colors"
            title="Назад"
          >
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div className="flex-1 min-w-0 hidden sm:block">
            {/* Раньше здесь была «Скопировать ссылку» на общий адрес анкеты, а
                сервер отправку по нему всегда отклоняет (403: анкета заполняется
                по ПЕРСОНАЛЬНОЙ ссылке). Кандидат заполнял всё и упирался в отказ
                на «Отправить» (20.10.2026). Отправляют из карточки кандидата. */}
            {!inDialog && (
              // В панели «Анкета» мы уже в карточке кандидата — подсказка лишняя.
              <span className="text-xs text-gray-500 truncate block">
                Отправить анкету — из карточки кандидата, чип «Анкета»: у каждого своя ссылка
              </span>
            )}
          </div>
          <div className="ml-auto flex flex-wrap items-center justify-end gap-2 min-w-0">
            <button
              onClick={() => setIsActive(!isActive)}
              className={clsx(
                'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors border',
                isActive
                  ? 'bg-emerald-50 border-emerald-200 text-emerald-700'
                  : 'bg-gray-50 border-gray-200 text-gray-500'
              )}
            >
              {isActive ? <ToggleRight className="w-4 h-4" /> : <ToggleLeft className="w-4 h-4" />}
              {isActive ? 'Активна' : 'Неактивна'}
            </button>
            <button
              onClick={() => window.open(`${publicUrl}?preview=1`, '_blank')}
              title="Предпросмотр"
              aria-label="Предпросмотр"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-gray-300 text-gray-700 hover:bg-gray-100 text-sm transition-colors"
            >
              <Eye className="w-4 h-4" />
              <span className="hidden sm:inline">Предпросмотр</span>
            </button>
            {autosave ? (
              // Разовая анкета: автосейв — индикатор вместо кнопки «Сохранить».
              <span
                className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-gray-500"
                aria-live="polite"
              >
                {autoSaveState === 'saving' ? (
                  <><Loader2 className="w-4 h-4 animate-spin" /> Сохранение…</>
                ) : autoSaveState === 'error' ? (
                  <span className="text-red-500">Ошибка сохранения</span>
                ) : autoSaveState === 'saved' ? (
                  <><Check className="w-4 h-4 text-emerald-600" /> Сохранено</>
                ) : (
                  <><Check className="w-4 h-4 text-gray-400" /> Автосохранение</>
                )}
              </span>
            ) : (
              <button
                onClick={handleSave}
                disabled={saving}
                className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium transition-colors disabled:opacity-50"
              >
                <Save className="w-4 h-4" />
                {saving ? 'Сохранение...' : 'Сохранить'}
              </button>
            )}
          </div>
        </div>
      </div>

      <div className="max-w-4xl mx-auto px-6 py-6">
        {/* Name */}
        <div className="mb-4">
          <label className="block text-sm font-medium text-gray-700 mb-1.5">Название анкеты</label>
          <input
            value={title}
            onChange={e => setTitle(e.target.value)}
            className="w-full px-3 py-2 bg-white border border-gray-300 rounded-lg text-sm font-medium text-gray-900 placeholder-gray-400 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 transition-colors"
            placeholder="Название анкеты"
          />
        </div>

        {/* Description */}
        <div className="mb-4">
          <label className="block text-sm font-medium text-gray-700 mb-1.5">
            Описание <span className="font-normal text-gray-400">(необязательно)</span>
          </label>
          <DescriptionEditor
            value={description}
            onChange={setDescription}
            placeholder="Например: о компании, условия, ссылки на сайт и соцсети"
          />
        </div>

        {/* Воронки шаблона (multi-select) — в каких воронках показывать этот
            шаблон в шаге выбора анкеты. Только для шаблонов; в разовых анкетах
            «с нуля» (autosave) скрыто. Привязка НЕ создаёт заявок по сабмиту. */}
        {!autosave && (
        <div className="mb-6">
          <label className="block text-sm text-gray-500 mb-1.5">Показывать в воронках</label>
          <div className="flex flex-wrap gap-2">
            {vacancies.map(v => {
              const selected = selectedVacancyIds.includes(v.id);
              return (
                <button
                  key={v.id}
                  type="button"
                  onClick={() => {
                    setSelectedVacancyIds(prev =>
                      selected ? prev.filter(id => id !== v.id) : [...prev, v.id]
                    );
                  }}
                  className={clsx(
                    'px-3 py-1.5 rounded-lg text-sm border transition-colors',
                    selected
                      ? 'bg-blue-50 border-blue-300 text-blue-700'
                      : 'bg-white border-gray-300 text-gray-600 hover:border-gray-400'
                  )}
                >
                  {v.title}
                </button>
              );
            })}
            {vacancies.length === 0 && (
              <span className="text-gray-400 text-sm">Нет доступных вакансий</span>
            )}
          </div>
        </div>
        )}

        {/* Canvas */}
        <div className="max-w-2xl mx-auto bg-white border border-gray-200 rounded-2xl shadow-sm p-6">
          {fields.length === 0 ? (
            <div className="text-center py-12 border-2 border-dashed border-gray-300 rounded-xl">
              <AlignLeft className="w-8 h-8 mx-auto mb-3 text-gray-300" />
              <p className="text-gray-500 mb-4">Пока нет вопросов</p>
              <button
                onClick={() => openTypePicker(0)}
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium transition-colors"
              >
                <Plus className="w-4 h-4" />
                Добавить вопрос
              </button>
            </div>
          ) : (
            <>
              {/* Inserter before the first block */}
              <InlineInserter onClick={() => openTypePicker(0)} />

              {fields.map((field, index) => (
                <div key={field.id}>
                  <QuestionBlock
                    field={field}
                    index={index}
                    total={fields.length}
                    isEditing={editingFieldId === field.id}
                    onEdit={() => setEditingFieldId(editingFieldId === field.id ? null : field.id)}
                    onDuplicate={() => duplicateField(field.id)}
                    onRemove={() => removeField(field.id)}
                    onUpdate={(updates) => updateField(field.id, updates)}
                    onMoveUp={() => moveField(field.id, -1)}
                    onMoveDown={() => moveField(field.id, 1)}
                  />
                  <InlineInserter onClick={() => openTypePicker(index + 1)} />
                </div>
              ))}
            </>
          )}
        </div>
      </div>

      {/* Type-picker modal "Добавить вопрос" */}
      <AnimatePresence>
        {showTypePicker && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4"
            onClick={() => setShowTypePicker(false)}
          >
            <motion.div
              initial={{ scale: 0.96, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.96, opacity: 0 }}
              onClick={e => e.stopPropagation()}
              className="bg-white border border-gray-200 rounded-2xl max-w-2xl w-full max-h-[80vh] overflow-hidden flex flex-col shadow-xl"
            >
              <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
                <h2 className="text-lg font-semibold text-gray-900">Добавить вопрос</h2>
                <button
                  onClick={() => setShowTypePicker(false)}
                  className="p-1 rounded-lg text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-colors text-xl leading-none w-8 h-8 flex items-center justify-center"
                >
                  &times;
                </button>
              </div>
              <div className="flex-1 overflow-y-auto p-6 space-y-6">
                {TYPE_GROUPS.map(group => (
                  <div key={group.title}>
                    <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-400 mb-3">
                      {group.title}
                    </h3>
                    <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                      {group.types.map(type => {
                        const ft = FIELD_TYPES.find(f => f.type === type);
                        if (!ft) return null;
                        const Icon = ft.icon;
                        return (
                          <button
                            key={type}
                            onClick={() => addFieldAt(insertIndex, type)}
                            className="flex items-center gap-3 px-3 py-3 rounded-xl border border-gray-200 bg-white hover:border-blue-400 hover:bg-blue-50/50 transition-colors text-left"
                          >
                            <span className="flex items-center justify-center w-9 h-9 rounded-lg bg-blue-50 text-blue-600 shrink-0">
                              <Icon className="w-5 h-5" />
                            </span>
                            <span className="text-sm font-medium text-gray-700">{ft.label}</span>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

    </div>
  );
}

// ============================================================
// Inline "+" inserter (thin full-width hover target)
// ============================================================

function InlineInserter({ onClick }: { onClick: () => void }) {
  return (
    <div className="group/inserter relative h-6 flex items-center justify-center">
      <button
        type="button"
        onClick={onClick}
        className="flex items-center justify-center w-full h-full"
        title="Добавить вопрос здесь"
      >
        <span className="absolute inset-x-0 top-1/2 -translate-y-1/2 h-px bg-blue-300 opacity-0 group-hover/inserter:opacity-100 transition-opacity" />
        <span className="relative z-10 flex items-center justify-center w-6 h-6 rounded-full bg-blue-600 text-white opacity-0 group-hover/inserter:opacity-100 transition-opacity shadow-sm">
          <Plus className="w-4 h-4" />
        </span>
      </button>
    </div>
  );
}

// ============================================================
// Question block — WYSIWYG preview + hover toolbar + settings
// ============================================================

function QuestionBlock({
  field,
  index,
  total,
  isEditing,
  onEdit,
  onDuplicate,
  onRemove,
  onUpdate,
  onMoveUp,
  onMoveDown,
}: {
  field: FormField;
  index: number;
  total: number;
  isEditing: boolean;
  onEdit: () => void;
  onDuplicate: () => void;
  onRemove: () => void;
  onUpdate: (updates: Partial<FormField>) => void;
  onMoveUp: () => void;
  onMoveDown: () => void;
}) {
  const hasOptions = ['select', 'multiselect', 'radio'].includes(field.type);
  const [newOption, setNewOption] = useState('');

  return (
    <div
      className={clsx(
        'relative group rounded-xl border transition-colors p-4',
        isEditing ? 'border-blue-400 bg-blue-50/30' : 'border-gray-200 hover:border-gray-300 bg-white'
      )}
    >
      {/* Number badge + preview */}
      <div className="flex gap-3">
        <span className="flex items-center justify-center w-6 h-6 rounded-full bg-gray-100 text-gray-500 text-xs font-medium shrink-0 mt-0.5">
          {index + 1}
        </span>
        <div className="flex-1 min-w-0 pointer-events-none select-none">
          <FieldRenderer field={field} value={previewValue(field)} onChange={() => {}} />
        </div>
      </div>

      {/* Hover toolbar */}
      <div className="absolute top-3 right-3 flex items-center gap-0.5 bg-white border border-gray-200 rounded-lg shadow-sm opacity-0 group-hover:opacity-100 transition-opacity">
        <button
          onClick={onMoveUp}
          disabled={index === 0}
          className="p-1.5 text-gray-400 hover:text-gray-700 transition-colors disabled:opacity-30 disabled:hover:text-gray-400"
          title="Выше"
        >
          <ArrowUp className="w-4 h-4" />
        </button>
        <button
          onClick={onMoveDown}
          disabled={index === total - 1}
          className="p-1.5 text-gray-400 hover:text-gray-700 transition-colors disabled:opacity-30 disabled:hover:text-gray-400"
          title="Ниже"
        >
          <ArrowDown className="w-4 h-4" />
        </button>
        <button
          onClick={onEdit}
          className={clsx(
            'p-1.5 transition-colors',
            isEditing ? 'text-blue-600' : 'text-gray-400 hover:text-gray-700'
          )}
          title="Настроить"
        >
          <Pencil className="w-4 h-4" />
        </button>
        <button
          onClick={onDuplicate}
          className="p-1.5 text-gray-400 hover:text-gray-700 transition-colors"
          title="Дублировать"
        >
          <Copy className="w-4 h-4" />
        </button>
        <button
          onClick={onRemove}
          className="p-1.5 text-gray-400 hover:text-red-500 transition-colors"
          title="Удалить"
        >
          <Trash2 className="w-4 h-4" />
        </button>
      </div>

      {/* Settings panel */}
      {isEditing && (
        <div className="mt-4 pt-4 border-t border-gray-200 bg-gray-50 -mx-4 -mb-4 px-4 pb-4 rounded-b-xl space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-gray-500 mb-1 block">Название поля</label>
                  <input
                    value={field.label}
                    onChange={e => onUpdate({ label: e.target.value })}
                    className="w-full px-3 py-1.5 bg-white border border-gray-300 rounded-lg text-sm text-gray-900 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 transition-colors"
                  />
                </div>
                <div>
                  <label className="text-xs text-gray-500 mb-1 block">Placeholder</label>
                  <input
                    value={field.placeholder || ''}
                    onChange={e => onUpdate({ placeholder: e.target.value || undefined })}
                    className="w-full px-3 py-1.5 bg-white border border-gray-300 rounded-lg text-sm text-gray-900 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 transition-colors"
                    placeholder="Подсказка..."
                  />
                </div>
              </div>

              <div className="flex items-center gap-4 flex-wrap">
                <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={field.required}
                    onChange={e => onUpdate({ required: e.target.checked })}
                    className="w-4 h-4 rounded border-gray-300 bg-white text-blue-600 focus:ring-blue-500"
                  />
                  Обязательное поле
                </label>

                <div className="flex items-center gap-2">
                  <label className="text-xs text-gray-500">Тип:</label>
                  <select
                    value={field.type}
                    onChange={e => {
                      const newType = e.target.value as FormField['type'];
                      const updates: Partial<FormField> = { type: newType };
                      if (['select', 'multiselect', 'radio'].includes(newType) && !field.options?.length) {
                        updates.options = ['Вариант 1', 'Вариант 2'];
                      }
                      onUpdate(updates);
                    }}
                    className="px-2 py-1 bg-white border border-gray-300 rounded-lg text-sm text-gray-900 outline-none focus:border-blue-500"
                  >
                    {FIELD_TYPES.map(ft => (
                      <option key={ft.type} value={ft.type}>{ft.label}</option>
                    ))}
                  </select>
                </div>
              </div>

              {hasOptions && (
                <div>
                  <label className="text-xs text-gray-500 mb-1 block">Варианты ответа</label>
                  <div className="space-y-1">
                    {(field.options || []).map((opt, i) => (
                      <div key={i} className="flex items-center gap-2">
                        <input
                          value={opt}
                          onChange={e => {
                            const newOpts = [...(field.options || [])];
                            newOpts[i] = e.target.value;
                            onUpdate({ options: newOpts });
                          }}
                          className="flex-1 px-3 py-1 bg-white border border-gray-300 rounded-lg text-sm text-gray-900 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 transition-colors"
                        />
                        <button
                          onClick={() => {
                            const newOpts = (field.options || []).filter((_, j) => j !== i);
                            onUpdate({ options: newOpts });
                          }}
                          className="p-1 text-gray-400 hover:text-red-500 transition-colors"
                        >
                          <Trash2 className="w-3 h-3" />
                        </button>
                      </div>
                    ))}
                    <div className="flex items-center gap-2">
                      <input
                        value={newOption}
                        onChange={e => setNewOption(e.target.value)}
                        onKeyDown={e => {
                          if (e.key === 'Enter' && newOption.trim()) {
                            onUpdate({ options: [...(field.options || []), newOption.trim()] });
                            setNewOption('');
                          }
                        }}
                        placeholder="Добавить вариант..."
                        className="flex-1 px-3 py-1 bg-white border border-dashed border-gray-300 rounded-lg text-sm text-gray-500 outline-none focus:border-blue-500"
                      />
                      <button
                        onClick={() => {
                          if (newOption.trim()) {
                            onUpdate({ options: [...(field.options || []), newOption.trim()] });
                            setNewOption('');
                          }
                        }}
                        className="p-1 text-gray-400 hover:text-blue-600 transition-colors"
                      >
                        <Plus className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {field.type === 'scale' && (
                <div>
                  <label className="text-xs text-gray-500 mb-1 block">Диапазон шкалы</label>
                  <div className="flex items-center gap-3">
                    <div>
                      <label className="text-xs text-gray-400 mb-0.5 block">Минимум</label>
                      <input
                        type="number"
                        value={field.min ?? 1}
                        onChange={e => { const n = parseInt(e.target.value, 10); onUpdate({ min: Number.isNaN(n) ? 1 : n }); }}
                        className="w-20 px-3 py-1.5 bg-white border border-gray-300 rounded-lg text-sm text-gray-900 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 transition-colors"
                      />
                    </div>
                    <div>
                      <label className="text-xs text-gray-400 mb-0.5 block">Максимум</label>
                      <input
                        type="number"
                        value={field.max ?? 10}
                        onChange={e => { const n = parseInt(e.target.value, 10); onUpdate({ max: Number.isNaN(n) ? 10 : n }); }}
                        className="w-20 px-3 py-1.5 bg-white border border-gray-300 rounded-lg text-sm text-gray-900 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 transition-colors"
                      />
                    </div>
                  </div>
                </div>
              )}

        </div>
      )}
    </div>
  );
}
