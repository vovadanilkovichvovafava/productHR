import { useState, useEffect, useMemo, useRef } from 'react';
import type { ReactNode } from 'react';
import { createPortal } from 'react-dom';
import clsx from 'clsx';
import toast from 'react-hot-toast';
import { escapeHtml } from '@/utils/linkify';
import { useLinkPrompt, wrapRangeWithLink } from '@/components/hr/LinkPrompt';

// Части формы вакансии: редактор текста, календарь дедлайна, выпадающий
// список и иконки (вынесено из VacancyForm, 20.10.2026).

export type HfSelectOption = {
  value: string | number;
  label: string;
  icon?: ReactNode;
};

type HfSelectMenuRect = {
  left: number;
  top: number;
};

function HfSpriteIcon({ id, className }: { id: string; className?: string }) {
  return (
    <svg className={className} viewBox="0 0 20 20" aria-hidden="true">
      <use href={`/huntflow-sprite.svg#${id}`} />
    </svg>
  );
}

// F1: WYSIWYG rich-text редактор (contentEditable). Кнопки реально форматируют
// через execCommand, списки продолжаются по Enter (нативно в браузере), значение
// хранится как HTML и рендерится с санитайзером в VacancyDetail/VacancyDetailModal.
export function RichTextField({
  value,
  onChange,
  disabled,
}: {
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  // Активные форматы под курсором — чтобы кнопки визуально «нажимались»
  // (иначе жирный/курсив срабатывали, но было не видно, что применено).
  const [activeFormats, setActiveFormats] = useState<Record<string, boolean>>({});

  // Инициализация / внешняя синхронизация без перезаписи при наборе (курсор не прыгает).
  useEffect(() => {
    const el = ref.current;
    if (el && el.innerHTML !== (value || '')) el.innerHTML = value || '';
  }, [value]);

  const sync = () => onChange(ref.current?.innerHTML || '');

  const refreshActiveFormats = () => {
    if (document.activeElement !== ref.current) return;
    setActiveFormats({
      bold: document.queryCommandState('bold'),
      italic: document.queryCommandState('italic'),
      underline: document.queryCommandState('underline'),
      insertUnorderedList: document.queryCommandState('insertUnorderedList'),
      insertOrderedList: document.queryCommandState('insertOrderedList'),
    });
  };

  // Курсор/выделение может двигаться кликом или стрелками без событий на самом
  // contentEditable — слушаем на уровне document и фильтруем по фокусу.
  useEffect(() => {
    document.addEventListener('selectionchange', refreshActiveFormats);
    return () => document.removeEventListener('selectionchange', refreshActiveFormats);
  }, []);

  const exec = (command: string, arg?: string) => {
    if (disabled) return;
    ref.current?.focus();
    document.execCommand(command, false, arg);
    sync();
    refreshActiveFormats();
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
    if (disabled) return;
    const selection = window.getSelection();
    savedRangeRef.current =
      selection && selection.rangeCount ? selection.getRangeAt(0).cloneRange() : null;
    void requestLink(selection?.toString() || '');
  };

  // Копирует содержимое поля целиком, сохраняя форматирование (жирный,
  // списки и т.п.) — при вставке в Word/Google Docs/почту оно применится;
  // в обычные текстовые поля вставится как plain text (браузер сам выбирает
  // подходящий MIME из clipboard item). ClipboardItem поддерживается не
  // везде (недоступен вне https/localhost) — тогда откатываемся на голый текст.
  const copyContent = async () => {
    const html = ref.current?.innerHTML || '';
    const text = ref.current?.innerText || '';
    if (!html && !text) return;
    try {
      if (typeof ClipboardItem !== 'undefined') {
        await navigator.clipboard.write([
          new ClipboardItem({
            'text/html': new Blob([html], { type: 'text/html' }),
            'text/plain': new Blob([text], { type: 'text/plain' }),
          }),
        ]);
      } else {
        await navigator.clipboard.writeText(text);
      }
      toast.success('Скопировано');
    } catch {
      toast.error('Не удалось скопировать');
    }
  };

  const btnClass = 'hf-vacancy-editor-btn flex items-center justify-center';

  return (
    <div className="hf-vacancy-editor">
      {linkModal}
      <div className="hf-vacancy-editor-toolbar flex items-center">
        <button type="button" aria-label="Жирный" aria-pressed={activeFormats.bold} disabled={disabled}
          className={clsx(btnClass, activeFormats.bold && 'hf-vacancy-editor-btn-active')}
          onMouseDown={(e) => { e.preventDefault(); exec('bold'); }}>
          <HfSpriteIcon id="bold" className="hf-vacancy-editor-icon" />
        </button>
        <button type="button" aria-label="Курсив" aria-pressed={activeFormats.italic} disabled={disabled}
          className={clsx(btnClass, activeFormats.italic && 'hf-vacancy-editor-btn-active')}
          onMouseDown={(e) => { e.preventDefault(); exec('italic'); }}>
          <HfSpriteIcon id="italic" className="hf-vacancy-editor-icon" />
        </button>
        <button type="button" aria-label="Подчёркнутый" aria-pressed={activeFormats.underline} disabled={disabled}
          className={clsx(btnClass, activeFormats.underline && 'hf-vacancy-editor-btn-active')}
          onMouseDown={(e) => { e.preventDefault(); exec('underline'); }}>
          <span className="text-[13px] font-semibold leading-none underline">U</span>
        </button>
        <button type="button" aria-label="Маркированный список" aria-pressed={activeFormats.insertUnorderedList} disabled={disabled}
          className={clsx(btnClass, activeFormats.insertUnorderedList && 'hf-vacancy-editor-btn-active')}
          onMouseDown={(e) => { e.preventDefault(); exec('insertUnorderedList'); }}>
          <HfSpriteIcon id="bullet-list" className="hf-vacancy-editor-icon" />
        </button>
        <button type="button" aria-label="Нумерованный список" aria-pressed={activeFormats.insertOrderedList} disabled={disabled}
          className={clsx(btnClass, activeFormats.insertOrderedList && 'hf-vacancy-editor-btn-active')}
          onMouseDown={(e) => { e.preventDefault(); exec('insertOrderedList'); }}>
          <HfSpriteIcon id="numbered-list" className="hf-vacancy-editor-icon" />
        </button>
        <button type="button" aria-label="Ссылка" disabled={disabled} className={btnClass}
          onMouseDown={(e) => { e.preventDefault(); addLink(); }}>
          <HfSpriteIcon id="link" className="hf-vacancy-editor-icon" />
        </button>
        <button type="button" aria-label="Копировать" title="Копировать текст" className={btnClass}
          onMouseDown={(e) => { e.preventDefault(); copyContent(); }}>
          <HfSpriteIcon id="clipboard" className="hf-vacancy-editor-icon" />
        </button>
      </div>
      <div
        ref={ref}
        contentEditable={!disabled}
        suppressContentEditableWarning
        role="textbox"
        aria-multiline="true"
        onInput={sync}
        onKeyUp={refreshActiveFormats}
        onMouseUp={refreshActiveFormats}
        onFocus={refreshActiveFormats}
        onBlur={() => setActiveFormats({})}
        onPaste={(e) => {
          e.preventDefault();
          const text = e.clipboardData.getData('text/plain');
          document.execCommand('insertText', false, text);
        }}
        className="hf-vacancy-textarea hf-vacancy-richtext"
      />
    </div>
  );
}

const WEEKDAYS_MON_FIRST = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];

function toDeadlineIso(y: number, m: number, d: number): string {
  // Дедлайн = конец выбранного дня. ВАЖНО: если писать T00:00:00, для «сегодня»
  // бэк (validate_closes_at, naive datetime.utcnow()) сочтёт момент уже прошедшим
  // и отклонит 422-й — «closes_at cannot be in the past».
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${y}-${pad(m + 1)}-${pad(d)}T23:59:59`;
}

// F-fix: «Без дедлайна» была нередактируемым readOnly-инпутом — просто текст,
// без реальной привязки к closes_at. Заменил на попап-календарь: сегодня и
// будущее кликабельны, прошлые дни — нет.
export function DeadlinePicker({
  value,
  onChange,
  disabled,
}: {
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [menuPos, setMenuPos] = useState<{ left: number; top: number } | null>(null);
  const btnRef = useRef<HTMLButtonElement>(null);

  const today = useMemo(() => {
    const t = new Date();
    t.setHours(0, 0, 0, 0);
    return t;
  }, []);

  const selectedDate = useMemo(() => {
    if (!value) return null;
    const d = new Date(value);
    return Number.isNaN(d.getTime()) ? null : d;
  }, [value]);

  const [viewMonth, setViewMonth] = useState(() => {
    const base = selectedDate || today;
    return new Date(base.getFullYear(), base.getMonth(), 1);
  });

  useEffect(() => {
    if (open) {
      const base = selectedDate || today;
      setViewMonth(new Date(base.getFullYear(), base.getMonth(), 1));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const closeOnOutside = (event: PointerEvent) => {
      const target = event.target as Element | null;
      if (!target?.closest('[data-deadline-root]') && !target?.closest('[data-deadline-menu]')) {
        setOpen(false);
      }
    };
    document.addEventListener('pointerdown', closeOnOutside);
    return () => document.removeEventListener('pointerdown', closeOnOutside);
  }, [open]);

  const openPicker = () => {
    if (disabled) return;
    const r = btnRef.current?.getBoundingClientRect();
    if (r) setMenuPos({ left: r.left, top: r.bottom + 4 });
    setOpen(true);
  };

  const monthLabel = viewMonth.toLocaleDateString('ru-RU', { month: 'long', year: 'numeric' });
  const firstWeekday = (new Date(viewMonth.getFullYear(), viewMonth.getMonth(), 1).getDay() + 6) % 7;
  const daysInMonth = new Date(viewMonth.getFullYear(), viewMonth.getMonth() + 1, 0).getDate();
  const cells: (number | null)[] = [
    ...Array(firstWeekday).fill(null),
    ...Array.from({ length: daysInMonth }, (_, i) => i + 1),
  ];

  const displayValue = selectedDate
    ? selectedDate.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' })
    : 'Без дедлайна';

  const menu = open && menuPos ? createPortal(
    <div
      data-deadline-menu
      className="hf-vacancy-calendar-menu"
      style={{ left: menuPos.left, top: menuPos.top }}
    >
      <div className="hf-vacancy-calendar-header">
        <button
          type="button"
          className="hf-vacancy-calendar-nav"
          onClick={() => setViewMonth(new Date(viewMonth.getFullYear(), viewMonth.getMonth() - 1, 1))}
          aria-label="Предыдущий месяц"
        >
          ‹
        </button>
        <span className="hf-vacancy-calendar-title">{monthLabel}</span>
        <button
          type="button"
          className="hf-vacancy-calendar-nav"
          onClick={() => setViewMonth(new Date(viewMonth.getFullYear(), viewMonth.getMonth() + 1, 1))}
          aria-label="Следующий месяц"
        >
          ›
        </button>
      </div>
      <div className="hf-vacancy-calendar-weekdays">
        {WEEKDAYS_MON_FIRST.map((w) => (
          <span key={w}>{w}</span>
        ))}
      </div>
      <div className="hf-vacancy-calendar-grid">
        {cells.map((day, i) => {
          if (day === null) return <span key={`blank-${i}`} />;
          const cellDate = new Date(viewMonth.getFullYear(), viewMonth.getMonth(), day);
          const isPast = cellDate < today;
          const isToday = cellDate.getTime() === today.getTime();
          const isSelected = !!selectedDate
            && cellDate.getFullYear() === selectedDate.getFullYear()
            && cellDate.getMonth() === selectedDate.getMonth()
            && cellDate.getDate() === selectedDate.getDate();
          return (
            <button
              key={day}
              type="button"
              disabled={isPast}
              className={clsx(
                'hf-vacancy-calendar-day',
                isPast && 'hf-vacancy-calendar-day-disabled',
                isToday && 'hf-vacancy-calendar-day-today',
                isSelected && 'hf-vacancy-calendar-day-selected',
              )}
              onClick={() => {
                onChange(toDeadlineIso(viewMonth.getFullYear(), viewMonth.getMonth(), day));
                setOpen(false);
              }}
            >
              {day}
            </button>
          );
        })}
      </div>
      <button
        type="button"
        className="hf-vacancy-calendar-clear"
        onClick={() => { onChange(''); setOpen(false); }}
      >
        Без дедлайна
      </button>
    </div>,
    document.body,
  ) : null;

  return (
    <div data-deadline-root>
      <button
        ref={btnRef}
        type="button"
        disabled={disabled}
        className="hf-vacancy-input hf-vacancy-deadline-trigger"
        onClick={openPicker}
      >
        <span className={clsx(!selectedDate && 'hf-vacancy-deadline-placeholder')}>{displayValue}</span>
      </button>
      {menu}
    </div>
  );
}

export function HuntflowClose28Icon({ className }: { className?: string }) {
  return (
    <svg aria-hidden="true" viewBox="0 0 28 28" className={className} fill="none">
      <path
        d="M19.833 8.167 8.167 19.833m0-11.666 11.666 11.666"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function HuntflowChevronDown24Icon({ className }: { className?: string }) {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" className={className} fill="none">
      <path
        d="M7.5 10.5 12 15l4.5-4.5"
        stroke="currentColor"
        strokeWidth="1.3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function HuntflowEyeOffIcon({ className }: { className?: string }) {
  return (
    <svg aria-hidden="true" viewBox="0 0 20 20" className={className} fill="none">
      <path
        d="m2.5 2.5 15 15M8.233 8.233A2.083 2.083 0 0 0 10 12.083c.557 0 1.063-.218 1.437-.573M6.821 6.821C4.04 8.116 2.5 10 2.5 10s2.727 5 7.5 5a8.53 8.53 0 0 0 3.179-.595M10 5c4.773 0 7.5 5 7.5 5a13.218 13.218 0 0 1-1.722 2.24"
        stroke="currentColor"
        strokeWidth="1.3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function HuntflowCheckIcon({ className }: { className?: string }) {
  return (
    <svg aria-hidden="true" viewBox="0 0 20 20" className={className} fill="none">
      <path
        d="m5 10.25 3.125 3.125L15 6.5"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function HuntflowFlagIcon({ className }: { className?: string }) {
  return (
    <svg aria-hidden="true" viewBox="0 0 20 20" className={className} fill="currentColor">
      <path d="M5.5 3.75a.75.75 0 0 1 .75-.75h7.27a.75.75 0 0 1 .66 1.106l-1.58 2.925 1.58 2.925a.75.75 0 0 1-.66 1.106H7v5.188a.75.75 0 0 1-1.5 0V3.75Z" />
    </svg>
  );
}

/**
 * Выпадающий список формы вакансии (валюта, видимость, песочница, приоритет).
 * Раньше был объявлен ВНУТРИ формы — каждое нажатие клавиши в любом поле
 * создавало новый тип компонента, и все списки пересоздавались вместе с
 * открытым меню. Теперь самостоятельный (20.10.2026); открыт не больше одного:
 * нажатие мимо (в том числе на другой список) закрывает меню.
 */
export function HfSelect({
  value,
  options,
  disabled,
  showSelectedIcon,
  onChange,
}: {
  value: string | number;
  options: HfSelectOption[];
  disabled?: boolean;
  showSelectedIcon?: boolean;
  onChange?: (value: string) => void;
}) {
  const [menuRect, setMenuRect] = useState<HfSelectMenuRect | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const isOpen = !!menuRect && !disabled;
  const close = () => setMenuRect(null);

  useEffect(() => {
    if (!isOpen) return;
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target as Node | null;
      if (target && (rootRef.current?.contains(target) || menuRef.current?.contains(target))) return;
      setMenuRect(null);
    };
    document.addEventListener('pointerdown', onPointerDown);
    return () => document.removeEventListener('pointerdown', onPointerDown);
  }, [isOpen]);

  const selectedOption = options.find((option) => String(option.value) === String(value)) || options[0];
  const menu = isOpen && menuRect ? createPortal(
    <div
      ref={menuRef}
      className="hf-vacancy-select-menu"
      data-hf-select-menu
      style={{ left: menuRect.left, top: menuRect.top }}
    >
      {options.map((option) => {
        const isSelected = String(option.value) === String(value);
        const icon = option.icon || (showSelectedIcon && isSelected ? <HuntflowCheckIcon className="hf-vacancy-select-icon-svg" /> : null);
        return (
          <button
            key={String(option.value)}
            type="button"
            className={clsx("hf-vacancy-select-option", isSelected && "hf-vacancy-select-option-active")}
            onMouseDown={(event) => {
              event.preventDefault();
              onChange?.(String(option.value));
              close();
            }}
          >
            <span className="hf-vacancy-select-option-inner">
              <span className="hf-vacancy-select-option-icon">
                {icon}
              </span>
              <span className="truncate">{option.label}</span>
            </span>
          </button>
        );
      })}
    </div>,
    document.body,
  ) : null;

  return (
    <div ref={rootRef} className="hf-vacancy-select-wrap" data-hf-select-root>
      <button
        type="button"
        disabled={disabled}
        className={clsx("hf-vacancy-input", "hf-vacancy-select-trigger", isOpen && "hf-vacancy-select-trigger-open")}
        onClick={(event) => {
          if (isOpen) {
            close();
            return;
          }
          const rect = event.currentTarget.getBoundingClientRect();
          setMenuRect({
            left: rect.left,
            top: rect.bottom + Number.parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--hf-vacancy-select-menu-top")),
          });
        }}
      >
        <span className="hf-vacancy-select-label">
          <span className="truncate">{selectedOption?.label}</span>
        </span>
        <HuntflowChevronDown24Icon className="hf-vacancy-select-chevron" />
      </button>
      {menu}
    </div>
  );
}
