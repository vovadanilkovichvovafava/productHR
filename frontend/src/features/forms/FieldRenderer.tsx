import { useState, useEffect, useMemo, useRef } from 'react';
import { Calendar as CalendarIcon, ChevronDown } from 'lucide-react';
import clsx from 'clsx';
import type { FormField } from '@/services/api/forms';
// Старые анкеты могли сохраниться с пустыми и повторяющимися вариантами —
// кандидату их не показываем (20.10.2026).
import { cleanOptions } from './formValidation';

const WEEKDAYS_MON_FIRST = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];
const MONTH_NAMES = [
  'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
  'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь',
];
// Диапазон лет с запасом в обе стороны: назад достаточно для даты рождения,
// вперёд — для дедлайнов.
const DATE_PICKER_MIN_YEAR = 1930;
const DATE_PICKER_MAX_FUTURE_YEARS = 2;

/**
 * Попап-календарь для поля типа «Дата» (клик по полю открывает выбор дня).
 */
function DateFieldPicker({
  value,
  onChange,
}: {
  value: string;
  onChange: (value: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  const selectedDate = useMemo(() => {
    if (!value) return null;
    const d = new Date(`${value}T00:00:00`);
    return Number.isNaN(d.getTime()) ? null : d;
  }, [value]);

  const [viewDate, setViewDate] = useState(() => selectedDate || new Date());

  useEffect(() => {
    if (open) setViewDate(selectedDate || new Date());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onOutside = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onOutside);
    return () => document.removeEventListener('mousedown', onOutside);
  }, [open]);

  const year = viewDate.getFullYear();
  const month = viewDate.getMonth();
  const firstWeekday = (new Date(year, month, 1).getDay() + 6) % 7;
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const cells: (number | null)[] = [
    ...Array(firstWeekday).fill(null),
    ...Array.from({ length: daysInMonth }, (_, i) => i + 1),
  ];
  const currentYear = new Date().getFullYear();
  const years = Array.from(
    { length: (currentYear + DATE_PICKER_MAX_FUTURE_YEARS) - DATE_PICKER_MIN_YEAR + 1 },
    (_, i) => (currentYear + DATE_PICKER_MAX_FUTURE_YEARS) - i,
  );
  const toIso = (y: number, m: number, d: number) =>
    `${y}-${String(m + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
  const todayStr = new Date().toDateString();
  const displayValue = selectedDate
    ? selectedDate.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' })
    : 'Выберите дату';

  return (
    <div className="relative" ref={rootRef}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center gap-2 px-4 py-2.5 border border-gray-300 bg-white rounded-xl text-left outline-none transition-colors focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 hover:border-gray-400"
      >
        <CalendarIcon className="w-4 h-4 text-gray-400 flex-shrink-0" />
        <span className={selectedDate ? 'text-gray-900' : 'text-gray-400'}>{displayValue}</span>
      </button>
      {open && (
        <div className="absolute z-50 mt-1.5 w-72 bg-white border border-gray-200 rounded-xl shadow-lg p-3">
          <div className="flex items-center gap-2 mb-2">
            {/* appearance-none + свой ChevronDown — нативная стрелка браузера
                накладывалась на текст года (узкий select, "199X" почти впритык
                к краю), да и вся пара month/year выглядела тускло (светлая
                border-gray-200 + слабый контраст текста). border-gray-300 +
                text-gray-900 + явный правый паддинг под иконку — как у
                остальных полей ввода в этом файле. */}
            <div className="relative flex-1 min-w-0">
              <select
                value={month}
                onChange={(e) => setViewDate(new Date(year, Number(e.target.value), 1))}
                className="w-full appearance-none text-sm font-medium text-gray-900 border border-gray-300 rounded-lg pl-2.5 pr-7 py-1.5 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 transition-colors"
                style={{ WebkitAppearance: 'none', MozAppearance: 'none' }}
              >
                {MONTH_NAMES.map((m, i) => (
                  <option key={m} value={i}>{m}</option>
                ))}
              </select>
              <ChevronDown className="hf-date-picker-chevron pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-500" />
            </div>
            <div className="relative shrink-0">
              <select
                value={year}
                onChange={(e) => setViewDate(new Date(Number(e.target.value), month, 1))}
                className="w-[92px] appearance-none text-sm font-medium text-gray-900 border border-gray-300 rounded-lg pl-2.5 pr-7 py-1.5 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 transition-colors"
                style={{ WebkitAppearance: 'none', MozAppearance: 'none' }}
              >
                {years.map((y) => (
                  <option key={y} value={y}>{y}</option>
                ))}
              </select>
              <ChevronDown className="hf-date-picker-chevron pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-500" />
            </div>
          </div>
          <div className="grid grid-cols-7 gap-1 text-center text-xs text-gray-400 mb-1">
            {WEEKDAYS_MON_FIRST.map((w) => (
              <span key={w}>{w}</span>
            ))}
          </div>
          <div className="grid grid-cols-7 gap-1">
            {cells.map((day, i) => {
              if (day === null) return <span key={`b${i}`} />;
              const isSelected = !!selectedDate
                && selectedDate.getFullYear() === year
                && selectedDate.getMonth() === month
                && selectedDate.getDate() === day;
              const isToday = new Date(year, month, day).toDateString() === todayStr;
              return (
                <button
                  key={day}
                  type="button"
                  onClick={() => { onChange(toIso(year, month, day)); setOpen(false); }}
                  className={clsx(
                    'h-8 w-8 flex items-center justify-center rounded-full text-sm transition-colors',
                    isSelected
                      ? 'bg-blue-600 text-white'
                      : isToday
                        ? 'border border-blue-400 text-blue-600'
                        : 'text-gray-700 hover:bg-gray-100',
                  )}
                >
                  {day}
                </button>
              );
            })}
          </div>
          {selectedDate && (
            <button
              type="button"
              onClick={() => { onChange(''); setOpen(false); }}
              className="mt-2 w-full text-xs text-gray-500 hover:text-gray-700 text-center py-1"
            >
              Очистить
            </button>
          )}
        </div>
      )}
    </div>
  );
}

export function FieldRenderer({
  field,
  value,
  onChange,
  onFileChange,
  selectedFile,
  error,
}: {
  field: FormField;
  value: unknown;
  onChange: (val: unknown) => void;
  onFileChange?: (file: File | null) => void;
  selectedFile?: File | null;
  error?: string;
}) {
  const inputClasses = `w-full px-4 py-2.5 border rounded-xl text-gray-900 placeholder-gray-400 outline-none transition-colors focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 ${
    error ? 'border-red-300 bg-red-50' : 'border-gray-300 bg-white'
  }`;

  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-1.5">
        {field.label}
        {field.required && <span className="text-red-500 ml-1">*</span>}
      </label>

      {field.type === 'text' && (
        <input
          type="text"
          value={String(value || '')}
          onChange={e => onChange(e.target.value)}
          placeholder={field.placeholder}
          className={inputClasses}
        />
      )}

      {field.type === 'email' && (
        <input
          type="email"
          value={String(value || '')}
          onChange={e => onChange(e.target.value)}
          placeholder={field.placeholder || 'email@example.com'}
          className={inputClasses}
        />
      )}

      {field.type === 'phone' && (
        <input
          type="tel"
          inputMode="tel"
          value={String(value || '')}
          // Только телефонные символы: цифры, +, пробел, скобки, дефис. Буквы не пускаем.
          onChange={e => onChange(e.target.value.replace(/[^\d+()\-\s]/g, ''))}
          placeholder={field.placeholder || '+7 (999) 123-45-67'}
          className={inputClasses}
        />
      )}

      {field.type === 'textarea' && (
        <textarea
          value={String(value || '')}
          onChange={e => onChange(e.target.value)}
          placeholder={field.placeholder}
          rows={4}
          className={inputClasses + ' resize-y'}
        />
      )}

      {field.type === 'select' && (
        <select
          value={String(value || '')}
          onChange={e => onChange(e.target.value)}
          className={inputClasses}
        >
          <option value="">-- Выберите --</option>
          {cleanOptions(field.options).map((opt, i) => (
            <option key={`${i}:${opt}`} value={opt}>{opt}</option>
          ))}
        </select>
      )}

      {field.type === 'radio' && (
        <div className="space-y-2 mt-1">
          {cleanOptions(field.options).map((opt, i) => (
            <label key={`${i}:${opt}`} className="flex items-center gap-3 cursor-pointer group">
              <input
                type="radio"
                name={field.id}
                value={opt}
                checked={value === opt}
                onChange={() => onChange(opt)}
                className="w-4 h-4 text-blue-600 border-gray-300 focus:ring-blue-500"
              />
              <span className="text-gray-700 group-hover:text-gray-900 transition-colors">{opt}</span>
            </label>
          ))}
        </div>
      )}

      {field.type === 'multiselect' && (
        <div className="space-y-2 mt-1">
          {cleanOptions(field.options).map((opt, i) => {
            const selected = Array.isArray(value) ? value as string[] : [];
            const isChecked = selected.includes(opt);
            return (
              <label key={`${i}:${opt}`} className="flex items-center gap-3 cursor-pointer group">
                <input
                  type="checkbox"
                  checked={isChecked}
                  onChange={() => {
                    if (isChecked) {
                      onChange(selected.filter(v => v !== opt));
                    } else {
                      onChange([...selected, opt]);
                    }
                  }}
                  className="w-4 h-4 rounded text-blue-600 border-gray-300 focus:ring-blue-500"
                />
                <span className="text-gray-700 group-hover:text-gray-900 transition-colors">{opt}</span>
              </label>
            );
          })}
        </div>
      )}

      {field.type === 'date' && (
        <DateFieldPicker
          value={String(value || '')}
          onChange={onChange}
        />
      )}

      {field.type === 'url' && (
        <input
          type="url"
          value={String(value || '')}
          onChange={e => onChange(e.target.value)}
          placeholder={field.placeholder || 'https://...'}
          className={inputClasses}
        />
      )}

      {field.type === 'scale' && (
        <div className="flex flex-wrap gap-2 mt-1">
          {Array.from({ length: (field.max ?? 10) - (field.min ?? 1) + 1 }, (_, i) => (field.min ?? 1) + i).map(n => (
            <button
              type="button"
              key={n}
              onClick={() => onChange(n)}
              className={`w-10 h-10 rounded-full border text-sm transition-colors ${
                value === n ? 'bg-blue-600 text-white border-blue-600' : 'border-gray-300 text-gray-600 hover:border-blue-400'
              }`}
            >
              {n}
            </button>
          ))}
        </div>
      )}

      {field.type === 'file' && (
        <div className="mt-1">
          {selectedFile ? (
            <div className="flex items-center gap-3 px-4 py-3 border border-gray-300 rounded-xl bg-gray-50">
              <svg className="w-6 h-6 text-blue-500 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              <div className="flex-1 min-w-0">
                <p className="text-sm text-gray-900 truncate">{selectedFile.name}</p>
                <p className="text-xs text-gray-500">{(selectedFile.size / 1024 / 1024).toFixed(1)} МБ</p>
              </div>
              <button
                type="button"
                onClick={() => {
                  onChange('');
                  onFileChange?.(null);
                }}
                className="text-gray-400 hover:text-red-500 transition-colors"
              >
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          ) : (
            <label className="flex items-center justify-center w-full px-4 py-6 border-2 border-dashed border-gray-300 rounded-xl cursor-pointer hover:border-blue-400 hover:bg-blue-50/50 transition-colors">
              <div className="text-center">
                <svg className="w-8 h-8 text-gray-400 mx-auto mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                </svg>
                <span className="text-sm text-gray-500">Нажмите для выбора файла</span>
                <span className="block text-xs text-gray-400 mt-1">PDF, DOC, JPG, PNG — до 10 МБ · видео MP4/MOV/AVI — до 100 МБ</span>
              </div>
              <input
                type="file"
                className="hidden"
                accept=".pdf,.doc,.docx,.jpg,.jpeg,.png,.webp,.mp4,.mov,.avi,video/mp4,video/quicktime,video/x-msvideo"
                onChange={e => {
                  const file = e.target.files?.[0];
                  if (file) {
                    onChange(file.name);
                    onFileChange?.(file);
                  }
                }}
              />
            </label>
          )}
        </div>
      )}

      {error && (
        <p className="text-red-500 text-xs mt-1">{error}</p>
      )}
    </div>
  );
}
