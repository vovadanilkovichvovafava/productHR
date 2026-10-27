import { useState, useEffect } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import { getPublicForm, submitPublicForm, submitPublicFormWithFiles, getPublicFormByToken, submitPublicFormByToken, submitPublicFormByTokenWithFiles, type SkippedFile, type SubmitWithFilesResult } from '@/services/api/forms';
import type { PublicFormData } from '@/services/api/forms';
import { FieldRenderer } from '@/features/forms/FieldRenderer';
import { sanitizeHtml } from '@/utils/sanitizeHtml';
import { autoLinkify } from '@/utils/linkify';
import {
  clearDraft,
  describeSubmitError,
  draftKey,
  hasAnswers,
  loadDraft,
  mergeDraft,
  reportSubmitError,
  saveDraft,
} from '@/utils/publicFormSubmit';

// Должны совпадать с бэкендом (_save_public_form_files): иначе файл «принимается»
// на фронте, но тихо отбрасывается на сервере. Стоп даём СРАЗУ при выборе.
// Видео (mp4/mov/avi) — до 100 МБ; остальное — до 10 МБ. Совпадает с бэкендом
// (forms.py: ALLOWED_EXTENSIONS / VIDEO_EXTENSIONS / PUBLIC_MAX_*).
const VIDEO_EXTS = ['.mp4', '.mov', '.avi'];
const ALLOWED_FILE_EXTS = ['.pdf', '.doc', '.docx', '.jpg', '.jpeg', '.png', '.webp', ...VIDEO_EXTS];
const MAX_FILE_BYTES = 10 * 1024 * 1024;
const MAX_VIDEO_BYTES = 100 * 1024 * 1024;

/** Проверка файла при выборе; null = ок, строка = причина отказа. */
function validatePickedFile(file: File): string | null {
  const dot = file.name.lastIndexOf('.');
  const ext = dot >= 0 ? file.name.slice(dot).toLowerCase() : '';
  if (!ALLOWED_FILE_EXTS.includes(ext)) {
    return 'Неподдерживаемый формат. Допустимы PDF, DOC/DOCX, JPG, PNG, WEBP, видео MP4/MOV/AVI.';
  }
  const isVideo = VIDEO_EXTS.includes(ext);
  if (file.size > (isVideo ? MAX_VIDEO_BYTES : MAX_FILE_BYTES)) {
    return isVideo ? 'Видео больше 100 МБ.' : 'Файл больше 10 МБ.';
  }
  if (file.size === 0) return 'Файл пустой.';
  return null;
}

/**
 * PublicFormPage - Light-themed page for candidates to fill out a form.
 * This page is accessible WITHOUT authentication.
 */
export default function PublicFormPage() {
  // /form/d/:token — персональная ссылка (токен). /form/:key — единый короткий путь:
  // это может быть и персональный токен, и slug общей анкеты; какой именно — решаем
  // при загрузке (сначала пробуем как токен, при неудаче как slug).
  const { token: dispatchToken, key } = useParams<{ token?: string; key?: string }>();
  const [searchParams] = useSearchParams();
  // Предпросмотр (из конструктора): форма как видит кандидат, но БЕЗ отправки.
  const isPreview = searchParams.get('preview') === '1';
  const [form, setForm] = useState<PublicFormData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [skippedFiles, setSkippedFiles] = useState<SkippedFile[]>([]);
  const [validationErrors, setValidationErrors] = useState<Record<string, string>>({});
  const [fileUploads, setFileUploads] = useState<Record<string, File>>({});
  // Разрешённый идентификатор ссылки: либо {token} (персональная), либо {slug} (общая).
  const [resolved, setResolved] = useState<{ token?: string; slug?: string } | null>(null);
  // Ответы восстановлены из черновика (перезагрузили страницу посреди анкеты).
  const [draftRestored, setDraftRestored] = useState(false);
  // Черновик пишем только после того, как анкета загружена и в неё влит прежний
  // черновик, — иначе пустые значения по умолчанию затёрли бы его.
  const [draftReady, setDraftReady] = useState(false);

  useEffect(() => {
    if (!dispatchToken && !key) return;
    (async () => {
      try {
        let data: PublicFormData;
        let res: { token?: string; slug?: string };
        if (dispatchToken) {
          // Явный персональный роут /form/d/:token
          data = await getPublicFormByToken(dispatchToken);
          res = { token: dispatchToken };
        } else {
          // Единый /form/:key — сначала как персональный токен, при 404 как slug общей.
          try {
            data = await getPublicFormByToken(key!);
            res = { token: key };
          } catch {
            data = await getPublicForm(key!);
            res = { slug: key };
          }
        }
        setResolved(res);
        setForm(data);
        // Initialize default values
        const defaults: Record<string, unknown> = {};
        for (const field of data.fields) {
          if (field.type === 'multiselect') {
            defaults[field.id] = [];
          } else if (field.type === 'scale') {
            defaults[field.id] = null;
          } else {
            defaults[field.id] = '';
          }
        }
        // Черновик: кандидат мог перезагрузить страницу посреди анкеты (17.10.2026
        // так стёрлись 23 ответа — пять раз подряд). Предпросмотр и уже
        // заполненную анкету не трогаем.
        const draftStorageKey = draftKey(res);
        const draft = !isPreview && !data.already_submitted ? loadDraft(draftStorageKey) : null;
        setValues(mergeDraft(defaults, draft, data.fields.filter((f) => f.type === 'file').map((f) => f.id)));
        if (hasAnswers(draft)) setDraftRestored(true);
        setDraftReady(!isPreview && !data.already_submitted);
      } catch {
        setError('Форма не найдена или больше не активна');
      } finally {
        setLoading(false);
      }
    })();
  }, [dispatchToken, key]);

  // Каждый ответ сразу сохраняется на устройстве кандидата.
  useEffect(() => {
    if (!draftReady || submitted || !resolved) return;
    saveDraft(draftKey(resolved), values);
  }, [values, draftReady, submitted, resolved]);

  const validate = (): boolean => {
    if (!form) return false;
    const errs: Record<string, string> = {};
    for (const field of form.fields) {
      if (field.required) {
        const val = values[field.id];
        // Строка из одних пробелов — тоже пусто (сервер её так и считает).
        const empty = val === undefined || val === null
          || (typeof val === 'string' && val.trim() === '')
          || (Array.isArray(val) && val.length === 0)
          || (field.type === 'file' && !fileUploads[field.id]);
        if (empty) errs[field.id] = 'Обязательное поле';
      }
      // Basic email validation
      if (field.type === 'email' && values[field.id]) {
        const email = String(values[field.id]).trim();
        if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
          errs[field.id] = 'Некорректный email';
        }
      }
    }
    setValidationErrors(errs);
    const firstBad = form.fields.find((f) => errs[f.id]);
    if (firstBad) {
      // Анкета длинная: без прокрутки кандидат жмёт «Отправить» внизу, и ничего
      // не происходит — красная подпись осталась где-то наверху.
      setError('');
      requestAnimationFrame(() => {
        document.getElementById(`field-${firstBad.id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      });
      return false;
    }
    return true;
  };

  const handleSubmit = async (e?: React.SyntheticEvent) => {
    e?.preventDefault();
    if (isPreview) return; // предпросмотр — ничего не отправляем
    const rToken = resolved?.token;
    const rSlug = resolved?.slug;
    if ((!rToken && !rSlug) || !validate()) return;

    setSubmitting(true);
    try {
      const files = Object.values(fileUploads);
      let result: SubmitWithFilesResult | undefined;
      if (rToken) {
        // Личная ссылка: с файлами — multipart, иначе JSON.
        if (files.length > 0) {
          result = await submitPublicFormByTokenWithFiles(rToken, values, files);
        } else {
          await submitPublicFormByToken(rToken, values);
        }
      } else if (files.length > 0) {
        result = await submitPublicFormWithFiles(rSlug!, values, files);
      } else {
        await submitPublicForm(rSlug!, values);
      }
      // Пропущенные файлы (формат/размер/лимит) — показываем кандидату, чтобы он
      // знал, что часть вложений не доставлена, а не считал анкету полной.
      if (result?.skipped_files?.length) setSkippedFiles(result.skipped_files);
      clearDraft(draftKey({ token: rToken, slug: rSlug }));
      setSubmitted(true);
    } catch (err: unknown) {
      // Раньше любой сбой без текста от сервера превращался в «Произошла ошибка
      // при отправке», а сам сбой не оставлял следов: 17.10.2026 запрос кандидата
      // до нас не дошёл ни разу. Теперь объясняем, что делать, и сообщаем нам.
      const info = describeSubmitError(err);
      setError(info.message);
      if (info.kind !== 'server_detail') reportSubmitError({ token: rToken, slug: rSlug }, info);
    } finally {
      setSubmitting(false);
    }
  };

  const updateValue = (fieldId: string, value: unknown) => {
    setValues(prev => ({ ...prev, [fieldId]: value }));
    if (validationErrors[fieldId]) {
      setValidationErrors(prev => {
        const next = { ...prev };
        delete next[fieldId];
        return next;
      });
    }
  };

  // Light theme — white background for external candidates
  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (error && !form) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <p className="text-gray-500 text-lg">{error}</p>
        </div>
      </div>
    );
  }

  if (!form) return null;

  // Анкета уже заполнена (рекрутёр открыл по ссылке) — показываем ответы кандидата
  // read-only, а не пустую форму.
  if (form.already_submitted && form.answers) {
    return (
      <div className="min-h-screen bg-gray-50">
        <div className="max-w-2xl mx-auto px-4 py-8 sm:py-12">
          <div className="text-center mb-8">
            <div className="text-sm font-semibold text-blue-600 tracking-wide uppercase mb-2">Enceladus</div>
            <h1 className="text-2xl sm:text-3xl font-bold text-gray-900">{form.title}</h1>
            <p className="text-green-600 mt-2 text-sm">✓ Анкета заполнена</p>
          </div>
          <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-6 sm:p-8 space-y-4">
            {form.fields.map(field => {
              const raw = form.answers?.[field.id];
              const text = Array.isArray(raw) ? raw.join(', ') : (raw == null || raw === '' ? '—' : String(raw));
              const fileUrl = form.file_links?.[field.id];
              const isUrl = /^https?:\/\//i.test(text);
              return (
                <div key={field.id}>
                  <div className="text-sm text-gray-500">{field.label}</div>
                  {fileUrl ? (
                    <a href={fileUrl} target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline break-all">{text !== '—' ? text : 'Открыть файл'}</a>
                  ) : isUrl ? (
                    <a href={text} target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline break-all">{text}</a>
                  ) : (
                    <div className="text-gray-900 break-words whitespace-pre-wrap">{text}</div>
                  )}
                </div>
              );
            })}
          </div>
          <p className="text-center text-xs text-gray-400 mt-6">Powered by Enceladus</p>
        </div>
      </div>
    );
  }

  if (submitted) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center max-w-md mx-auto px-4">
          <div className="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-4">
            <svg className="w-8 h-8 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
          </div>
          <h2 className="text-2xl font-bold text-gray-800 mb-2">Спасибо!</h2>
          <p className="text-gray-500">Ваша анкета успешно отправлена. Мы свяжемся с вами в ближайшее время.</p>
          {skippedFiles.length > 0 && (
            <div className="mt-5 text-left bg-amber-50 border border-amber-200 rounded-lg p-4">
              <p className="text-sm font-semibold text-amber-800 mb-1">
                Внимание: часть файлов не была загружена
              </p>
              <ul className="text-sm text-amber-700 list-disc list-inside space-y-0.5">
                {skippedFiles.map((f, i) => (
                  <li key={i}><span className="font-medium">{f.name}</span> — {f.reason}</li>
                ))}
              </ul>
              <p className="text-xs text-amber-600 mt-2">
                Допустимы PDF, DOC/DOCX, JPG, PNG, WEBP до 10 МБ. При необходимости свяжитесь с рекрутёром.
              </p>
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-2xl mx-auto px-4 py-8 sm:py-12">
        {/* Header */}
        <div className="text-center mb-8">
          <div className="text-sm font-semibold text-blue-600 tracking-wide uppercase mb-2">
            Enceladus
          </div>
          <h1 className="text-2xl sm:text-3xl font-bold text-gray-900">{form.title}</h1>
          {form.vacancy_title && (
            <p className="text-gray-500 mt-1">Вакансия: {form.vacancy_title}</p>
          )}
          {form.description && (
            <p
              className="text-gray-600 mt-3 [&_a]:text-blue-600 [&_a]:underline [&_a]:hover:text-blue-700"
              dangerouslySetInnerHTML={{ __html: sanitizeHtml(autoLinkify(form.description)) }}
            />
          )}
        </div>

        {isPreview && (
          <div className="mb-6 p-4 bg-amber-50 border border-amber-200 rounded-xl text-amber-700 text-sm text-center">
            Режим предпросмотра — так анкету видит кандидат. Ответы не сохраняются.
          </div>
        )}

        {draftRestored && !error && (
          <div className="mb-6 p-4 bg-blue-50 border border-blue-200 rounded-xl text-blue-800 text-sm">
            Мы восстановили ваши ответы — можно продолжить с того же места.
            {form.fields.some((f) => f.type === 'file') && ' Файлы, если они были, прикрепите заново.'}
          </div>
        )}

        {/* Form */}
        <form
          onSubmit={handleSubmit}
          onKeyDown={(e) => {
            // Анкета отправляется ТОЛЬКО по клику на кнопку — Enter не сабмитит
            // (жалоба HR: кандидаты по 3 раза случайно отправляли клавишей Enter).
            // В многострочных полях (textarea) Enter = перенос строки; на самой
            // кнопке Enter = её нажатие. В любом другом поле Enter гасим.
            if (e.key !== 'Enter') return;
            const tag = (e.target as HTMLElement).tagName;
            if (tag === 'TEXTAREA' || tag === 'BUTTON') return;
            e.preventDefault();
          }}
          className="bg-white rounded-2xl shadow-sm border border-gray-200 p-6 sm:p-8 space-y-6">
          {form.fields.map(field => (
            <div key={field.id} id={`field-${field.id}`}>
            <FieldRenderer
              field={field}
              value={values[field.id]}
              onChange={val => updateValue(field.id, val)}
              onFileChange={field.type === 'file' ? (file: File | null) => {
                // Стоп-валидация СРАЗУ при выборе: плохой файл не принимаем,
                // показываем причину под полем — кандидат исправляет до отправки.
                const reason = file ? validatePickedFile(file) : null;
                if (reason) {
                  setValidationErrors(prev => ({ ...prev, [field.id]: reason }));
                  setFileUploads(prev => {
                    const next = { ...prev };
                    delete next[field.id];
                    return next;
                  });
                  return;
                }
                setValidationErrors(prev => {
                  const next = { ...prev };
                  delete next[field.id];
                  return next;
                });
                setFileUploads(prev => {
                  const next = { ...prev };
                  if (file) {
                    next[field.id] = file;
                  } else {
                    delete next[field.id];
                  }
                  return next;
                });
              } : undefined}
              selectedFile={fileUploads[field.id] || null}
              error={validationErrors[field.id]}
            />
            </div>
          ))}

          {/* Ошибка — у кнопки, а не в шапке: анкета длинная, человек жмёт
              «Отправить» внизу и сообщения наверху просто не видит. */}
          {error && (
            <div role="alert" className="p-4 bg-red-50 border border-red-200 rounded-xl text-red-700 text-sm">
              {error}
            </div>
          )}
          {!error && Object.keys(validationErrors).length > 0 && (
            <div role="alert" className="p-4 bg-red-50 border border-red-200 rounded-xl text-red-700 text-sm">
              Заполните отмеченные красным поля: {Object.keys(validationErrors).length}
            </div>
          )}

          <button
            type="button"
            onClick={handleSubmit}
            disabled={submitting || isPreview}
            className="w-full py-3 px-6 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-xl transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isPreview ? 'Предпросмотр — отправка отключена' : submitting ? 'Отправка...' : 'Отправить'}
          </button>
          {draftReady && (
            <p className="text-center text-xs text-gray-400 -mt-3">
              Ответы сохраняются автоматически — если обновить страницу, они не пропадут.
            </p>
          )}
        </form>

        <p className="text-center text-xs text-gray-400 mt-6">
          Powered by Enceladus
        </p>
      </div>
    </div>
  );
}
