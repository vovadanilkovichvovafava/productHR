import { pluralRu } from '@/utils/plural';
import { copyOrShowLink } from '@/utils/copyOrShowLink';
import { useState, useEffect, useCallback, useRef } from 'react';
import HrConfirm from '@/components/hr/HrConfirm';
import * as Dialog from '@radix-ui/react-dialog';
import toast from 'react-hot-toast';
import { Plus, LayoutGrid, Sparkles, X, Send, Loader2, ChevronLeft, FileText, PenLine, Trash2 } from 'lucide-react';
import { FormBuilder, submissionWord, type FormBuilderHandle } from './FormBuilder';
import { formProblem } from './formValidation';
import {
  createForm, createDispatch, getFormTemplates, deleteForm,
  aiFormChat,
  type FormTemplate, type AIChatMessage, type FormField,
} from '@/services/api/forms';

type Step = 'entry' | 'template-select' | 'builder' | 'ai-chat';
type ChatMsg = { role: 'user' | 'assistant'; content: string };

function apiDetail(error: unknown): string | null {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  return typeof detail === 'string' ? detail : null;
}

export function AnketaDrawer({
  open, onOpenChange, entityId, entityName, vacancyId, vacancyTitle,
}: {
  open: boolean; onOpenChange: (v: boolean) => void; entityId: number; entityName: string;
  // Контекст воронки (если открыто из воронки) — для показа её шаблонов первыми.
  vacancyId?: number; vacancyTitle?: string;
}) {
  const [step, setStep] = useState<Step>('entry');
  const [formId, setFormId] = useState<number | null>(null);
  const [isTemplate, setIsTemplate] = useState(false);
  // «Использовать» шаблон напрямую (без клона) — id шаблона, пока идёт запрос.
  const [dispatchingTemplateId, setDispatchingTemplateId] = useState<number | null>(null);

  useEffect(() => {
    if (!open) { setStep('entry'); setFormId(null); setIsTemplate(false); }
  }, [open]);

  const startBlank = async () => {
    try {
      const form = await createForm({ title: 'Анкета', fields: [
        { id: `f${Date.now()}`, type: 'text', label: 'ФИО', required: true },
      ] });
      setFormId(form.id); setIsTemplate(false); setStep('builder');
    } catch { toast.error('Не удалось создать анкету'); }
  };

  // «Использовать» шаблон = отправить его напрямую (FormDispatch ссылается на
  // сам шаблон по form_id) — БЕЗ клонирования в новую анкету. Раньше каждое
  // использование шаблона создавало ещё одну сохранённую анкету; новая строка
  // должна появляться только когда её явно создают («Создать шаблон» / «С нуля»).
  const useTemplateDirectly = async (tpl: FormTemplate) => {
    // Шаблон, на котором кандидат застрял бы (нет вариантов у выбора, кривая
    // шкала), не отправляем — сначала исправить (formValidation.ts).
    const problem = formProblem(tpl.title, tpl.fields || []);
    if (problem) {
      toast.error(`Шаблон «${tpl.title}» пока нельзя отправить. ${problem} — откройте его на карандаше и исправьте.`, { duration: 7000 });
      return;
    }
    setDispatchingTemplateId(tpl.id);
    try {
      const { url } = await createDispatch(tpl.id, entityId);
      await copyOrShowLink(`${window.location.origin}${url}`, 'Персональная ссылка скопирована');
      onOpenChange(false);
    } catch (error) {
      toast.error(apiDetail(error) || 'Не удалось создать ссылку');
    } finally {
      setDispatchingTemplateId(null);
    }
  };

  const createNewTemplate = async () => {
    try {
      const form = await createForm({
        title: 'Новый шаблон',
        fields: [{ id: `f${Date.now()}`, type: 'text', label: 'ФИО', required: true }],
        is_template: true,
      });
      setFormId(form.id); setIsTemplate(true); setStep('builder');
    } catch { toast.error('Не удалось создать шаблон'); }
  };

  const editTemplate = (id: number) => {
    setFormId(id); setIsTemplate(true); setStep('builder');
  };

  const createFromAIFields = async (rawFields: Omit<FormField, 'id'>[]) => {
    const form = await createForm({
      title: 'AI-анкета',
      fields: rawFields.map((f, i) => ({ ...f, id: `f${Date.now()}_${i}` })),
    });
    setFormId(form.id); setIsTemplate(false); setStep('builder');
  };

  const builderRef = useRef<FormBuilderHandle | null>(null);
  const [sending, setSending] = useState(false);
  const sendToCandidate = async () => {
    if (!formId || sending) return;
    setSending(true);
    try {
      // Проверяем то, что на экране, и досохраняем последнюю правку: раньше
      // ссылка уходила, пока автосейв ещё ждал свои 0,7 с.
      const problem = await builderRef.current?.flush();
      if (problem) {
        toast.error(problem, { duration: 6000 });
        return;
      }
      const { url } = await createDispatch(formId, entityId);
      await copyOrShowLink(`${window.location.origin}${url}`, 'Персональная ссылка скопирована');
    } catch (error) {
      toast.error(apiDetail(error) || 'Не удалось создать ссылку');
    } finally {
      setSending(false);
    }
  };

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/40 z-[1000]" />
        <Dialog.Content className="fixed right-0 top-0 bottom-0 z-[1001] w-full max-w-3xl bg-white shadow-xl flex flex-col">
          <div className="flex items-center justify-between border-b px-5 py-3 shrink-0">
            <div className="min-w-0">
              <Dialog.Title className="text-base font-semibold text-gray-900">
                {isTemplate ? 'Шаблон анкеты' : 'Анкета'}
              </Dialog.Title>
              {/* Кандидат — контекст дровера, НЕ часть названия анкеты: имя не
                  должно попадать в title (и тем более в шаблон при переносе). */}
              {!isTemplate && (
                <p className="text-xs text-gray-500 truncate">{entityName}</p>
              )}
            </div>
            <Dialog.Close className="text-gray-400 hover:text-gray-700" aria-label="Закрыть">
              <X className="w-5 h-5" />
            </Dialog.Close>
          </div>

          <div className={`flex-1 min-h-0 ${step === 'ai-chat' ? 'overflow-hidden flex flex-col' : 'overflow-auto'}`}>
            {step === 'entry' && (
              <EntryStep
                onBlank={startBlank}
                onTemplates={() => setStep('template-select')}
                onAI={() => setStep('ai-chat')}
              />
            )}

            {step === 'template-select' && (
              <TemplateSelectStep
                onBack={() => setStep('entry')}
                onUse={useTemplateDirectly}
                usingTemplateId={dispatchingTemplateId}
                onEdit={editTemplate}
                onNew={createNewTemplate}
                vacancyId={vacancyId}
                vacancyTitle={vacancyTitle}
              />
            )}

            {step === 'ai-chat' && (
              <AIStep
                entityId={entityId}
                entityName={entityName}
                onBack={() => setStep('entry')}
                onCreateForm={createFromAIFields}
              />
            )}

            {step === 'builder' && formId && (
              <>
                {/* Разовая анкета (С нуля / из шаблона / AI): автосейв, без
                    кнопки «Сохранить», НЕ попадает в шаблоны. Шаблон: как раньше —
                    ручное «Сохранить» в библиотеку. */}
                <FormBuilder
                  handleRef={builderRef}
                  inDialog
                  formId={formId}
                  saveAsTemplate={isTemplate}
                  autosave={!isTemplate}
                  onClose={() => setStep(isTemplate ? 'template-select' : 'entry')}
                />
                {!isTemplate && (
                  <div className="sticky bottom-0 bg-white border-t px-5 py-3 flex justify-end gap-2">
                    <button
                      onClick={sendToCandidate}
                      disabled={sending}
                      className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-60 text-white rounded-lg text-sm font-medium"
                    >
                      <Send className="w-4 h-4" /> Отправить кандидату
                    </button>
                  </div>
                )}
              </>
            )}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

// ─────────────────────────────────────────────
// Entry step
// ─────────────────────────────────────────────

function EntryStep({ onBlank, onTemplates, onAI }: {
  onBlank: () => void;
  onTemplates: () => void;
  onAI: () => void;
}) {
  return (
    <div className="p-5">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <button onClick={onBlank} className="border rounded-xl p-4 text-left hover:border-blue-400 transition-colors">
          <Plus className="w-5 h-5 text-gray-500" />
          <p className="mt-2 font-medium text-sm text-gray-900">С нуля</p>
          <p className="text-xs text-gray-500">Пустой конструктор</p>
        </button>

        <button onClick={onTemplates} className="border rounded-xl p-4 text-left hover:border-gray-400 transition-colors">
          <LayoutGrid className="w-5 h-5 text-gray-500" />
          <p className="mt-2 font-medium text-sm text-gray-900">Из шаблона</p>
          <p className="text-xs text-gray-500">Шаблоны вашей команды</p>
        </button>

        <button onClick={onAI} className="border rounded-xl p-4 text-left hover:border-purple-300 transition-colors">
          <Sparkles className="w-5 h-5 text-purple-500" />
          <p className="mt-2 font-medium text-sm text-gray-900">AI-генерация</p>
          <p className="text-xs text-gray-500">По резюме кандидата</p>
        </button>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────
// Template select step
// ─────────────────────────────────────────────

function TemplateSelectStep({ onBack, onUse, usingTemplateId, onEdit, onNew, vacancyId, vacancyTitle }: {
  onBack: () => void;
  onUse: (tpl: FormTemplate) => void;
  // id шаблона, который сейчас отправляется (спиннер на его кнопке) — null,
  // если ничего не отправляется.
  usingTemplateId: number | null;
  onEdit: (id: number) => void;
  onNew: () => void;
  vacancyId?: number;
  vacancyTitle?: string;
}) {
  const [templates, setTemplates] = useState<FormTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [pendingDeleteId, setPendingDeleteId] = useState<number | null>(null);

  useEffect(() => {
    getFormTemplates()
      .then(setTemplates)
      .catch(() => toast.error('Не удалось загрузить шаблоны'))
      .finally(() => setLoading(false));
  }, []);

  const handleDelete = async (id: number, submissionsCount: number) => {
    // «Использовать» шлёт FormDispatch напрямую на шаблон (без клона) — удаление
    // шаблона каскадно стирает ответы ВСЕХ кандидатов, кто по нему отвечал.
    // Если ответы уже есть, блокируем удаление и предлагаем деактивировать.
    if (submissionsCount > 0) {
      toast.error(
        `У шаблона уже есть ${submissionsCount} ${submissionWord(submissionsCount)} — удаление сотрёт их. Деактивируйте шаблон вместо удаления.`,
        { duration: 6000 },
      );
      return;
    }
    setPendingDeleteId(id);
  };
  const confirmDelete = async () => {
    const id = pendingDeleteId;
    if (id == null) return;
    setDeletingId(id);
    try {
      await deleteForm(id);
      setTemplates(prev => prev.filter(t => t.id !== id));
      toast.success('Шаблон удалён');
      setPendingDeleteId(null);
    } catch (error) {
      const detail = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(typeof detail === 'string' ? detail : 'Не удалось удалить шаблон');
    } finally {
      setDeletingId(null);
    }
  };

  const pendingDelete = templates.find(t => t.id === pendingDeleteId);
  return (
    <div className="flex flex-col h-full min-h-0">
      {pendingDelete && (
        <HrConfirm
          title="Удалить шаблон?"
          subtitle={`«${pendingDelete.title}»`}
          danger="Действие нельзя отменить."
          confirmLabel="Удалить"
          busy={deletingId === pendingDelete.id}
          inDialog
          onCancel={() => setPendingDeleteId(null)}
          onConfirm={confirmDelete}
        />
      )}
      <div className="flex items-center gap-2 px-5 py-2.5 border-b bg-gray-50/60 shrink-0">
        <button onClick={onBack} className="text-gray-400 hover:text-gray-700 p-0.5 -ml-1">
          <ChevronLeft className="w-4 h-4" />
        </button>
        <span className="text-sm font-medium text-gray-800">Шаблоны анкет</span>
        <button
          onClick={onNew}
          className="ml-auto inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-gray-900 hover:bg-gray-700 text-white text-xs font-medium transition-colors"
        >
          <Plus className="w-3.5 h-3.5" /> Создать шаблон
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-5">
        {loading && (
          <div className="flex items-center gap-2 text-sm text-gray-500">
            <Loader2 className="w-4 h-4 animate-spin" /> Загрузка…
          </div>
        )}

        {!loading && templates.length === 0 && (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <FileText className="w-10 h-10 text-gray-300 mb-3" />
            <p className="text-sm font-medium text-gray-600">Шаблонов пока нет</p>
            <p className="text-xs text-gray-400 mt-1 mb-4">Создайте шаблон, чтобы переиспользовать его для разных кандидатов</p>
            <button
              onClick={onNew}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-gray-900 hover:bg-gray-700 text-white text-sm font-medium transition-colors"
            >
              <Plus className="w-4 h-4" /> Создать первый шаблон
            </button>
          </div>
        )}

        {!loading && templates.length > 0 && (() => {
          const card = (tpl: FormTemplate) => (
            <div key={tpl.id} className="border border-gray-200 rounded-xl p-4 flex items-start gap-3 hover:border-gray-300 transition-colors">
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-900 truncate">
                  {tpl.title}
                  {tpl.is_active === false && (
                    <span className="ml-2 align-middle px-1.5 py-0.5 rounded bg-gray-100 text-gray-500 text-[11px] font-normal">Выключен</span>
                  )}
                </p>
                {tpl.description && (
                  <p className="text-xs text-gray-500 mt-0.5 truncate">{tpl.description}</p>
                )}
                <p className="text-xs text-gray-400 mt-1">
                  {/* Количество ответов на шаблон (агрегат по ВСЕМ кандидатам,
                      кому его отправляли) тут не показываем — не читается как
                      метрика самого шаблона. tpl.submissions_count не убираем
                      из данных: им же защищено удаление ниже (handleDelete). */}
                  {tpl.fields.length} {pluralRu(tpl.fields.length, 'вопрос', 'вопроса', 'вопросов')}
                </p>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <button
                  onClick={() => onEdit(tpl.id)}
                  className="p-1.5 text-gray-400 hover:text-gray-700 rounded-lg hover:bg-gray-100 transition-colors"
                  title="Редактировать шаблон"
                >
                  <PenLine className="w-4 h-4" />
                </button>
                <button
                  onClick={() => handleDelete(tpl.id, tpl.submissions_count)}
                  disabled={deletingId === tpl.id}
                  className="p-1.5 text-gray-400 hover:text-red-500 rounded-lg hover:bg-red-50 transition-colors disabled:opacity-50"
                  title="Удалить шаблон"
                >
                  {deletingId === tpl.id ? <Loader2 className="w-4 h-4 animate-spin" /> : <Trash2 className="w-4 h-4" />}
                </button>
                <button
                  onClick={() => onUse(tpl)}
                  disabled={usingTemplateId === tpl.id || tpl.is_active === false}
                  title={tpl.is_active === false ? 'Шаблон выключен — включите его на карандаше, чтобы отправлять' : undefined}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium transition-colors disabled:opacity-60"
                >
                  {usingTemplateId === tpl.id && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                  Использовать
                </button>
              </div>
            </div>
          );
          // Скоуп по воронке: сперва шаблоны текущей воронки, затем остальные.
          const scoped = vacancyId ? templates.filter(t => (t.vacancy_ids || []).includes(vacancyId)) : [];
          const others = vacancyId ? templates.filter(t => !(t.vacancy_ids || []).includes(vacancyId)) : templates;
          return (
            <div className="space-y-4">
              {vacancyId && scoped.length > 0 && (
                <div>
                  <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
                    Шаблоны воронки{vacancyTitle ? ` «${vacancyTitle}»` : ''}
                  </div>
                  <div className="space-y-2">{scoped.map(card)}</div>
                </div>
              )}
              {others.length > 0 && (
                <div>
                  {vacancyId && scoped.length > 0 && (
                    <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Другие шаблоны</div>
                  )}
                  <div className="space-y-2">{others.map(card)}</div>
                </div>
              )}
            </div>
          );
        })()}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────
// AI chat step
// ─────────────────────────────────────────────

function AIStep({ entityId, entityName, onBack, onCreateForm }: {
  entityId: number;
  entityName: string;
  onBack: () => void;
  onCreateForm: (fields: Omit<FormField, 'id'>[]) => Promise<void>;
}) {
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [fields, setFields] = useState<Omit<FormField, 'id'>[] | null>(null);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [hasResume, setHasResume] = useState<boolean | null>(null);
  const [creating, setCreating] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  const send = useCallback(async (msgs: ChatMsg[]) => {
    setLoading(true);
    try {
      const res = await aiFormChat(entityId, msgs as AIChatMessage[]);
      setHasResume(res.has_resume);
      setMessages([...msgs, { role: 'assistant', content: res.message }]);
      if (res.fields) setFields(res.fields);
    } catch {
      toast.error('Ошибка AI — попробуй ещё раз');
    } finally {
      setLoading(false);
    }
  }, [entityId]);

  useEffect(() => { send([]); }, [send]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const handleSend = () => {
    if (!input.trim() || loading) return;
    const userMsg: ChatMsg = { role: 'user', content: input.trim() };
    const newMsgs = [...messages, userMsg];
    setMessages(newMsgs);
    setInput('');
    send(newMsgs);
  };

  const handleCreate = async () => {
    if (!fields) return;
    setCreating(true);
    try { await onCreateForm(fields); }
    catch { toast.error('Не удалось создать анкету'); }
    finally { setCreating(false); }
  };

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="flex items-center gap-2 px-5 py-2.5 border-b bg-purple-50/50 shrink-0">
        <button onClick={onBack} className="text-gray-400 hover:text-gray-700 p-0.5 -ml-1">
          <ChevronLeft className="w-4 h-4" />
        </button>
        <Sparkles className="w-4 h-4 text-purple-500" />
        <span className="text-sm font-medium text-gray-800">AI-анкета · {entityName}</span>
        {hasResume !== null && (
          <span className={`ml-auto text-xs px-2 py-0.5 rounded-full font-medium ${
            hasResume ? 'bg-green-100 text-green-700' : 'bg-amber-100 text-amber-700'
          }`}>
            {hasResume ? '✓ Резюме найдено' : '! Резюме не найдено'}
          </span>
        )}
      </div>

      <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3 min-h-0">
        {messages.length === 0 && loading && (
          <div className="flex items-center gap-2.5 text-sm text-gray-500 pt-2">
            <Loader2 className="w-4 h-4 animate-spin text-purple-500 shrink-0" />
            <span>Анализирую резюме {entityName}…</span>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap ${
              m.role === 'user'
                ? 'bg-purple-600 text-white rounded-br-sm'
                : 'bg-gray-100 text-gray-800 rounded-bl-sm'
            }`}>
              {m.content}
            </div>
          </div>
        ))}
        {loading && messages.length > 0 && (
          <div className="flex justify-start">
            <div className="bg-gray-100 rounded-2xl rounded-bl-sm px-4 py-3">
              <Loader2 className="w-4 h-4 animate-spin text-purple-500" />
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {fields && (
        <div className="px-5 pb-3 shrink-0">
          <div className="border border-purple-200 rounded-xl bg-purple-50/40 p-3">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold text-purple-700 uppercase tracking-wide">Предложенная анкета</span>
              <span className="text-xs text-gray-500">{fields.length} {pluralRu(fields.length, 'вопрос', 'вопроса', 'вопросов')}</span>
            </div>
            <div className="space-y-0.5 max-h-28 overflow-y-auto">
              {fields.map((f, i) => (
                <div key={i} className="flex items-center gap-2 text-xs py-0.5">
                  <span className="text-gray-400 w-4 text-right shrink-0">{i + 1}.</span>
                  <span className="text-gray-800 flex-1 truncate">{f.label}</span>
                  {f.required && <span className="text-red-400 shrink-0">*</span>}
                  <span className="text-gray-400 shrink-0 font-mono">{f.type}</span>
                </div>
              ))}
            </div>
            <button
              onClick={handleCreate}
              disabled={creating}
              className="mt-3 w-full flex items-center justify-center gap-2 py-2 rounded-lg bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white text-sm font-medium transition-colors"
            >
              {creating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
              {creating ? 'Создаю…' : 'Создать эту анкету'}
            </button>
          </div>
        </div>
      )}

      <div className="px-5 pt-2 pb-4 border-t bg-white shrink-0">
        <div className="flex gap-2">
          <input
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
            placeholder={fields ? 'Что изменить в анкете?' : 'Добавь требования или уточни…'}
            disabled={loading}
            className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm outline-none focus:border-purple-400 focus:ring-2 focus:ring-purple-400/20 disabled:opacity-50 disabled:bg-gray-50"
          />
          <button
            onClick={handleSend}
            disabled={loading || !input.trim()}
            className="px-3 py-2 rounded-lg bg-purple-600 hover:bg-purple-700 disabled:opacity-40 text-white transition-colors shrink-0"
          >
            <Send className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
