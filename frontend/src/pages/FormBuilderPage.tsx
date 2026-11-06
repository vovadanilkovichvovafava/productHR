import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Plus,
  Trash2,
  FileText,
  Loader2,
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
import { FormsPageTabs } from '@/features/forms/FormsPageTabs';

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

  const templates = forms.filter(f => f.is_template);
  const others = forms.filter(f => !f.is_template);

  const renderTable = (list: FormTemplate[]) => (
    <div className="hf-forms-table-wrap" style={{ alignSelf: 'stretch', flex: 'none' }}>
      <table className="hf-forms-table" style={{ minWidth: 560 }}>
        <thead>
          <tr>
            <th className="hf-forms-th">Название</th>
            <th className="hf-forms-th">Вопросов</th>
            <th className="hf-forms-th">Создана</th>
            <th className="hf-forms-th" aria-label="Действия" />
          </tr>
        </thead>
        <tbody>
          {list.map((form) => (
            <tr key={form.id} className="hf-forms-row hf-forms-row-click" onClick={() => navigate(`/form-builder/${form.id}`)}>
              <td className="hf-forms-td">
                <span className="hf-forms-name">{form.title}</span>
                {form.is_active === false && (
                  <span className="hf-forms-pill hf-forms-pill-muted" style={{ marginLeft: 8 }}>Неактивна</span>
                )}
                {/* «Ответов» имеет смысл только для разовой анкеты конкретного
                    кандидата (заполнил/нет). У шаблона это агрегат по ВСЕМ, кому
                    его когда-либо отправляли — рядом с названием формы это число
                    не читается и только сбивало с толку. Само поле submissions_count
                    не трогаем — оно используется в защите от удаления шаблона
                    с уже существующими ответами (handleDelete). */}
                {!form.is_template && typeof form.submissions_count === 'number' && (
                  <div className="hf-forms-sub">{form.submissions_count} {submissionWord(form.submissions_count)}</div>
                )}
              </td>
              <td className="hf-forms-td hf-forms-td-num">{form.fields.length} {fieldWord(form.fields.length)}</td>
              <td className="hf-forms-td hf-forms-td-num">
                {form.created_at ? new Date(form.created_at).toLocaleDateString('ru') : '—'}
              </td>
              <td className="hf-forms-td hf-forms-td-actions">
                {/* «Скопировать ссылку» убрана: публичный slug-сабмит намеренно
                    отключён (403) — анкеты уходят персональной token-ссылкой. */}
                {!form.is_template && !observer && (
                  <button
                    type="button"
                    onClick={(e) => handlePromote(form.id, e)}
                    className="hf-forms-action"
                    title="Перенести в шаблоны — станет доступна в карточке кандидата"
                  >
                    В шаблоны
                  </button>
                )}
                {!observer && (
                  <button
                    type="button"
                    onClick={(e) => handleDelete(form.id, e)}
                    className="hf-forms-icon-btn"
                    title="Удалить"
                    aria-label={`Удалить «${form.title}»`}
                  >
                    <Trash2 size={15} />
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

  return (
    <div className="hf-forms-page">
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
      <div className="hf-forms-header">
        <div>
          <div className="hf-forms-heading">
            <h1 className="hf-forms-title">Анкеты</h1>
            <FormsPageTabs />
          </div>
          <p className="hf-forms-subtitle">
            Шаблоны анкет для кандидатов — создайте заранее и отправляйте из карточки кандидата
          </p>
        </div>
        {!observer && (
          <div className="hf-forms-tools">
            <button type="button" onClick={handleCreate} className="hf-forms-btn hf-forms-btn-primary">
              <Plus size={15} />
              Создать шаблон
            </button>
          </div>
        )}
      </div>

      {loading ? (
        <div className="hf-forms-spinner"><Loader2 className="animate-spin" size={26} /></div>
      ) : forms.length === 0 ? (
        <div className="hf-forms-empty" style={{ alignSelf: 'stretch', flex: 'none' }}>
          <FileText size={28} style={{ margin: '0 auto 8px', opacity: 0.5 }} />
          Пока нет шаблонов. Создайте первый — он появится в карточке кандидата в «Шаблонах анкет».
        </div>
      ) : (
        <div style={{ overflowY: 'auto', minHeight: 0 }}>
          <div className="hf-forms-section-title">Шаблоны</div>
          {templates.length === 0 ? (
            <div className="hf-forms-sub" style={{ fontSize: 'var(--hf-fs-2xs)' }}>
              {others.length > 0
                ? 'Пока нет шаблонов — создайте новый или нажмите «В шаблоны» у анкеты ниже, чтобы сделать её переиспользуемой.'
                : 'Пока нет шаблонов — создайте первый, он появится в карточке кандидата.'}
            </div>
          ) : renderTable(templates)}
          {/* Остальные сохранённые анкеты: разовые/старые (созданные до этой
              страницы, без is_template) — чтобы они не «терялись» из виду. */}
          {others.length > 0 && (
            <>
              <div className="hf-forms-section-title">Остальные анкеты</div>
              {renderTable(others)}
            </>
          )}
        </div>
      )}
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
