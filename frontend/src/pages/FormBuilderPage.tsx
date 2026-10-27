import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  Plus,
  Trash2,
  FileText,
} from 'lucide-react';
import toast from 'react-hot-toast';
import {
  getMyForms,
  createForm,
  updateForm,
  deleteForm,
} from '@/services/api/forms';
import type { FormTemplate } from '@/services/api/forms';
import { FormBuilder, nextFieldId, fieldWord, submissionWord } from '@/features/forms/FormBuilder';
import { useAuthStore } from '@/stores/authStore';
import HrConfirm from '@/components/hr/HrConfirm';

// ============================================================
// List mode component
// ============================================================

function FormListView() {
  const navigate = useNavigate();
  // Наблюдатель: анкеты видит, но не создаёт и не удаляет.
  const observer = !!useAuthStore((state) => state.user?.is_readonly);
  const [forms, setForms] = useState<FormTemplate[]>([]);
  const [loading, setLoading] = useState(true);

  const loadForms = useCallback(async () => {
    try {
      // ВСЕ анкеты орга (GET /forms отдаёт полный шейп с is_template).
      // На странице делим на две секции: «Шаблоны» (is_template=true — те же,
      // что в «Шаблонах анкет» карточки кандидата) и «Остальные анкеты»
      // (разовые/старые, в т.ч. созданные до появления этой страницы).
      const data = await getMyForms();
      setForms(data);
    } catch {
      toast.error('Не удалось загрузить анкеты');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadForms(); }, [loadForms]);

  const handleCreate = async () => {
    try {
      const form = await createForm({
        title: 'Новая анкета',
        is_template: true,
        fields: [
          { id: nextFieldId(), type: 'text', label: 'ФИО', required: true, placeholder: 'Иван Иванов' },
          { id: nextFieldId(), type: 'email', label: 'Email', required: true },
        ],
      });
      navigate(`/form-builder/${form.id}`);
    } catch {
      toast.error('Не удалось создать шаблон');
    }
  };

  // Удаление спрашиваем окном сайта, а анкету с ответами не удаляем вовсе:
  // удаление стирает ответы всех кандидатов (сервер тоже не даст, 409).
  const [pendingDelete, setPendingDelete] = useState<FormTemplate | null>(null);
  const [deleting, setDeleting] = useState(false);
  const handleDelete = (id: number, e: React.MouseEvent) => {
    e.stopPropagation();
    const form = forms.find(f => f.id === id);
    if (!form) return;
    if (form.submissions_count > 0) {
      toast.error(
        `У анкеты уже есть ${form.submissions_count} ${submissionWord(form.submissions_count)} — удаление сотрёт их. Сделайте её неактивной вместо удаления.`,
        { duration: 6000 },
      );
      return;
    }
    setPendingDelete(form);
  };
  const confirmDelete = async () => {
    if (!pendingDelete) return;
    setDeleting(true);
    try {
      await deleteForm(pendingDelete.id);
      setForms(prev => prev.filter(f => f.id !== pendingDelete.id));
      toast.success('Анкета удалена');
      setPendingDelete(null);
    } catch (error) {
      const detail = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(typeof detail === 'string' ? detail : 'Не удалось удалить');
    } finally {
      setDeleting(false);
    }
  };

  // Продвижение разовой/старой анкеты в шаблоны: спасает анкеты, созданные до
  // появления этой страницы (без is_template), — одним кликом переносит их в
  // секцию «Шаблоны», после чего они видны в карточке кандидата.
  const handlePromote = async (id: number, e: React.MouseEvent) => {
    e.stopPropagation();
    const form = forms.find((f) => f.id === id);
    // Разовые анкеты называются «Анкета — Имя Кандидата» (AnketaDrawer
    // подставляет entityName при создании) — шаблон не должен нести имя
    // конкретного кандидата, иначе оно так и останется в библиотеке навсегда
    // и будет предлагаться для ВСЕХ следующих кандидатов. Отрезаем суффикс
    // « — Имя» (последнее тире в названии) при переносе в шаблоны.
    const cleanTitle = form?.title.replace(/\s+—\s+[^—]+$/, '').trim() || form?.title;
    try {
      await updateForm(id, { is_template: true, ...(cleanTitle ? { title: cleanTitle } : {}) });
      setForms(prev => prev.map(f => (f.id === id ? { ...f, is_template: true, title: cleanTitle || f.title } : f)));
      toast.success('Анкета перенесена в шаблоны');
    } catch (error) {
      // Жёсткая защита от дублей названия шаблонов (backend update_form, 409) —
      // показываем конкретную причину вместо общей ошибки.
      const detail = (error as { response?: { status?: number; data?: { detail?: string } } })?.response;
      toast.error(detail?.status === 409 && detail.data?.detail ? detail.data.detail : 'Не удалось перенести в шаблоны');
    }
  };

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-accent-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="p-6 max-w-5xl mx-auto">
      {pendingDelete && (
        <HrConfirm
          title="Удалить анкету?"
          subtitle={`«${pendingDelete.title}»`}
          danger="Действие нельзя отменить."
          confirmLabel="Удалить"
          busy={deleting}
          onCancel={() => setPendingDelete(null)}
          onConfirm={confirmDelete}
        />
      )}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-white">Анкеты</h1>
          <p className="text-dark-400 text-sm mt-1">
            Шаблоны анкет для кандидатов — создайте заранее и отправляйте из карточки кандидата
          </p>
        </div>
        {!observer && (
        <button
          onClick={handleCreate}
          className="flex items-center gap-2 px-4 py-2.5 bg-accent-500 hover:bg-accent-600 text-white rounded-xl font-medium transition-colors"
        >
          <Plus className="w-4 h-4" />
          Создать шаблон
        </button>
        )}
      </div>

      {(() => {
        const templates = forms.filter(f => f.is_template);
        const others = forms.filter(f => !f.is_template);

        const renderCard = (form: FormTemplate) => (
          <motion.div
            key={form.id}
            layout
            onClick={() => navigate(`/form-builder/${form.id}`)}
            className="bg-dark-800 border border-dark-700 rounded-xl p-4 hover:border-dark-600 cursor-pointer transition-colors group"
          >
            <div className="flex items-center justify-between">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <h3 className="font-semibold text-white truncate">{form.title}</h3>
                  {form.is_active === false && (
                    <span className="px-2 py-0.5 text-xs rounded-full bg-dark-600 text-dark-400">
                      Неактивна
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-4 mt-1 text-sm text-dark-400">
                  <span>{form.fields.length} {fieldWord(form.fields.length)}</span>
                  {/* «Ответов» имеет смысл только для разовой анкеты конкретного
                      кандидата (заполнил/нет). У шаблона это агрегат по ВСЕМ, кому
                      его когда-либо отправляли — рядом с названием формы это число
                      не читается и только сбивало с толку. Само поле submissions_count
                      не трогаем — оно используется в защите от удаления шаблона
                      с уже существующими ответами (handleDelete в AnketaDrawer). */}
                  {!form.is_template && typeof form.submissions_count === 'number' && (
                    <span>{form.submissions_count} {submissionWord(form.submissions_count)}</span>
                  )}
                  {form.created_at && (
                    <span>{new Date(form.created_at).toLocaleDateString('ru')}</span>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                {/* «Скопировать ссылку» убрана: публичный slug-сабмит намеренно
                    отключён (403) — анкеты уходят персональной token-ссылкой. */}
                {!form.is_template && !observer && (
                  <button
                    onClick={(e) => handlePromote(form.id, e)}
                    className="px-2.5 py-1.5 rounded-lg text-xs font-medium bg-accent-500/15 text-accent-500 hover:bg-accent-500/25 transition-colors"
                    title="Перенести в шаблоны — станет доступна в карточке кандидата"
                  >
                    В шаблоны
                  </button>
                )}
                {!observer && (
                <button
                  onClick={(e) => handleDelete(form.id, e)}
                  className="p-2 rounded-lg hover:bg-red-500/20 text-dark-400 hover:text-red-400 transition-colors"
                  title="Удалить"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
                )}
              </div>
            </div>
          </motion.div>
        );

        if (forms.length === 0) {
          return (
            <div className="text-center py-20 text-dark-400">
              <FileText className="w-12 h-12 mx-auto mb-3 opacity-50" />
              <p className="text-lg">Пока нет шаблонов</p>
              <p className="text-sm mt-1">Создайте первый шаблон — он появится в карточке кандидата в «Шаблонах анкет»</p>
            </div>
          );
        }

        return (
          <>
            <div className="text-sm font-medium text-dark-400 uppercase tracking-wide mb-3">
              Шаблоны
            </div>
            {templates.length === 0 ? (
              <div className="text-sm text-dark-400 mb-6">
                {others.length > 0 ? (
                  <>Пока нет шаблонов — создайте новый или нажмите «В шаблоны» на анкете ниже, чтобы сделать её переиспользуемой.</>
                ) : (
                  <>Пока нет шаблонов — создайте первый, он появится в карточке кандидата.</>
                )}
              </div>
            ) : (
              <div className="grid gap-3 mb-8">{templates.map(renderCard)}</div>
            )}
            {/* Остальные сохранённые анкеты: разовые/старые (созданные до этой
                страницы, без is_template) — чтобы они не «терялись» из виду. */}
            {others.length > 0 && (
              <>
                <div className="text-sm font-medium text-dark-400 uppercase tracking-wide mb-3">
                  Остальные анкеты
                </div>
                <div className="grid gap-3">{others.map(renderCard)}</div>
              </>
            )}
          </>
        );
      })()}
    </div>
  );
}

// ============================================================
// Main page
// ============================================================

export default function FormBuilderPage() {
  const { formId } = useParams<{ formId: string }>();
  const navigate = useNavigate();

  if (formId) {
    return <FormBuilder formId={parseInt(formId, 10)} onClose={() => navigate('/form-builder')} />;
  }

  return <FormListView />;
}
