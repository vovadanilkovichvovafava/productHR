/**
 * Document Templates Page (Admin)
 *
 * Manage document templates for signing (NDA, contracts, etc.)
 * - List templates
 * - Create / edit template with variable insertion
 * - Preview with sample data
 */
import { useState, useEffect, useCallback } from 'react';
import {
  FileText,
  Plus,
  Edit3,
  Trash2,
  Eye,
  X,
  Save,
  Copy,
} from 'lucide-react';
import clsx from 'clsx';
import * as docsApi from '@/services/api/documents';
import type { DocumentTemplate, DocumentTemplateCreate } from '@/services/api/documents';

// ─── Helpers ────────────────────────────────────────────────

const AVAILABLE_VARIABLES = [
  { key: 'name', label: 'ФИО сотрудника' },
  { key: 'email', label: 'Email' },
  { key: 'position', label: 'Должность' },
  { key: 'department', label: 'Отдел' },
  { key: 'date', label: 'Текущая дата' },
  { key: 'phone', label: 'Телефон' },
  { key: 'telegram', label: 'Telegram' },
];

function renderPreview(content: string): string {
  const sample: Record<string, string> = {
    name: 'Иванов Иван Иванович',
    email: 'ivanov@company.com',
    position: 'Frontend-разработчик',
    department: 'Разработка',
    date: new Date().toLocaleDateString('ru-RU'),
    phone: '+7 (999) 123-45-67',
    telegram: '@ivanov',
  };
  let result = content;
  for (const [key, value] of Object.entries(sample)) {
    result = result.split(`{{${key}}}`).join(`<mark class="bg-blue-100 text-blue-800 px-1 rounded">${value}</mark>`);
  }
  return result;
}

// ─── Main page ──────────────────────────────────────────────

export default function DocumentTemplatesPage() {
  const [templates, setTemplates] = useState<DocumentTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [showEditor, setShowEditor] = useState(false);
  const [editingTemplate, setEditingTemplate] = useState<DocumentTemplate | null>(null);
  const [showPreview, setShowPreview] = useState(false);
  const [previewContent, setPreviewContent] = useState('');

  // Form state
  const [formName, setFormName] = useState('');
  const [formContent, setFormContent] = useState('');
  const [saving, setSaving] = useState(false);

  const fetchTemplates = useCallback(async () => {
    try {
      const data = await docsApi.getDocumentTemplates();
      setTemplates(data);
    } catch {
      // silently ignore
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchTemplates();
  }, [fetchTemplates]);

  const handleCreate = () => {
    setEditingTemplate(null);
    setFormName('');
    setFormContent('');
    setShowEditor(true);
  };

  const handleEdit = (t: DocumentTemplate) => {
    setEditingTemplate(t);
    setFormName(t.name);
    setFormContent(t.content);
    setShowEditor(true);
  };

  const handleSave = async () => {
    if (!formName.trim() || !formContent.trim()) return;
    setSaving(true);
    try {
      if (editingTemplate) {
        await docsApi.updateDocumentTemplate(editingTemplate.id, {
          name: formName,
          content: formContent,
        });
      } else {
        await docsApi.createDocumentTemplate({
          name: formName,
          content: formContent,
        } as DocumentTemplateCreate);
      }
      setShowEditor(false);
      fetchTemplates();
    } catch {
      // silently ignore
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm('Удалить шаблон?')) return;
    try {
      await docsApi.deleteDocumentTemplate(id);
      fetchTemplates();
    } catch {
      // silently ignore
    }
  };

  const handlePreview = (content: string) => {
    setPreviewContent(content);
    setShowPreview(true);
  };

  const insertVariable = (key: string) => {
    setFormContent((prev) => prev + `{{${key}}}`);
  };

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="p-6 max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-3">
            <FileText className="w-7 h-7 text-emerald-400" />
            Шаблоны документов
          </h1>
          <p className="text-sm text-white/40 mt-1">
            Создавайте шаблоны NDA, договоров и других документов для подписания сотрудниками
          </p>
        </div>
        <button
          onClick={handleCreate}
          className="flex items-center gap-2 px-4 py-2.5 bg-emerald-500 hover:bg-emerald-600 text-white text-sm font-medium rounded-xl shadow-lg shadow-emerald-500/20 transition-colors"
        >
          <Plus className="w-4 h-4" />
          Создать шаблон
        </button>
      </div>

      {/* Templates list */}
      {templates.length === 0 ? (
        <div className="text-center py-16">
          <FileText className="w-16 h-16 text-white/10 mx-auto mb-4" />
          <p className="text-white/30 text-lg">Пока нет шаблонов</p>
          <p className="text-white/20 text-sm mt-1">Создайте первый шаблон для подписания документов</p>
        </div>
      ) : (
        <div className="grid gap-4">
          {templates.map((t) => (
            <div
              key={t.id}
              className="bg-dark-800/50 border border-white/5 rounded-xl p-5 hover:border-white/10 transition-colors"
            >
              <div className="flex items-start justify-between">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-3">
                    <h3 className="text-base font-semibold text-white truncate">{t.name}</h3>
                    {!t.is_active && (
                      <span className="px-2 py-0.5 text-xs bg-red-500/20 text-red-400 rounded-full">
                        Неактивен
                      </span>
                    )}
                  </div>
                  {t.variables && t.variables.length > 0 && (
                    <div className="flex flex-wrap gap-1.5 mt-2">
                      {t.variables.map((v) => (
                        <span
                          key={v}
                          className="px-2 py-0.5 text-xs bg-blue-500/10 text-blue-400 rounded-md"
                        >
                          {`{{${v}}}`}
                        </span>
                      ))}
                    </div>
                  )}
                  <p className="text-xs text-white/20 mt-2">
                    Создан: {t.created_at ? new Date(t.created_at).toLocaleDateString('ru-RU') : '—'}
                  </p>
                </div>
                <div className="flex items-center gap-1 ml-4">
                  <button
                    onClick={() => handlePreview(t.content)}
                    className="p-2 text-white/30 hover:text-blue-400 hover:bg-blue-500/10 rounded-lg transition-colors"
                    title="Предпросмотр"
                  >
                    <Eye className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => handleEdit(t)}
                    className="p-2 text-white/30 hover:text-emerald-400 hover:bg-emerald-500/10 rounded-lg transition-colors"
                    title="Редактировать"
                  >
                    <Edit3 className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => handleDelete(t.id)}
                    className="p-2 text-white/30 hover:text-red-400 hover:bg-red-500/10 rounded-lg transition-colors"
                    title="Удалить"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Editor Modal */}
      {showEditor && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="bg-dark-900 border border-white/10 rounded-2xl w-full max-w-3xl max-h-[90vh] flex flex-col shadow-2xl">
            <div className="flex items-center justify-between px-6 py-4 border-b border-white/5">
              <h2 className="text-lg font-semibold text-white">
                {editingTemplate ? 'Редактировать шаблон' : 'Новый шаблон'}
              </h2>
              <button
                onClick={() => setShowEditor(false)}
                className="p-2 text-white/30 hover:text-white hover:bg-white/5 rounded-lg transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5">
              {/* Name */}
              <div>
                <label className="block text-sm font-medium text-white/60 mb-1.5">
                  Название шаблона
                </label>
                <input
                  type="text"
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  placeholder="NDA, Договор..."
                  className="w-full px-4 py-2.5 bg-dark-800 border border-white/10 rounded-xl text-white placeholder:text-white/20 focus:outline-none focus:border-emerald-500/50 transition-colors"
                />
              </div>

              {/* Variables helper */}
              <div>
                <label className="block text-sm font-medium text-white/60 mb-1.5">
                  Вставить переменную
                </label>
                <div className="flex flex-wrap gap-1.5">
                  {AVAILABLE_VARIABLES.map((v) => (
                    <button
                      key={v.key}
                      type="button"
                      onClick={() => insertVariable(v.key)}
                      className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 rounded-lg transition-colors"
                    >
                      <Copy className="w-3 h-3" />
                      {`{{${v.key}}}`}
                      <span className="text-white/30">({v.label})</span>
                    </button>
                  ))}
                </div>
              </div>

              {/* Content */}
              <div>
                <label className="block text-sm font-medium text-white/60 mb-1.5">
                  Содержание документа
                </label>
                <textarea
                  value={formContent}
                  onChange={(e) => setFormContent(e.target.value)}
                  rows={14}
                  placeholder="Введите текст документа. Используйте {{name}}, {{position}} и другие переменные..."
                  className="w-full px-4 py-3 bg-dark-800 border border-white/10 rounded-xl text-white text-sm placeholder:text-white/20 focus:outline-none focus:border-emerald-500/50 transition-colors resize-y font-mono leading-relaxed"
                />
              </div>
            </div>

            <div className="flex items-center justify-between px-6 py-4 border-t border-white/5">
              <button
                onClick={() => handlePreview(formContent)}
                className="flex items-center gap-2 px-4 py-2 text-sm text-blue-400 hover:bg-blue-500/10 rounded-lg transition-colors"
              >
                <Eye className="w-4 h-4" />
                Предпросмотр
              </button>
              <div className="flex items-center gap-3">
                <button
                  onClick={() => setShowEditor(false)}
                  className="px-4 py-2 text-sm text-white/40 hover:text-white/60 transition-colors"
                >
                  Отмена
                </button>
                <button
                  onClick={handleSave}
                  disabled={saving || !formName.trim() || !formContent.trim()}
                  className={clsx(
                    'flex items-center gap-2 px-5 py-2.5 text-sm font-medium rounded-xl transition-colors',
                    saving || !formName.trim() || !formContent.trim()
                      ? 'bg-emerald-500/30 text-emerald-300/50 cursor-not-allowed'
                      : 'bg-emerald-500 hover:bg-emerald-600 text-white shadow-lg shadow-emerald-500/20'
                  )}
                >
                  <Save className="w-4 h-4" />
                  {saving ? 'Сохранение...' : 'Сохранить'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Preview Modal */}
      {showPreview && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="bg-white rounded-2xl w-full max-w-2xl max-h-[85vh] flex flex-col shadow-2xl">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
              <h2 className="text-lg font-semibold text-gray-900">
                Предпросмотр документа
              </h2>
              <button
                onClick={() => setShowPreview(false)}
                className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto px-8 py-6">
              <div
                className="prose prose-sm max-w-none text-gray-800 whitespace-pre-wrap leading-relaxed"
                dangerouslySetInnerHTML={{ __html: renderPreview(previewContent) }}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
