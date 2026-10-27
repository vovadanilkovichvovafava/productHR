import { backdropClose } from '@/utils/backdropClose';
import { useState, useEffect, useRef, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  X,
  Save,
  Trash2,
  FileText,
  MessageSquare,
  Paperclip,
  ListTree,
  Settings2,
  Plus,
  Download,
  Pencil,
  Check,
  Loader2,
  Calendar,
  Clock,
  User,
  Flag,
  Send,
  Upload,
  AlertTriangle,
} from 'lucide-react';
import toast from 'react-hot-toast';
import clsx from 'clsx';
import * as api from '@/services/api';
import { getErrorDetail } from '@/utils';
import { useAuthStore } from '@/stores/authStore';
import type {
  ProjectTask,
  ProjectMember,
  TaskComment,
  TaskAttachment,
  ProjectTaskStatusDef,
  TaskFieldValue,
  ProjectCustomField,
} from '@/services/api/projects';

// ============================================================
// CONSTANTS
// ============================================================

const PRIORITY_LABELS: Record<number, string> = {
  0: 'Низкий',
  1: 'Нормальный',
  2: 'Высокий',
  3: 'Критический',
};

const PRIORITY_COLORS: Record<number, string> = {
  0: 'bg-gray-100 dark:bg-dark-800 text-gray-500 dark:text-dark-400 border-gray-200 dark:border-white/[0.08]',
  1: 'bg-blue-50 text-blue-600 border-blue-200',
  2: 'bg-amber-50 text-amber-600 border-amber-200',
  3: 'bg-red-50 text-red-600 border-red-200',
};

const DEFAULT_STATUS_LABELS: Record<string, string> = {
  backlog: 'Бэклог',
  todo: 'К выполнению',
  in_progress: 'В работе',
  review: 'Ревью',
  done: 'Готово',
  cancelled: 'Отменена',
};

type ModalTab = 'description' | 'comments' | 'attachments' | 'subtasks' | 'custom_fields';

const TABS: { id: ModalTab; label: string; icon: React.ReactNode }[] = [
  { id: 'description', label: 'Описание', icon: <FileText className="w-4 h-4" /> },
  { id: 'comments', label: 'Комментарии', icon: <MessageSquare className="w-4 h-4" /> },
  { id: 'attachments', label: 'Файлы', icon: <Paperclip className="w-4 h-4" /> },
  { id: 'subtasks', label: 'Подзадачи', icon: <ListTree className="w-4 h-4" /> },
  { id: 'custom_fields', label: 'Поля', icon: <Settings2 className="w-4 h-4" /> },
];

// ============================================================
// HELPERS
// ============================================================

function formatDate(date: string | undefined | null): string {
  if (!date) return '—';
  return new Date(date).toLocaleDateString('ru-RU', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  });
}

function formatDateTime(date: string | undefined | null): string {
  if (!date) return '—';
  return new Date(date).toLocaleString('ru-RU', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// ============================================================
// COMMENT CONTENT RENDERER (with inline attachment cards)
// ============================================================

const ATTACHMENT_REGEX = /\[attachment:(\d+):([^:]+):(\d+)\]/g;
const IMAGE_EXT_REGEX = /\.(png|jpe?g|gif|webp|bmp|svg)$/i;
// Порядок в master-регексе определяет приоритет: mention > bold > code > URL
const INLINE_REGEX = /@\[([^\]\n]+)\]|\*\*([^*\n]+)\*\*|`([^`\n]+)`|(https?:\/\/[^\s<>"')]+)/g;

function renderInline(text: string, keyPrefix: string): React.ReactNode[] {
  const nodes: React.ReactNode[] = [];
  let lastIdx = 0;
  let m: RegExpExecArray | null;
  let i = 0;
  const re = new RegExp(INLINE_REGEX.source, 'g');
  while ((m = re.exec(text)) !== null) {
    if (m.index > lastIdx) {
      nodes.push(
        <span key={`${keyPrefix}-t-${lastIdx}`} className="whitespace-pre-wrap break-words">
          {text.slice(lastIdx, m.index)}
        </span>
      );
    }
    const key = `${keyPrefix}-m-${i++}`;
    if (m[1] !== undefined) {
      // mention @[Name]
      nodes.push(
        <span
          key={key}
          className="inline-flex items-center px-1.5 py-0.5 rounded bg-blue-100 text-blue-700 text-xs font-medium mx-0.5 align-baseline"
        >
          @{m[1]}
        </span>
      );
    } else if (m[2] !== undefined) {
      nodes.push(
        <strong key={key} className="font-semibold">{m[2]}</strong>
      );
    } else if (m[3] !== undefined) {
      nodes.push(
        <code key={key} className="px-1 py-0.5 rounded bg-gray-100 dark:bg-dark-800 text-gray-800 dark:text-dark-100 text-xs font-mono break-all">{m[3]}</code>
      );
    } else if (m[4] !== undefined) {
      nodes.push(
        <a
          key={key}
          href={m[4]}
          target="_blank"
          rel="noopener noreferrer"
          className="text-blue-600 hover:text-blue-800 underline break-all"
        >
          {m[4]}
        </a>
      );
    }
    lastIdx = m.index + m[0].length;
  }
  if (lastIdx < text.length) {
    nodes.push(
      <span key={`${keyPrefix}-t-${lastIdx}`} className="whitespace-pre-wrap break-words">
        {text.slice(lastIdx)}
      </span>
    );
  }
  return nodes;
}

function CommentContent({
  content,
  projectId,
  taskId,
}: {
  content: string;
  projectId: number;
  taskId: number;
}) {
  const parts: React.ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  const regex = new RegExp(ATTACHMENT_REGEX.source, 'g');

  const pushText = (text: string, key: string) => {
    if (!text) return;
    parts.push(
      <span key={key} className="block">
        {renderInline(text, key)}
      </span>
    );
  };

  while ((match = regex.exec(content)) !== null) {
    if (match.index > lastIndex) {
      pushText(content.slice(lastIndex, match.index).replace(/\n+$/, ''), `t-${lastIndex}`);
    }
    const attId = match[1];
    const filename = match[2];
    const fileSize = parseInt(match[3], 10);
    const isImage = IMAGE_EXT_REGEX.test(filename);
    const attUrl = `/api/projects/${projectId}/tasks/${taskId}/attachments/${attId}`;
    if (isImage) {
      parts.push(
        <a
          key={`a-${attId}`}
          href={attUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="block my-1 w-fit max-w-full"
          title={filename}
        >
          <img
            src={attUrl}
            alt={filename}
            loading="lazy"
            className="max-w-full max-h-80 rounded-lg border border-gray-200 dark:border-white/[0.08] object-contain bg-white dark:bg-dark-900"
          />
        </a>
      );
    } else {
      parts.push(
        <a
          key={`a-${attId}`}
          href={attUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-2 px-3 py-2 my-1 bg-blue-50 border border-blue-200 rounded-lg hover:bg-blue-100 transition-colors group w-fit max-w-full"
        >
          <Paperclip className="w-4 h-4 text-blue-500 flex-shrink-0" />
          <span className="text-sm text-blue-700 font-medium truncate max-w-[200px]">{filename}</span>
          <span className="text-[10px] text-blue-400">{formatFileSize(fileSize)}</span>
          <Download className="w-3.5 h-3.5 text-blue-400 group-hover:text-blue-600 flex-shrink-0" />
        </a>
      );
    }
    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < content.length) {
    pushText(content.slice(lastIndex).replace(/^\n+/, ''), `t-${lastIndex}`);
  }

  if (parts.length === 0) {
    const lines = content.split('\n');
    const rendered = lines.map((line, i) => {
      if (line.startsWith('📎 ')) {
        const filenames = line.slice(2).trim();
        return (
          <div key={i} className="flex items-center gap-2 px-3 py-2 my-1 bg-gray-50 dark:bg-dark-800 border border-gray-200 dark:border-white/[0.08] rounded-lg w-fit max-w-full">
            <Paperclip className="w-4 h-4 text-gray-400 dark:text-dark-500 flex-shrink-0" />
            <span className="text-sm text-gray-600 dark:text-dark-300 truncate">{filenames}</span>
          </div>
        );
      }
      return line ? (
        <span key={i} className="block">
          {renderInline(line, `l-${i}`)}
        </span>
      ) : null;
    }).filter(Boolean);
    if (rendered.length > 0) {
      return <div className="text-sm text-gray-600 dark:text-dark-300 space-y-1 break-words overflow-hidden">{rendered}</div>;
    }
    return (
      <p className="text-sm text-gray-600 dark:text-dark-300 whitespace-pre-wrap break-words overflow-hidden">
        {renderInline(content, 'all')}
      </p>
    );
  }

  return <div className="text-sm text-gray-600 dark:text-dark-300 space-y-1 break-words overflow-hidden">{parts}</div>;
}

// ============================================================
// PROPS
// ============================================================

interface TaskDetailModalProps {
  isOpen: boolean;
  onClose: () => void;
  projectId: number;
  taskId?: number | null;  // null = create mode
  mode?: 'create' | 'edit';  // defaults to 'edit' if taskId provided
  members: ProjectMember[];
  statuses?: ProjectTaskStatusDef[];
  onTaskUpdated?: () => void;
  onTaskDeleted?: () => void;
  onTaskCreated?: (task: api.ProjectTask) => void;
  parentTaskId?: number;
  /** Если передан — после загрузки коментов модалка переключится на вкладку
   *  'comments' и проскроллит к нужному коментарию + подсветит его. */
  scrollToCommentId?: number | null;
}

// ============================================================
// DESCRIPTION TAB
// ============================================================

function DescriptionTab({
  description,
  tags,
  onDescriptionChange,
  onTagsChange,
}: {
  description: string;
  tags: string[];
  onDescriptionChange: (v: string) => void;
  onTagsChange: (v: string[]) => void;
}) {
  const [tagInput, setTagInput] = useState('');

  const addTag = () => {
    const tag = tagInput.trim();
    if (tag && !tags.includes(tag)) {
      onTagsChange([...tags, tag]);
    }
    setTagInput('');
  };

  const removeTag = (t: string) => {
    onTagsChange(tags.filter((x) => x !== t));
  };

  return (
    <div className="space-y-4">
      <div>
        <label className="text-xs font-medium text-gray-500 dark:text-dark-400 uppercase tracking-wider mb-2 block">Описание</label>
        <textarea
          value={description}
          onChange={(e) => onDescriptionChange(e.target.value)}
          rows={8}
          placeholder="Добавьте описание задачи..."
          className="w-full bg-white dark:bg-dark-900 border border-gray-300 dark:border-white/10 rounded-lg px-4 py-3 text-sm text-gray-900 dark:text-dark-100 placeholder-gray-400 dark:placeholder-dark-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 resize-y"
        />
      </div>
      <div>
        <label className="text-xs font-medium text-gray-500 dark:text-dark-400 uppercase tracking-wider mb-2 block">Теги</label>
        <div className="flex flex-wrap gap-2 mb-2">
          {tags.map((tag) => (
            <span
              key={tag}
              className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium bg-purple-50 text-purple-700 rounded-lg border border-purple-200"
            >
              {tag}
              <button onClick={() => removeTag(tag)} className="hover:text-purple-900 transition-colors">
                <X className="w-3 h-3" />
              </button>
            </span>
          ))}
        </div>
        <div className="flex gap-2">
          <input
            value={tagInput}
            onChange={(e) => setTagInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                addTag();
              }
            }}
            placeholder="Новый тег..."
            className="flex-1 bg-white dark:bg-dark-900 border border-gray-300 dark:border-white/10 rounded-lg px-3 py-1.5 text-sm text-gray-900 dark:text-dark-100 placeholder-gray-400 dark:placeholder-dark-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
          />
          <button
            onClick={addTag}
            className="px-3 py-1.5 text-xs font-medium text-gray-600 dark:text-dark-300 hover:text-gray-900 dark:hover:text-dark-100 dark:text-dark-100 bg-gray-50 dark:bg-dark-800 hover:bg-gray-100 dark:hover:bg-dark-800 rounded-lg border border-gray-200 dark:border-white/[0.08] transition-colors"
          >
            <Plus className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
}

// ============================================================
// COMMENTS TAB
// ============================================================

function CommentsTab({
  projectId,
  taskId,
  members,
  scrollToCommentId,
}: {
  projectId: number;
  taskId: number;
  members: ProjectMember[];
  scrollToCommentId?: number | null;
}) {
  const currentUser = useAuthStore((s) => s.user);
  const isSuperAdmin = useAuthStore((s) => s.isSuperAdmin);
  const isOwner = useAuthStore((s) => s.isOwner);
  const canManageComment = (authorId: number): boolean => {
    if (!currentUser) return false;
    if (currentUser.id === authorId) return true;
    return isSuperAdmin() || isOwner();
  };

  const [comments, setComments] = useState<TaskComment[]>([]);
  const [loading, setLoading] = useState(true);
  const [newComment, setNewComment] = useState('');
  const [sending, setSending] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editContent, setEditContent] = useState('');
  const [pendingFiles, setPendingFiles] = useState<File[]>([]);
  const [fileInputKey, setFileInputKey] = useState(0);
  const commentFileRef = useRef<HTMLInputElement>(null);

  // Mention autocomplete state
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [mentionQuery, setMentionQuery] = useState<string | null>(null);
  const [mentionStart, setMentionStart] = useState<number>(-1);
  const [mentionIndex, setMentionIndex] = useState<number>(0);

  const mentionCandidates = mentionQuery === null
    ? []
    : members
        .filter((m) => m.user_name && m.user_name.toLowerCase().includes(mentionQuery.toLowerCase()))
        .slice(0, 8);

  const updateMentionState = (value: string, caret: number) => {
    // Ищем последний @ до каретки, у которого перед ним пробел/перевод строки/начало
    const before = value.slice(0, caret);
    const at = before.lastIndexOf('@');
    if (at === -1) { setMentionQuery(null); return; }
    // @ должен быть в начале строки или после пробела
    if (at > 0 && !/\s/.test(before[at - 1])) { setMentionQuery(null); return; }
    const query = before.slice(at + 1);
    // Не активируем если в query есть пробел/скобки — значит уже не мeншн
    if (/[\s\[\]]/.test(query) || query.length > 30) { setMentionQuery(null); return; }
    setMentionQuery(query);
    setMentionStart(at);
    setMentionIndex(0);
  };

  const insertMention = (name: string) => {
    if (mentionStart < 0 || !textareaRef.current) return;
    const ta = textareaRef.current;
    const caret = ta.selectionStart;
    const before = newComment.slice(0, mentionStart);
    const after = newComment.slice(caret);
    const inserted = `@[${name}] `;
    const next = before + inserted + after;
    setNewComment(next);
    setMentionQuery(null);
    // Ставим каретку сразу после вставленного
    setTimeout(() => {
      const pos = before.length + inserted.length;
      ta.focus();
      ta.setSelectionRange(pos, pos);
    }, 0);
  };

  const loadComments = useCallback(async () => {
    try {
      const data = await api.getTaskComments(projectId, taskId);
      setComments(data);
    } catch {
      toast.error('Не удалось загрузить комментарии');
    } finally {
      setLoading(false);
    }
  }, [projectId, taskId]);

  // Если пришли по deep-link с notification — скроллим к нужному коментарию
  // и подсвечиваем его на 2 секунды.
  const [highlightedCommentId, setHighlightedCommentId] = useState<number | null>(null);
  useEffect(() => {
    if (!scrollToCommentId || loading || comments.length === 0) return;
    const el = document.querySelector(`[data-comment-id="${scrollToCommentId}"]`);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      setHighlightedCommentId(scrollToCommentId);
      const t = setTimeout(() => setHighlightedCommentId(null), 2500);
      return () => clearTimeout(t);
    }
  }, [scrollToCommentId, loading, comments.length]);

  useEffect(() => {
    loadComments();
  }, [loadComments]);

  const handleAdd = async () => {
    const text = newComment.trim();
    if (!text && pendingFiles.length === 0) return;
    setSending(true);
    try {
      // Upload attached files and collect attachment metadata
      const uploaded: { id: number; original_filename: string; file_size: number }[] = [];
      for (const file of pendingFiles) {
        const att = await api.uploadTaskAttachment(projectId, taskId, file);
        uploaded.push({ id: att.id, original_filename: att.original_filename, file_size: att.file_size });
      }
      // Build comment text with embedded attachment markers
      const attachmentMarkers = uploaded
        .map(a => `[attachment:${a.id}:${a.original_filename}:${a.file_size}]`)
        .join('\n');
      const fullText = text && attachmentMarkers
        ? `${text}\n${attachmentMarkers}`
        : attachmentMarkers || text;
      if (fullText) {
        await api.createTaskComment(projectId, taskId, fullText);
      }
      setNewComment('');
      setPendingFiles([]);
      await loadComments();
      toast.success(uploaded.length > 0 ? 'Комментарий и файлы добавлены' : 'Комментарий добавлен');
    } catch {
      toast.error('Не удалось добавить комментарий');
    } finally {
      setSending(false);
    }
  };

  const handlePaste = (e: React.ClipboardEvent) => {
    const items = e.clipboardData?.items;
    if (!items) return;
    for (let i = 0; i < items.length; i++) {
      if (items[i].type.startsWith('image/')) {
        e.preventDefault();
        const file = items[i].getAsFile();
        if (file) {
          const named = new File([file], `screenshot-${Date.now()}.png`, { type: file.type });
          setPendingFiles(prev => [...prev, named]);
          toast.success('Скриншот прикреплён');
        }
      }
    }
  };

  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      const newFiles = Array.from(files);
      setPendingFiles(prev => [...prev, ...newFiles]);
      toast.success(`${newFiles.length > 1 ? newFiles.length + ' файлов' : newFiles[0].name} прикреплено`);
    }
    // Reset input via key to allow re-selecting same file
    setFileInputKey(k => k + 1);
  }, []);

  const handleUpdate = async (commentId: number) => {
    const text = editContent.trim();
    if (!text) return;
    try {
      await api.updateTaskComment(projectId, taskId, commentId, text);
      setEditingId(null);
      setEditContent('');
      await loadComments();
      toast.success('Комментарий обновлён');
    } catch {
      toast.error('Не удалось обновить комментарий');
    }
  };

  const handleDelete = async (commentId: number) => {
    try {
      await api.deleteTaskComment(projectId, taskId, commentId);
      await loadComments();
      toast.success('Комментарий удалён');
    } catch {
      toast.error('Не удалось удалить комментарий');
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="w-6 h-6 text-gray-300 animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Comment list */}
      <div className="space-y-3 max-h-[400px] overflow-y-auto pr-1">
        {comments.length === 0 ? (
          <p className="text-sm text-gray-400 dark:text-dark-500 text-center py-8">Нет комментариев</p>
        ) : (
          comments.map((c) => (
            <div
              key={c.id}
              data-comment-id={c.id}
              className={clsx(
                'bg-gray-50 dark:bg-dark-800 border border-gray-200 dark:border-white/[0.08] rounded-xl p-3 transition-colors',
                highlightedCommentId === c.id && 'ring-2 ring-blue-500 bg-blue-50 dark:bg-blue-500/10',
              )}>
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <div className="w-6 h-6 rounded-full bg-gradient-to-br from-blue-400 to-purple-400 flex items-center justify-center">
                    <span className="text-[9px] text-white font-medium">
                      {(c.user_name || '?').charAt(0).toUpperCase()}
                    </span>
                  </div>
                  <span className="text-xs font-medium text-gray-700 dark:text-dark-200">{c.user_name || `User ${c.user_id}`}</span>
                  <span className="text-[10px] text-gray-400 dark:text-dark-500">{formatDateTime(c.created_at)}</span>
                  {c.edited_at && <span className="text-[10px] text-gray-300">(ред.)</span>}
                </div>
                {canManageComment(c.user_id) && (
                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => {
                        setEditingId(c.id);
                        setEditContent(c.content);
                      }}
                      className="p-1 text-gray-300 hover:text-gray-500 dark:text-dark-400 transition-colors"
                      title="Редактировать"
                    >
                      <Pencil className="w-3 h-3" />
                    </button>
                    <button
                      onClick={() => handleDelete(c.id)}
                      className="p-1 text-gray-300 hover:text-red-500 transition-colors"
                      title="Удалить"
                    >
                      <Trash2 className="w-3 h-3" />
                    </button>
                  </div>
                )}
              </div>
              {editingId === c.id ? (
                <div className="space-y-2">
                  <textarea
                    value={editContent}
                    onChange={(e) => setEditContent(e.target.value)}
                    rows={3}
                    className="w-full bg-white dark:bg-dark-900 border border-gray-300 dark:border-white/10 rounded-lg px-3 py-2 text-sm text-gray-900 dark:text-dark-100 placeholder-gray-400 dark:placeholder-dark-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 resize-y min-h-[80px] max-h-[400px]"
                  />
                  <div className="flex gap-2">
                    <button
                      onClick={() => handleUpdate(c.id)}
                      className="px-3 py-1 text-xs font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg transition-colors"
                    >
                      Сохранить
                    </button>
                    <button
                      onClick={() => {
                        setEditingId(null);
                        setEditContent('');
                      }}
                      className="px-3 py-1 text-xs text-gray-500 dark:text-dark-400 hover:text-gray-700 dark:hover:text-dark-200 dark:text-dark-200 transition-colors"
                    >
                      Отмена
                    </button>
                  </div>
                </div>
              ) : (
                <CommentContent content={c.content} projectId={projectId} taskId={taskId} />
              )}
            </div>
          ))
        )}
      </div>

      {/* Pending files preview */}
      {pendingFiles.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-2">
          {pendingFiles.map((f, i) => (
            <div key={i} className="flex items-center gap-1 px-2 py-1 bg-blue-50 border border-blue-200 rounded-lg text-xs text-blue-700">
              <Paperclip className="w-3 h-3" />
              <span className="max-w-[120px] truncate">{f.name}</span>
              <button onClick={() => setPendingFiles(prev => prev.filter((_, idx) => idx !== i))} className="hover:text-red-500">
                <X className="w-3 h-3" />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* New comment input */}
      <div className="flex gap-2">
        <div className="flex-1 relative">
          <textarea
            ref={textareaRef}
            value={newComment}
            onChange={(e) => {
              const v = e.target.value;
              setNewComment(v);
              updateMentionState(v, e.target.selectionStart);
            }}
            onKeyUp={(e) => {
              const el = e.currentTarget;
              updateMentionState(el.value, el.selectionStart);
            }}
            onPaste={handlePaste}
            onBlur={() => setTimeout(() => setMentionQuery(null), 150)}
            onKeyDown={(e) => {
              if (mentionQuery !== null && mentionCandidates.length > 0) {
                if (e.key === 'ArrowDown') {
                  e.preventDefault();
                  setMentionIndex((i) => (i + 1) % mentionCandidates.length);
                  return;
                }
                if (e.key === 'ArrowUp') {
                  e.preventDefault();
                  setMentionIndex((i) => (i - 1 + mentionCandidates.length) % mentionCandidates.length);
                  return;
                }
                if (e.key === 'Enter' || e.key === 'Tab') {
                  e.preventDefault();
                  const pick = mentionCandidates[mentionIndex];
                  if (pick?.user_name) insertMention(pick.user_name);
                  return;
                }
                if (e.key === 'Escape') {
                  e.preventDefault();
                  setMentionQuery(null);
                  return;
                }
              }
              if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                e.preventDefault();
                handleAdd();
              }
            }}
            rows={2}
            placeholder="Комментарий... (@ — упомянуть, **жирный**, `код`, Ctrl+V — скрин, Ctrl+Enter — отправить)"
            className="w-full bg-white dark:bg-dark-900 border border-gray-300 dark:border-white/10 rounded-xl px-4 py-2 pr-10 text-sm text-gray-900 dark:text-dark-100 placeholder-gray-400 dark:placeholder-dark-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 resize-y min-h-[56px] max-h-[400px]"
          />
          {mentionQuery !== null && mentionCandidates.length > 0 && (
            <div className="absolute left-2 bottom-full mb-1 z-20 w-64 max-h-56 overflow-y-auto bg-white dark:bg-dark-900 border border-gray-200 dark:border-white/[0.08] rounded-lg shadow-lg">
              {mentionCandidates.map((m, i) => (
                <button
                  key={m.id}
                  type="button"
                  onMouseDown={(e) => { e.preventDefault(); if (m.user_name) insertMention(m.user_name); }}
                  className={clsx(
                    'w-full flex items-center gap-2 px-3 py-2 text-left text-sm',
                    i === mentionIndex ? 'bg-blue-50 text-blue-700' : 'text-gray-700 dark:text-dark-200 hover:bg-gray-50 dark:hover:bg-dark-800 dark:bg-dark-800'
                  )}
                >
                  <div className="w-6 h-6 rounded-full bg-gradient-to-br from-blue-400 to-purple-400 flex items-center justify-center flex-shrink-0">
                    <span className="text-[9px] text-white font-medium">
                      {(m.user_name || '?').charAt(0).toUpperCase()}
                    </span>
                  </div>
                  <span className="truncate">{m.user_name}</span>
                  <span className="ml-auto text-[10px] text-gray-400 dark:text-dark-500 uppercase">{m.role}</span>
                </button>
              ))}
            </div>
          )}
          <button
            type="button"
            onClick={() => commentFileRef.current?.click()}
            className="absolute right-2 bottom-2 p-1 text-gray-400 dark:text-dark-500 hover:text-gray-600 dark:text-dark-300 transition-colors"
            title="Прикрепить файл"
          >
            <Paperclip className="w-4 h-4" />
          </button>
          <input
            key={fileInputKey}
            ref={commentFileRef}
            type="file"
            multiple
            accept="image/*,.pdf,.doc,.docx,.xls,.xlsx,.txt,.zip,.rar"
            style={{ position: 'absolute', width: 0, height: 0, opacity: 0, overflow: 'hidden' }}
            onChange={handleFileSelect}
          />
        </div>
        <button
          onClick={handleAdd}
          disabled={sending || (!newComment.trim() && pendingFiles.length === 0)}
          className="self-end px-3 py-2 text-white bg-blue-600 hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed rounded-xl transition-colors"
        >
          {sending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
        </button>
      </div>
    </div>
  );
}

// ============================================================
// ATTACHMENTS TAB
// ============================================================

function AttachmentsTab({
  projectId,
  taskId,
}: {
  projectId: number;
  taskId: number;
}) {
  const [attachments, setAttachments] = useState<TaskAttachment[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadAttachments = useCallback(async () => {
    try {
      const data = await api.getTaskAttachments(projectId, taskId);
      setAttachments(data);
    } catch {
      toast.error('Не удалось загрузить файлы');
    } finally {
      setLoading(false);
    }
  }, [projectId, taskId]);

  useEffect(() => {
    loadAttachments();
  }, [loadAttachments]);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      await api.uploadTaskAttachment(projectId, taskId, file);
      await loadAttachments();
      toast.success('Файл загружен');
    } catch {
      toast.error('Не удалось загрузить файл');
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const handleDelete = async (attachmentId: number) => {
    try {
      await api.deleteTaskAttachment(projectId, taskId, attachmentId);
      await loadAttachments();
      toast.success('Файл удалён');
    } catch {
      toast.error('Не удалось удалить файл');
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="w-6 h-6 text-gray-300 animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Upload button */}
      <div>
        <input
          ref={fileInputRef}
          type="file"
          className="hidden"
          onChange={handleUpload}
        />
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={uploading}
          className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-gray-600 dark:text-dark-300 hover:text-gray-900 dark:hover:text-dark-100 dark:text-dark-100 bg-gray-50 dark:bg-dark-800 hover:bg-gray-100 dark:hover:bg-dark-800 rounded-xl border border-gray-200 dark:border-white/[0.08] transition-colors disabled:opacity-40"
        >
          {uploading ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Upload className="w-4 h-4" />
          )}
          {uploading ? 'Загрузка...' : 'Загрузить файл'}
        </button>
      </div>

      {/* File list */}
      {attachments.length === 0 ? (
        <p className="text-sm text-gray-400 dark:text-dark-500 text-center py-8">Нет файлов</p>
      ) : (
        <div className="space-y-2">
          {attachments.map((a) => (
            <div
              key={a.id}
              className="flex items-center justify-between bg-gray-50 dark:bg-dark-800 border border-gray-200 dark:border-white/[0.08] rounded-xl px-4 py-3"
            >
              <div className="flex items-center gap-3 min-w-0">
                <Paperclip className="w-4 h-4 text-gray-400 dark:text-dark-500 flex-shrink-0" />
                <div className="min-w-0">
                  <p className="text-sm text-gray-900 dark:text-dark-100 truncate">{a.original_filename}</p>
                  <div className="flex items-center gap-2 text-[10px] text-gray-400 dark:text-dark-500">
                    <span>{formatFileSize(a.file_size)}</span>
                    {a.user_name && <span>{a.user_name}</span>}
                    {a.created_at && <span>{formatDateTime(a.created_at)}</span>}
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-1 flex-shrink-0">
                <a
                  href={`/api/projects/${projectId}/tasks/${taskId}/attachments/${a.id}/download`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="p-1.5 text-gray-300 hover:text-gray-600 dark:text-dark-300 transition-colors"
                  title="Скачать"
                >
                  <Download className="w-4 h-4" />
                </a>
                <button
                  onClick={() => handleDelete(a.id)}
                  className="p-1.5 text-gray-300 hover:text-red-500 transition-colors"
                  title="Удалить"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ============================================================
// SUBTASKS TAB
// ============================================================

function SubtasksTab({
  projectId,
  taskId,
  members,
  statuses,
}: {
  projectId: number;
  taskId: number;
  members: ProjectMember[];
  statuses: ProjectTaskStatusDef[];
}) {
  const [subtasks, setSubtasks] = useState<ProjectTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  const [newDescription, setNewDescription] = useState('');
  const [newAssignee, setNewAssignee] = useState<number | ''>('');
  const [creating, setCreating] = useState(false);
  // Раскрытое описание подзадачи + инлайн-редактирование
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [editDescId, setEditDescId] = useState<number | null>(null);
  const [editDescText, setEditDescText] = useState('');
  const [savingDesc, setSavingDesc] = useState(false);

  const loadSubtasks = useCallback(async () => {
    try {
      const data = await api.getSubtasks(projectId, taskId);
      setSubtasks(data);
    } catch {
      toast.error('Не удалось загрузить подзадачи');
    } finally {
      setLoading(false);
    }
  }, [projectId, taskId]);

  useEffect(() => {
    loadSubtasks();
  }, [loadSubtasks]);

  const handleCreate = async () => {
    const title = newTitle.trim();
    if (!title) return;
    setCreating(true);
    try {
      await api.createProjectTask(projectId, {
        title,
        description: newDescription.trim() || undefined,
        parent_task_id: taskId,
        assignee_id: newAssignee || undefined,
      });
      setNewTitle('');
      setNewDescription('');
      setNewAssignee('');
      setShowAdd(false);
      await loadSubtasks();
      toast.success('Подзадача создана');
    } catch (err) {
      toast.error(getErrorDetail(err, 'Не удалось создать подзадачу'));
    } finally {
      setCreating(false);
    }
  };

  const handleSaveDescription = async (subtaskId: number) => {
    setSavingDesc(true);
    try {
      const updated = await api.updateProjectTask(projectId, subtaskId, {
        description: editDescText.trim() || undefined,
      });
      setSubtasks((prev) => prev.map((s) => (s.id === subtaskId ? updated : s)));
      setEditDescId(null);
      toast.success('Описание сохранено');
    } catch (err) {
      toast.error(getErrorDetail(err, 'Не удалось сохранить описание'));
    } finally {
      setSavingDesc(false);
    }
  };

  const handleDeleteSubtask = async (subtaskId: number) => {
    if (!confirm('Удалить подзадачу?')) return;
    try {
      await api.deleteProjectTask(projectId, subtaskId);
      setSubtasks((prev) => prev.filter((s) => s.id !== subtaskId));
      toast.success('Подзадача удалена');
    } catch (err) {
      toast.error(getErrorDetail(err, 'Не удалось удалить подзадачу'));
    }
  };

  const handleChangeStatus = async (subtaskId: number, newStatus: string) => {
    try {
      await api.updateProjectTask(projectId, subtaskId, { status: newStatus });
      setSubtasks((prev) => prev.map((s) => (s.id === subtaskId ? { ...s, status: newStatus } : s)));
    } catch (err) {
      toast.error(getErrorDetail(err, 'Не удалось изменить статус'));
    }
  };

  const handleChangeAssignee = async (subtaskId: number, assigneeId: number | null) => {
    try {
      const updated = await api.updateProjectTask(projectId, subtaskId, {
        assignee_id: assigneeId ?? undefined,
      });
      setSubtasks((prev) => prev.map((s) => (s.id === subtaskId ? updated : s)));
    } catch (err) {
      toast.error(getErrorDetail(err, 'Не удалось изменить исполнителя'));
    }
  };

  const getStatusColor = (slug: string): string | undefined => {
    return statuses.find((s) => s.slug === slug)?.color;
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="w-6 h-6 text-gray-300 animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Add subtask button */}
      {!showAdd ? (
        <button
          onClick={() => setShowAdd(true)}
          className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-gray-600 dark:text-dark-300 hover:text-gray-900 dark:hover:text-dark-100 dark:text-dark-100 bg-gray-50 dark:bg-dark-800 hover:bg-gray-100 dark:hover:bg-dark-800 rounded-xl border border-gray-200 dark:border-white/[0.08] transition-colors"
        >
          <Plus className="w-4 h-4" />
          Добавить подзадачу
        </button>
      ) : (
        <div className="bg-gray-50 dark:bg-dark-800 border border-gray-200 dark:border-white/[0.08] rounded-xl p-4 space-y-3">
          <input
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleCreate();
              }
            }}
            placeholder="Название подзадачи..."
            className="w-full bg-white dark:bg-dark-900 border border-gray-300 dark:border-white/10 rounded-lg px-3 py-2 text-sm text-gray-900 dark:text-dark-100 placeholder-gray-400 dark:placeholder-dark-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
            autoFocus
          />
          <textarea
            value={newDescription}
            onChange={(e) => setNewDescription(e.target.value)}
            placeholder="Описание (необязательно)"
            rows={2}
            className="w-full bg-white dark:bg-dark-900 border border-gray-300 dark:border-white/10 rounded-lg px-3 py-2 text-sm text-gray-900 dark:text-dark-100 placeholder-gray-400 dark:placeholder-dark-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 resize-y"
          />
          <select
            value={newAssignee}
            onChange={(e) => setNewAssignee(e.target.value ? Number(e.target.value) : '')}
            className="w-full bg-white dark:bg-dark-900 border border-gray-300 dark:border-white/10 rounded-lg px-3 py-2 text-sm text-gray-900 dark:text-dark-100 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 cursor-pointer"
          >
            <option value="">Без исполнителя</option>
            {members.map((m) => (
              <option key={m.user_id} value={m.user_id}>
                {m.user_name || m.user_email || `User ${m.user_id}`}
              </option>
            ))}
          </select>
          <div className="flex gap-2">
            <button
              onClick={handleCreate}
              disabled={creating || !newTitle.trim()}
              className="px-4 py-1.5 text-xs font-medium text-white bg-blue-600 hover:bg-blue-700 disabled:opacity-40 rounded-lg transition-colors"
            >
              {creating ? 'Создание...' : 'Создать'}
            </button>
            <button
              onClick={() => {
                setShowAdd(false);
                setNewTitle('');
                setNewDescription('');
                setNewAssignee('');
              }}
              className="px-4 py-1.5 text-xs text-gray-500 dark:text-dark-400 hover:text-gray-700 dark:hover:text-dark-200 dark:text-dark-200 transition-colors"
            >
              Отмена
            </button>
          </div>
        </div>
      )}

      {/* Subtask list */}
      {subtasks.length === 0 ? (
        <p className="text-sm text-gray-400 dark:text-dark-500 text-center py-8">Нет подзадач</p>
      ) : (
        <div className="space-y-2">
          {subtasks.map((st) => {
            const dotColor = getStatusColor(st.status);
            const isExpanded = expandedId === st.id;
            const isEditingDesc = editDescId === st.id;
            return (
              <div
                key={st.id}
                className="bg-gray-50 dark:bg-dark-800 border border-gray-200 dark:border-white/[0.08] rounded-xl group"
              >
                <div className="flex items-center justify-between px-4 py-3">
                  <div
                    className="flex items-center gap-3 min-w-0 flex-1 cursor-pointer"
                    onClick={() => setExpandedId(isExpanded ? null : st.id)}
                    title={isExpanded ? 'Свернуть' : 'Раскрыть'}
                  >
                    {dotColor ? (
                      <span
                        className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                        style={{ backgroundColor: dotColor }}
                      />
                    ) : (
                      <span className={clsx('w-2.5 h-2.5 rounded-full flex-shrink-0', {
                        'bg-green-400': st.status === 'done',
                        'bg-amber-400': st.status === 'in_progress',
                        'bg-blue-400': st.status === 'todo',
                        'bg-gray-300': st.status === 'backlog' || st.status === 'cancelled',
                        'bg-purple-400': st.status === 'review',
                      })} />
                    )}
                    <div className="min-w-0 flex-1">
                      <p className={clsx('text-sm break-words', st.status === 'done' ? 'text-gray-400 dark:text-dark-500 line-through' : 'text-gray-900 dark:text-dark-100')}>
                        {st.title}
                      </p>
                      <select
                        value={st.status}
                        onChange={(e) => handleChangeStatus(st.id, e.target.value)}
                        onClick={(e) => e.stopPropagation()}
                        className="text-[10px] text-gray-500 dark:text-dark-400 bg-transparent border-none p-0 cursor-pointer hover:text-gray-700 dark:hover:text-dark-200 dark:text-dark-200 focus:outline-none"
                      >
                        {statuses.length > 0 ? (
                          statuses.map((s) => (
                            <option key={s.slug} value={s.slug}>{s.name}</option>
                          ))
                        ) : (
                          Object.entries(DEFAULT_STATUS_LABELS).map(([slug, label]) => (
                            <option key={slug} value={slug}>{label}</option>
                          ))
                        )}
                      </select>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0 ml-3">
                    {st.description && !isExpanded && (
                      <span className="text-[10px] text-gray-400 dark:text-dark-500" title="Есть описание">📝</span>
                    )}
                    <select
                      value={st.assignee_id ?? ''}
                      onChange={(e) => handleChangeAssignee(st.id, e.target.value ? Number(e.target.value) : null)}
                      onClick={(e) => e.stopPropagation()}
                      className="text-xs text-gray-600 dark:text-dark-300 bg-white dark:bg-dark-900 border border-gray-200 dark:border-white/[0.08] rounded-md px-2 py-1 cursor-pointer hover:border-gray-300 dark:hover:border-white/10 dark:border-white/10 focus:outline-none focus:ring-1 focus:ring-blue-500"
                    >
                      <option value="">Без исполнителя</option>
                      {members.map((m) => (
                        <option key={m.user_id} value={m.user_id}>
                          {m.user_name || m.user_email || `User ${m.user_id}`}
                        </option>
                      ))}
                    </select>
                    <button
                      onClick={(e) => { e.stopPropagation(); handleDeleteSubtask(st.id); }}
                      className="p-1.5 text-gray-400 dark:text-dark-500 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-500/10 rounded-md opacity-0 group-hover:opacity-100 transition-all"
                      title="Удалить подзадачу"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>

                {/* Раскрытое описание + inline-редактирование */}
                {isExpanded && (
                  <div className="border-t border-gray-200 dark:border-white/[0.08] px-4 py-3">
                    {isEditingDesc ? (
                      <div className="space-y-2">
                        <textarea
                          value={editDescText}
                          onChange={(e) => setEditDescText(e.target.value)}
                          disabled={savingDesc}
                          rows={3}
                          placeholder="Описание подзадачи..."
                          className="w-full bg-white dark:bg-dark-900 border border-gray-300 dark:border-white/10 rounded-lg px-3 py-2 text-sm text-gray-900 dark:text-dark-100 placeholder-gray-400 dark:placeholder-dark-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 resize-y disabled:opacity-50"
                          autoFocus
                        />
                        <div className="flex justify-end gap-2">
                          <button
                            onClick={() => setEditDescId(null)}
                            disabled={savingDesc}
                            className="px-3 py-1 text-xs text-gray-500 dark:text-dark-400 hover:text-gray-700 dark:hover:text-dark-200 dark:text-dark-200 disabled:opacity-50"
                          >
                            Отмена
                          </button>
                          <button
                            onClick={() => handleSaveDescription(st.id)}
                            disabled={savingDesc}
                            className="px-3 py-1 text-xs font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-md disabled:opacity-50"
                          >
                            {savingDesc ? 'Сохраняем…' : 'Сохранить'}
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div className="flex items-start justify-between gap-3">
                        <p className="text-xs text-gray-600 dark:text-dark-300 whitespace-pre-wrap break-words flex-1">
                          {st.description || <span className="italic text-gray-400 dark:text-dark-500">Нет описания</span>}
                        </p>
                        <button
                          onClick={() => { setEditDescText(st.description || ''); setEditDescId(st.id); }}
                          className="text-[11px] text-blue-600 dark:text-blue-400 hover:underline flex-shrink-0"
                        >
                          {st.description ? 'Изменить' : '+ описание'}
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ============================================================
// CUSTOM FIELDS TAB
// ============================================================

function CustomFieldsTab({
  projectId,
  taskId,
}: {
  projectId: number;
  taskId: number;
}) {
  const [fields, setFields] = useState<ProjectCustomField[]>([]);
  const [values, setValues] = useState<TaskFieldValue[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<Record<number, boolean>>({});

  useEffect(() => {
    const load = async () => {
      try {
        const [f, v] = await Promise.all([
          api.getCustomFields(projectId),
          api.getTaskFieldValues(projectId, taskId),
        ]);
        setFields(f);
        setValues(v);
      } catch {
        toast.error('Не удалось загрузить поля');
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [projectId, taskId]);

  const handleChange = async (fieldId: number, value: string) => {
    // Optimistic update
    setValues((prev) =>
      prev.map((v) => (v.field_id === fieldId ? { ...v, value } : v))
    );
    setSaving((prev) => ({ ...prev, [fieldId]: true }));
    try {
      await api.setTaskFieldValue(projectId, taskId, fieldId, value);
    } catch {
      toast.error('Не удалось сохранить значение');
    } finally {
      setSaving((prev) => ({ ...prev, [fieldId]: false }));
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="w-6 h-6 text-gray-300 animate-spin" />
      </div>
    );
  }

  if (fields.length === 0) {
    return <p className="text-sm text-gray-400 dark:text-dark-500 text-center py-8">Настраиваемые поля не добавлены</p>;
  }

  return (
    <div className="space-y-4">
      {fields.map((field) => {
        const fv = values.find((v) => v.field_id === field.id);
        const currentValue = fv?.value ?? '';
        const isSaving = saving[field.id] ?? false;

        return (
          <div key={field.id}>
            <label className="flex items-center gap-2 text-xs font-medium text-gray-500 dark:text-dark-400 uppercase tracking-wider mb-1.5">
              {field.name}
              {field.is_required && <span className="text-red-500">*</span>}
              {isSaving && <Loader2 className="w-3 h-3 animate-spin text-gray-300" />}
            </label>
            {field.field_type === 'text' && (
              <input
                value={currentValue}
                onChange={(e) => handleChange(field.id, e.target.value)}
                className="w-full bg-white dark:bg-dark-900 border border-gray-300 dark:border-white/10 rounded-lg px-3 py-2 text-sm text-gray-900 dark:text-dark-100 placeholder-gray-400 dark:placeholder-dark-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
              />
            )}
            {(field.field_type === 'number' || field.field_type === 'currency') && (
              <div className="flex items-center gap-2">
                <input
                  type="number"
                  value={currentValue}
                  onChange={(e) => handleChange(field.id, e.target.value)}
                  className="w-full bg-white dark:bg-dark-900 border border-gray-300 dark:border-white/10 rounded-lg px-3 py-2 text-sm text-gray-900 dark:text-dark-100 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
                />
                {field.field_type === 'currency' && field.currency && (
                  <span className="text-xs text-gray-400 dark:text-dark-500">{field.currency}</span>
                )}
              </div>
            )}
            {field.field_type === 'select' && (
              <select
                value={currentValue}
                onChange={(e) => handleChange(field.id, e.target.value)}
                className="w-full bg-white dark:bg-dark-900 border border-gray-300 dark:border-white/10 rounded-lg px-3 py-2 text-sm text-gray-900 dark:text-dark-100 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 cursor-pointer"
              >
                <option value="">— Не выбрано —</option>
                {field.options.map((opt) => (
                  <option key={opt} value={opt}>{opt}</option>
                ))}
              </select>
            )}
            {field.field_type === 'date' && (
              <input
                type="date"
                value={currentValue}
                onChange={(e) => handleChange(field.id, e.target.value)}
                className="w-full bg-white dark:bg-dark-900 border border-gray-300 dark:border-white/10 rounded-lg px-3 py-2 text-sm text-gray-900 dark:text-dark-100 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
              />
            )}
            {field.field_type === 'checkbox' && (
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={currentValue === 'true'}
                  onChange={(e) => handleChange(field.id, e.target.checked ? 'true' : 'false')}
                  className="w-4 h-4 rounded bg-white dark:bg-dark-900 border border-gray-300 dark:border-white/10"
                />
                <span className="text-sm text-gray-600 dark:text-dark-300">{currentValue === 'true' ? 'Да' : 'Нет'}</span>
              </label>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ============================================================
// MAIN MODAL
// ============================================================

export default function TaskDetailModal({
  isOpen,
  onClose,
  projectId,
  taskId,
  mode: modeProp,
  members,
  statuses = [],
  onTaskUpdated,
  onTaskDeleted,
  onTaskCreated,
  parentTaskId,
  scrollToCommentId,
}: TaskDetailModalProps) {
  const isCreateMode = modeProp === 'create' || !taskId;

  // ---- State ----
  const [task, setTask] = useState<ProjectTask | null>(null);
  const [loading, setLoading] = useState(!isCreateMode);
  const [saving, setSaving] = useState(false);
  const [activeTab, setActiveTab] = useState<ModalTab>('description');
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  // Editable fields
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [status, setStatus] = useState(statuses.find(s => s.is_default)?.slug || statuses[0]?.slug || 'backlog');
  const [priority, setPriority] = useState(1);
  const [assigneeId, setAssigneeId] = useState<number | ''>('');
  const [dueDate, setDueDate] = useState('');
  const [estimatedHours, setEstimatedHours] = useState('');
  const [tags, setTags] = useState<string[]>([]);
  const [isEditingTitle, setIsEditingTitle] = useState(isCreateMode);
  const titleInputRef = useRef<HTMLInputElement>(null);

  // ---- Reset for create mode ----
  useEffect(() => {
    if (!isOpen || !isCreateMode) return;
    setTask(null);
    setTitle('');
    setDescription('');
    setStatus(statuses.find(s => s.is_default)?.slug || statuses[0]?.slug || 'backlog');
    setPriority(1);
    setAssigneeId('');
    setDueDate('');
    setEstimatedHours('');
    setTags([]);
    setLoading(false);
    setActiveTab('description');
    setShowDeleteConfirm(false);
    setIsEditingTitle(true);
  }, [isOpen, isCreateMode]);

  // ---- Load task data ----
  useEffect(() => {
    if (!isOpen || !taskId || isCreateMode) return;
    setLoading(true);
    // Если пришли по deep-link из notification к коментарию — открываем
    // сразу вкладку 'Комментарии', иначе обычный дефолт.
    setActiveTab(scrollToCommentId ? 'comments' : 'description');
    setShowDeleteConfirm(false);

    const loadTask = async () => {
      try {
        const tasks = await api.getProjectTasks(projectId);
        const found = tasks.find((t) => t.id === taskId);
        if (found) {
          setTask(found);
          setTitle(found.title);
          setDescription(found.description || '');
          setStatus(found.status);
          setPriority(found.priority);
          setAssigneeId(found.assignee_id || '');
          setDueDate(found.due_date || '');
          setEstimatedHours(found.estimated_hours != null ? String(found.estimated_hours) : '');
          setTags(found.tags || []);
        } else {
          toast.error('Задача не найдена');
          onClose();
        }
      } catch {
        toast.error('Не удалось загрузить задачу');
        onClose();
      } finally {
        setLoading(false);
      }
    };

    loadTask();
  }, [isOpen, taskId, projectId, onClose, scrollToCommentId]);

  // Focus title input when editing
  useEffect(() => {
    if (isEditingTitle && titleInputRef.current) {
      titleInputRef.current.focus();
      titleInputRef.current.select();
    }
  }, [isEditingTitle]);

  // ---- Handlers ----
  const handleSave = async () => {
    setSaving(true);
    try {
      if (isCreateMode) {
        // CREATE new task
        if (!title.trim()) {
          toast.error('Введите название задачи');
          setSaving(false);
          return;
        }
        const newTask = await api.createProjectTask(projectId, {
          title: title.trim(),
          description: description || undefined,
          status: status || undefined,
          priority,
          assignee_id: assigneeId || undefined,
          due_date: dueDate || undefined,
          estimated_hours: estimatedHours ? Number(estimatedHours) : undefined,
          tags,
          parent_task_id: parentTaskId,
        });
        toast.success('Задача создана');
        onTaskCreated?.(newTask);
        onTaskUpdated?.();
        onClose();
      } else {
        // UPDATE existing task
        if (!task) return;
        await api.updateProjectTask(projectId, task.id, {
          title: title.trim() || task.title,
          description: description || undefined,
          status: status || undefined,
          priority,
          assignee_id: assigneeId || undefined,
          due_date: dueDate || undefined,
          estimated_hours: estimatedHours ? Number(estimatedHours) : undefined,
          tags,
        });
        toast.success('Задача обновлена');
        onTaskUpdated?.();
      }
    } catch (err) {
      toast.error(getErrorDetail(err, isCreateMode ? 'Не удалось создать задачу' : 'Не удалось сохранить изменения'));
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!task) return;
    try {
      await api.deleteProjectTask(projectId, task.id);
      toast.success('Задача удалена');
      onTaskDeleted?.();
    } catch (err) {
      toast.error(getErrorDetail(err, 'Не удалось удалить задачу'));
    }
  };

  // ESC to close
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    if (isOpen) window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [isOpen, onClose]);

  // ---- Helpers ----
  const getStatusLabel = (slug: string): string => {
    const st = statuses.find((s) => s.slug === slug);
    return st?.name || DEFAULT_STATUS_LABELS[slug] || slug;
  };

  const getStatusColor = (slug: string): string | undefined => {
    return statuses.find((s) => s.slug === slug)?.color;
  };

  const statusOptions = statuses.length > 0
    ? statuses.map((s) => ({ value: s.slug, label: s.name, color: s.color }))
    : Object.entries(DEFAULT_STATUS_LABELS).map(([value, label]) => ({ value, label, color: undefined }));

  // ---- Render ----
  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
          className="fixed inset-0 z-50 flex items-start justify-center bg-black/50 p-4 pt-[5vh] overflow-y-auto"
          {...backdropClose(onClose)}
        >
          <motion.div
            initial={{ scale: 0.95, opacity: 0, y: 20 }}
            animate={{ scale: 1, opacity: 1, y: 0 }}
            exit={{ scale: 0.95, opacity: 0, y: 20 }}
            transition={{ duration: 0.2 }}
            className="bg-white dark:bg-dark-900 rounded-2xl shadow-2xl w-full max-w-5xl relative"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Loading state */}
            {loading ? (
              <div className="flex items-center justify-center py-32">
                <Loader2 className="w-8 h-8 text-gray-300 animate-spin" />
              </div>
            ) : (task || isCreateMode) ? (
              <>
                {/* ========== HEADER ========== */}
                <div className="flex items-start justify-between gap-4 p-6 pb-4 border-b border-gray-200 dark:border-white/[0.08]">
                  <div className="flex-1 min-w-0">
                    {/* Title */}
                    {isEditingTitle || isCreateMode ? (
                      <input
                        ref={titleInputRef}
                        value={title}
                        onChange={(e) => setTitle(e.target.value)}
                        onBlur={() => !isCreateMode && setIsEditingTitle(false)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' && !isCreateMode) setIsEditingTitle(false);
                          if (e.key === 'Escape' && !isCreateMode) {
                            setTitle(task?.title || '');
                            setIsEditingTitle(false);
                          }
                        }}
                        placeholder={isCreateMode ? 'Название задачи...' : undefined}
                        className="w-full text-xl font-bold text-gray-900 dark:text-dark-100 bg-transparent border-b-2 border-blue-500 pb-1 focus:outline-none placeholder-gray-400 dark:placeholder-dark-500"
                        autoFocus={isCreateMode}
                      />
                    ) : (
                      <h2
                        className="text-xl font-bold text-gray-900 dark:text-dark-100 cursor-pointer hover:text-gray-600 dark:text-dark-300 transition-colors truncate"
                        onClick={() => setIsEditingTitle(true)}
                        title="Нажмите для редактирования"
                      >
                        {title || task?.title || 'Без названия'}
                      </h2>
                    )}

                    {/* Status + Priority badges */}
                    <div className="flex items-center gap-2 mt-2">
                      {(() => {
                        const dotColor = getStatusColor(status);
                        return dotColor ? (
                          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 text-xs font-medium rounded-lg border border-gray-200 dark:border-white/[0.08] text-gray-700 dark:text-dark-200">
                            <span className="w-2 h-2 rounded-full" style={{ backgroundColor: dotColor }} />
                            {getStatusLabel(status)}
                          </span>
                        ) : (
                          <span className="inline-flex items-center px-2.5 py-0.5 text-xs font-medium rounded-lg border bg-gray-100 dark:bg-dark-800 text-gray-600 dark:text-dark-300 border-gray-200 dark:border-white/[0.08]">
                            {getStatusLabel(status)}
                          </span>
                        );
                      })()}
                      <span className={clsx('inline-flex items-center gap-1 px-2.5 py-0.5 text-xs font-medium rounded-lg border', PRIORITY_COLORS[priority] || PRIORITY_COLORS[1])}>
                        <Flag className="w-3 h-3" />
                        {PRIORITY_LABELS[priority] ?? 'Нормальный'}
                      </span>
                      {task?.parent_task_id && (
                        <span className="text-[10px] text-gray-400 dark:text-dark-500">Подзадача</span>
                      )}
                    </div>
                  </div>

                  {/* Close button */}
                  <button
                    onClick={onClose}
                    className="p-2 text-gray-400 dark:text-dark-500 hover:text-gray-600 dark:text-dark-300 hover:bg-gray-100 dark:hover:bg-dark-800 dark:bg-dark-800 rounded-xl transition-colors flex-shrink-0"
                  >
                    <X className="w-5 h-5" />
                  </button>
                </div>

                {/* ========== BODY: LEFT + RIGHT ========== */}
                <div className="flex flex-col lg:flex-row">
                  {/* ---- LEFT: TABS ---- */}
                  <div className="flex-1 min-w-0 p-6 border-r border-gray-200 dark:border-white/[0.08]">
                    {/* Tab buttons */}
                    <div className="flex gap-1 mb-5 bg-gray-100 dark:bg-dark-800 rounded-xl p-1 border border-gray-200 dark:border-white/[0.08] overflow-x-auto">
                      {(isCreateMode ? TABS.filter(t => t.id === 'description') : TABS).map((tab) => (
                        <button
                          key={tab.id}
                          onClick={() => setActiveTab(tab.id)}
                          className={clsx(
                            'flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg transition-all whitespace-nowrap',
                            activeTab === tab.id
                              ? 'bg-white dark:bg-dark-900 text-gray-900 dark:text-dark-100 shadow-sm'
                              : 'text-gray-500 dark:text-dark-400 hover:text-gray-700 dark:hover:text-dark-200 dark:text-dark-200'
                          )}
                        >
                          {tab.icon}
                          {tab.label}
                          {tab.id === 'comments' && (task?.comment_count || 0) > 0 && (
                            <span className="text-[10px] text-gray-400 dark:text-dark-500">{task?.comment_count}</span>
                          )}
                          {tab.id === 'attachments' && (task?.attachment_count || 0) > 0 && (
                            <span className="text-[10px] text-gray-400 dark:text-dark-500">{task?.attachment_count}</span>
                          )}
                          {tab.id === 'subtasks' && (task?.subtask_count || 0) > 0 && (
                            <span className="text-[10px] text-gray-400 dark:text-dark-500">{task?.subtask_count}</span>
                          )}
                        </button>
                      ))}
                    </div>

                    {/* Tab content */}
                    <AnimatePresence mode="wait">
                      <motion.div
                        key={activeTab}
                        initial={{ opacity: 0, y: 5 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -5 }}
                        transition={{ duration: 0.15 }}
                      >
                        {activeTab === 'description' && (
                          <DescriptionTab
                            description={description}
                            tags={tags}
                            onDescriptionChange={setDescription}
                            onTagsChange={setTags}
                          />
                        )}
                        {activeTab === 'comments' && task && (
                          <CommentsTab projectId={projectId} taskId={task.id} members={members} scrollToCommentId={scrollToCommentId} />
                        )}
                        {activeTab === 'attachments' && task && (
                          <AttachmentsTab projectId={projectId} taskId={task.id} />
                        )}
                        {activeTab === 'subtasks' && task && (
                          <SubtasksTab
                            projectId={projectId}
                            taskId={task.id}
                            members={members}
                            statuses={statuses}
                          />
                        )}
                        {activeTab === 'custom_fields' && task && (
                          <CustomFieldsTab projectId={projectId} taskId={task.id} />
                        )}
                      </motion.div>
                    </AnimatePresence>
                  </div>

                  {/* ---- RIGHT: SIDEBAR ---- */}
                  <div className="lg:w-[300px] flex-shrink-0 p-6 space-y-5 bg-gray-50 dark:bg-dark-800">
                    {/* Status */}
                    <div>
                      <label className="flex items-center gap-1.5 text-xs font-medium text-gray-500 dark:text-dark-400 uppercase tracking-wider mb-1.5">
                        <Check className="w-3.5 h-3.5" />
                        Статус
                      </label>
                      <select
                        value={status}
                        onChange={(e) => setStatus(e.target.value)}
                        className="w-full bg-white dark:bg-dark-900 border border-gray-300 dark:border-white/10 rounded-lg px-3 py-2 text-sm text-gray-900 dark:text-dark-100 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 cursor-pointer"
                      >
                        {statusOptions.map((opt) => (
                          <option key={opt.value} value={opt.value}>{opt.label}</option>
                        ))}
                      </select>
                    </div>

                    {/* Assignee */}
                    <div>
                      <label className="flex items-center gap-1.5 text-xs font-medium text-gray-500 dark:text-dark-400 uppercase tracking-wider mb-1.5">
                        <User className="w-3.5 h-3.5" />
                        Исполнитель
                      </label>
                      <select
                        value={assigneeId}
                        onChange={(e) => setAssigneeId(e.target.value ? Number(e.target.value) : '')}
                        className="w-full bg-white dark:bg-dark-900 border border-gray-300 dark:border-white/10 rounded-lg px-3 py-2 text-sm text-gray-900 dark:text-dark-100 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 cursor-pointer"
                      >
                        <option value="">Не назначен</option>
                        {members.map((m) => (
                          <option key={m.user_id} value={m.user_id}>
                            {m.user_name || m.user_email || `User ${m.user_id}`}
                          </option>
                        ))}
                      </select>
                    </div>

                    {/* Priority */}
                    <div>
                      <label className="flex items-center gap-1.5 text-xs font-medium text-gray-500 dark:text-dark-400 uppercase tracking-wider mb-1.5">
                        <Flag className="w-3.5 h-3.5" />
                        Приоритет
                      </label>
                      <select
                        value={priority}
                        onChange={(e) => setPriority(Number(e.target.value))}
                        className="w-full bg-white dark:bg-dark-900 border border-gray-300 dark:border-white/10 rounded-lg px-3 py-2 text-sm text-gray-900 dark:text-dark-100 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 cursor-pointer"
                      >
                        {Object.entries(PRIORITY_LABELS).map(([val, label]) => (
                          <option key={val} value={val}>{label}</option>
                        ))}
                      </select>
                    </div>

                    {/* Due date */}
                    <div>
                      <label className="flex items-center gap-1.5 text-xs font-medium text-gray-500 dark:text-dark-400 uppercase tracking-wider mb-1.5">
                        <Calendar className="w-3.5 h-3.5" />
                        Дедлайн
                      </label>
                      <input
                        type="date"
                        value={dueDate ? dueDate.slice(0, 10) : ''}
                        min={new Date().toISOString().slice(0, 10)}
                        onChange={(e) => setDueDate(e.target.value)}
                        className="w-full bg-white dark:bg-dark-900 border border-gray-300 dark:border-white/10 rounded-lg px-3 py-2 text-sm text-gray-900 dark:text-dark-100 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
                      />
                    </div>

                    {/* Estimated hours */}
                    <div>
                      <label className="flex items-center gap-1.5 text-xs font-medium text-gray-500 dark:text-dark-400 uppercase tracking-wider mb-1.5">
                        <Clock className="w-3.5 h-3.5" />
                        Оценка (часы)
                      </label>
                      <input
                        type="number"
                        min="0"
                        step="0.5"
                        value={estimatedHours}
                        onChange={(e) => setEstimatedHours(e.target.value)}
                        placeholder="0"
                        className="w-full bg-white dark:bg-dark-900 border border-gray-300 dark:border-white/10 rounded-lg px-3 py-2 text-sm text-gray-900 dark:text-dark-100 placeholder-gray-400 dark:placeholder-dark-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
                      />
                    </div>

                    {/* Divider */}
                    {!isCreateMode && task && (
                      <div className="border-t border-gray-200 dark:border-white/[0.08] pt-4 space-y-3">
                        {task.task_key && (
                          <div>
                            <span className="text-[10px] text-gray-400 dark:text-dark-500 uppercase tracking-wider">ID</span>
                            <p className="text-xs text-gray-600 dark:text-dark-300 mt-0.5 font-mono">{task.task_key}</p>
                          </div>
                        )}
                        <div>
                          <span className="text-[10px] text-gray-400 dark:text-dark-500 uppercase tracking-wider">Создал</span>
                          <p className="text-xs text-gray-500 dark:text-dark-400 mt-0.5">
                            {task.creator_name || (task.created_by ? `User ${task.created_by}` : '—')}
                          </p>
                        </div>
                        <div>
                          <span className="text-[10px] text-gray-400 dark:text-dark-500 uppercase tracking-wider">Создано</span>
                          <p className="text-xs text-gray-500 dark:text-dark-400 mt-0.5">{formatDate(task.created_at)}</p>
                        </div>
                        {task.updated_at && (
                          <div>
                            <span className="text-[10px] text-gray-400 dark:text-dark-500 uppercase tracking-wider">Обновлено</span>
                            <p className="text-xs text-gray-500 dark:text-dark-400 mt-0.5">{formatDateTime(task.updated_at)}</p>
                          </div>
                        )}
                        {task.total_hours_logged > 0 && (
                          <div>
                            <span className="text-[10px] text-gray-400 dark:text-dark-500 uppercase tracking-wider">Залогировано</span>
                            <p className="text-xs text-gray-500 dark:text-dark-400 mt-0.5">{task.total_hours_logged}ч</p>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>

                {/* ========== FOOTER ========== */}
                <div className="flex items-center justify-between px-6 py-4 border-t border-gray-200 dark:border-white/[0.08] bg-gray-50 dark:bg-dark-800 rounded-b-2xl">
                  {!isCreateMode ? (
                    <button
                      onClick={() => setShowDeleteConfirm(true)}
                      className="flex items-center gap-1.5 px-3 py-2 text-sm text-red-500 hover:text-red-700 hover:bg-red-50 rounded-xl transition-colors"
                    >
                      <Trash2 className="w-4 h-4" />
                      Удалить
                    </button>
                  ) : <div />}

                  <div className="flex items-center gap-3">
                    <button
                      onClick={onClose}
                      className="px-4 py-2 text-sm text-gray-600 dark:text-dark-300 hover:text-gray-900 dark:hover:text-dark-100 dark:text-dark-100 hover:bg-gray-200 rounded-lg transition-colors"
                    >
                      Отмена
                    </button>
                    <button
                      onClick={handleSave}
                      disabled={saving || (isCreateMode && !title.trim())}
                      className="flex items-center gap-2 px-5 py-2.5 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 disabled:opacity-50 rounded-lg transition-colors shadow-sm"
                    >
                      {saving ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <Save className="w-4 h-4" />
                      )}
                      {isCreateMode ? 'Создать' : 'Сохранить'}
                    </button>
                  </div>
                </div>

                {/* ========== DELETE CONFIRMATION ========== */}
                <AnimatePresence>
                  {showDeleteConfirm && (
                    <motion.div
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      className="absolute inset-0 z-10 flex items-center justify-center bg-black/30 rounded-2xl"
                      onClick={() => setShowDeleteConfirm(false)}
                    >
                      <motion.div
                        initial={{ scale: 0.95, opacity: 0 }}
                        animate={{ scale: 1, opacity: 1 }}
                        exit={{ scale: 0.95, opacity: 0 }}
                        className="bg-white dark:bg-dark-900 border border-gray-200 dark:border-white/[0.08] rounded-2xl p-6 w-full max-w-sm shadow-2xl"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <div className="flex items-center gap-3 mb-4">
                          <div className="p-2 rounded-xl bg-red-50">
                            <AlertTriangle className="w-5 h-5 text-red-600" />
                          </div>
                          <h3 className="text-lg font-semibold text-gray-900 dark:text-dark-100">Удалить задачу?</h3>
                        </div>
                        <p className="text-sm text-gray-600 dark:text-dark-300 mb-6">
                          Задача &laquo;{task?.title}&raquo; будет удалена безвозвратно.
                        </p>
                        <div className="flex justify-end gap-3">
                          <button
                            onClick={() => setShowDeleteConfirm(false)}
                            className="px-4 py-2 text-sm text-gray-600 dark:text-dark-300 hover:text-gray-900 dark:hover:text-dark-100 dark:text-dark-100 hover:bg-gray-100 dark:hover:bg-dark-800 dark:bg-dark-800 rounded-lg transition-colors"
                          >
                            Отмена
                          </button>
                          <button
                            onClick={handleDelete}
                            className="px-5 py-2.5 text-sm font-medium text-white bg-red-600 hover:bg-red-700 rounded-lg transition-colors shadow-sm"
                          >
                            Удалить
                          </button>
                        </div>
                      </motion.div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </>
            ) : null}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
