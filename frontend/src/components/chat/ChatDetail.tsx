import { useState, useRef, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import * as Tabs from '@radix-ui/react-tabs';
import {
  MessageSquare,
  Users,
  Settings,
  FileText,
  Download,
  Edit3,
  Check,
  X,
  File,
  Image,
  FileSpreadsheet,
  Presentation,
  Archive,
  Mail,
  CheckCircle,
  AlertTriangle,
  XCircle,
  ChevronDown,
  ChevronUp,
  UserCheck,
  FolderKanban,
  Building2,
  Briefcase,
  DollarSign,
  Headphones,
  MoreHorizontal,
  Trash2,
  Loader2,
  Upload,
  Link,
  Unlink
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import type { Chat, Message, ChatTypeId } from '@/types';
import { getMessages, getParticipants, updateChat, deleteChat, downloadReport } from '@/services/api';
import { useEntityStore } from '@/stores/entityStore';
import { useAuthStore } from '@/stores/authStore';
import CriteriaPanel from './CriteriaPanel';
import ImportHistoryModal from './ImportHistoryModal';
import toast from 'react-hot-toast';
import clsx from 'clsx';

// Cache for blob URLs to avoid re-fetching
// Stores blob URL on success, or FAILED_SENTINEL on error to prevent retry spam
const blobUrlCache = new Map<string, string>();
const FAILED_SENTINEL = '__FAILED__';

// Helper function to cleanup all blob URLs from cache
const cleanupBlobUrls = () => {
  blobUrlCache.forEach((url) => {
    if (url !== FAILED_SENTINEL) URL.revokeObjectURL(url);
  });
  blobUrlCache.clear();
};

// Helper to fetch file with auth header and return blob URL
const fetchWithAuth = async (url: string): Promise<string> => {
  // Check cache first
  const cached = blobUrlCache.get(url);
  if (cached === FAILED_SENTINEL) {
    throw new Error('Previously failed');
  }
  if (cached) {
    return cached;
  }

  const token = localStorage.getItem('token');
  const response = await fetch(url, {
    headers: token ? { 'Authorization': `Bearer ${token}` } : {},
    credentials: 'include',
  });

  if (!response.ok) {
    // Cache the failure to prevent retry spam (404/403 won't resolve on retry)
    if (response.status === 404 || response.status === 403) {
      blobUrlCache.set(url, FAILED_SENTINEL);
    }
    throw new Error(`HTTP ${response.status}`);
  }

  const blob = await response.blob();
  const blobUrl = URL.createObjectURL(blob);
  blobUrlCache.set(url, blobUrl);
  return blobUrl;
};

// Helper to get file URL (without token in query string)
const getFileUrl = (fileId: string) => {
  return `/api/chats/file/${fileId}`;
};

// Helper to get local file URL for imported media (without token in query string)
const getLocalFileUrl = (filePath: string) => {
  // filePath format: "uploads/{chat_id}/{filename}"
  // Convert to: "/api/chats/local/{chat_id}/{filename}"
  const parts = filePath.replace('uploads/', '').split('/');
  if (parts.length >= 2) {
    const chatId = parts[0];
    const filename = parts.slice(1).join('/');
    // URL-encode the filename to handle special characters like @, spaces, etc.
    const encodedFilename = encodeURIComponent(filename);
    return `/api/chats/local/${chatId}/${encodedFilename}`;
  }
  return '';
};

// Get media URL for a message (either from Telegram or local import)
const getMediaUrl = (message: { file_id?: string; file_path?: string }) => {
  if (message.file_id) {
    return getFileUrl(message.file_id);
  }
  if (message.file_path) {
    return getLocalFileUrl(message.file_path);
  }
  return '';
};

// Hook to fetch media with auth and return blob URL
const useAuthMedia = (url: string) => {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (!url) return;

    let cancelled = false;
    fetchWithAuth(url)
      .then((result) => {
        if (!cancelled) setBlobUrl(result);
      })
      .catch(() => {
        if (!cancelled) setError(true);
      });

    return () => { cancelled = true; };
  }, [url]);

  return { blobUrl, error };
};

// Authenticated Image component
const AuthImage = ({ src, alt, className, onClick }: {
  src: string;
  alt: string;
  className?: string;
  onClick?: () => void;
}) => {
  const { blobUrl, error } = useAuthMedia(src);

  if (error || !blobUrl) {
    return error ? (
      <div className="flex items-center gap-2 text-dark-400">
        <Image className="w-5 h-5" />
        <span className="text-sm">[Фото недоступно]</span>
      </div>
    ) : null;
  }

  return (
    <img
      src={blobUrl}
      alt={alt}
      className={className}
      onClick={onClick}
      loading="lazy"
    />
  );
};

// Authenticated Video component
const AuthVideo = ({ src, className, controls, preload, isRound }: {
  src: string;
  className?: string;
  controls?: boolean;
  preload?: string;
  isRound?: boolean;
}) => {
  const { blobUrl, error } = useAuthMedia(src);

  if (error) {
    return (
      <div
        className={isRound
          ? "w-32 h-32 rounded-full bg-dark-700 flex items-center justify-center text-dark-400"
          : "flex items-center gap-2 text-dark-400"
        }
      >
        <span className="text-sm">{isRound ? 'Видео' : '[Видео недоступно]'}</span>
      </div>
    );
  }

  if (!blobUrl) return null;

  return (
    <video
      src={blobUrl}
      className={className}
      controls={controls}
      preload={preload}
    />
  );
};

// Authenticated Audio component
const AuthAudio = ({ src, className }: {
  src: string;
  className?: string;
}) => {
  const { blobUrl, error } = useAuthMedia(src);

  if (error) {
    return (
      <div className="flex items-center gap-2 text-dark-400">
        <span className="text-sm">[Голосовое сообщение недоступно]</span>
      </div>
    );
  }

  if (!blobUrl) return null;

  return (
    <audio
      src={blobUrl}
      controls
      preload="metadata"
      className={className}
    />
  );
};

// Component to render text with clickable links
const TextWithLinks = ({ text, className }: { text: string; className?: string }) => {
  // URL regex pattern - matches http(s) URLs and www. URLs
  const urlPattern = /(https?:\/\/[^\s<>\"\']+|www\.[^\s<>\"\']+)/gi;

  const parts = text.split(urlPattern);

  return (
    <span className={className}>
      {parts.map((part, index) => {
        if (urlPattern.test(part)) {
          // Reset regex lastIndex after test
          urlPattern.lastIndex = 0;
          const href = part.startsWith('www.') ? `https://${part}` : part;
          return (
            <a
              key={index}
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="text-accent-400 hover:text-accent-300 hover:underline break-all"
              onClick={(e) => e.stopPropagation()}
            >
              {part}
            </a>
          );
        }
        return <span key={index}>{part}</span>;
      })}
    </span>
  );
};

// Chat type options
const CHAT_TYPES: { id: ChatTypeId; name: string; icon: typeof UserCheck }[] = [
  { id: 'work', name: 'Рабочий чат', icon: MessageSquare },
  { id: 'hr', name: 'HR / Кандидаты', icon: UserCheck },
  { id: 'project', name: 'Проект', icon: FolderKanban },
  { id: 'client', name: 'Клиент', icon: Building2 },
  { id: 'contractor', name: 'Подрядчик', icon: Briefcase },
  { id: 'sales', name: 'Продажи', icon: DollarSign },
  { id: 'support', name: 'Поддержка', icon: Headphones },
  { id: 'custom', name: 'Другое', icon: MoreHorizontal },
];

// File type icon mapping
const getFileIcon = (contentType: string, fileName?: string) => {
  const ext = fileName?.split('.').pop()?.toLowerCase();

  if (contentType === 'photo' || ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'heic'].includes(ext || '')) {
    return Image;
  }
  if (['xlsx', 'xls', 'csv', 'ods'].includes(ext || '')) {
    return FileSpreadsheet;
  }
  if (['pptx', 'ppt', 'odp'].includes(ext || '')) {
    return Presentation;
  }
  if (['zip', 'rar', '7z'].includes(ext || '')) {
    return Archive;
  }
  if (['eml', 'msg'].includes(ext || '')) {
    return Mail;
  }
  return FileText;
};

// Parse status badge
const ParseStatusBadge = ({ status, error }: { status?: string; error?: string }) => {
  if (!status) return null;

  const config = {
    parsed: { icon: CheckCircle, color: 'bg-green-500/20 text-green-400', label: 'Parsed' },
    partial: { icon: AlertTriangle, color: 'bg-yellow-500/20 text-yellow-400', label: 'Partial' },
    failed: { icon: XCircle, color: 'bg-red-500/20 text-red-400', label: 'Failed' },
    skipped: { icon: AlertTriangle, color: 'bg-gray-500/20 text-gray-400', label: 'Skipped' },
  }[status] || { icon: File, color: 'bg-gray-500/20 text-gray-400', label: status };

  const Icon = config.icon;

  return (
    <span
      className={clsx('inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs', config.color)}
      title={error}
    >
      <Icon className="w-3 h-3" />
      {config.label}
    </span>
  );
};

// Document message component
const DocumentMessage = ({ message }: { message: Message }) => {
  const [expanded, setExpanded] = useState(false);
  const FileIcon = getFileIcon(message.content_type, message.file_name);
  const meta = message.document_metadata;

  const preview = message.content.length > 300
    ? message.content.substring(0, 300) + '...'
    : message.content;

  const hasFullContent = message.content.length > 300;

  // Get download URL for the document
  const downloadUrl = message.file_id
    ? getFileUrl(message.file_id)
    : message.file_path
      ? getLocalFileUrl(message.file_path)
      : '';

  return (
    <div className="space-y-2">
      {/* Document header */}
      <div className="flex items-start gap-3 p-3 glass rounded-lg">
        <div className="p-2 rounded-lg bg-accent-500/20">
          <FileIcon className="w-5 h-5 text-accent-400" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap min-w-0">
            {downloadUrl ? (
              <a
                href={downloadUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="font-medium text-sm truncate text-accent-400 hover:underline min-w-0"
              >
                {message.file_name || 'Скачать файл'}
              </a>
            ) : (
              <span className="font-medium text-sm truncate min-w-0">{message.file_name || '[Файл]'}</span>
            )}
            {meta?.file_type && (
              <span className="px-2 py-0.5 rounded-full text-xs bg-dark-700 text-dark-300 uppercase flex-shrink-0">
                {meta.file_type}
              </span>
            )}
            <ParseStatusBadge status={message.parse_status} error={message.parse_error} />
          </div>
          {/* Metadata */}
          <div className="flex flex-wrap gap-3 mt-1 text-xs text-dark-500">
            {meta?.file_size && (
              <span>{(meta.file_size / 1024).toFixed(1)} KB</span>
            )}
            {meta?.pages_count && (
              <span>{meta.pages_count} pages</span>
            )}
            {meta?.sheets_count && (
              <span>{meta.sheets_count} sheets</span>
            )}
            {meta?.slides_count && (
              <span>{meta.slides_count} slides</span>
            )}
            {meta?.tables_count && meta.tables_count > 0 && (
              <span>{meta.tables_count} tables</span>
            )}
            {meta?.extracted_files && (
              <span>{meta.extracted_files.length} files</span>
            )}
          </div>
        </div>
      </div>

      {/* Content preview */}
      {message.parse_status === 'parsed' && message.content && !message.content.startsWith('[') && (
        <div className="pl-4 border-l-2 border-accent-500/30">
          <p className="text-sm text-dark-300 whitespace-pre-wrap">
            {expanded ? message.content : preview}
          </p>
          {hasFullContent && (
            <button
              onClick={() => setExpanded(!expanded)}
              className="flex items-center gap-1 mt-2 text-xs text-accent-400 hover:text-accent-300"
            >
              {expanded ? (
                <>
                  <ChevronUp className="w-3 h-3" />
                  Свернуть
                </>
              ) : (
                <>
                  <ChevronDown className="w-3 h-3" />
                  Показать полностью
                </>
              )}
            </button>
          )}
        </div>
      )}
    </div>
  );
};

interface ChatDetailProps {
  chat: Chat;
}

export default function ChatDetail({ chat }: ChatDetailProps) {
  const [activeTab, setActiveTab] = useState('messages');
  const [isEditing, setIsEditing] = useState(false);
  const [editName, setEditName] = useState(chat.custom_name || chat.title);
  const [showTypeDropdown, setShowTypeDropdown] = useState(false);
  const [showEntityDropdown, setShowEntityDropdown] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [showImportModal, setShowImportModal] = useState(false);
  const [downloadingReport, setDownloadingReport] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const messagesContainerRef = useRef<HTMLDivElement>(null);

  const { user } = useAuthStore();
  // Entity store for linking
  const { entities, fetchEntities } = useEntityStore();

  // Helper to check permissions using authStore
  const { canDeleteResource, canEditResource } = useAuthStore();
  const canDelete = () => {
    return canDeleteResource({
      owner_id: chat.owner_id,
      is_mine: chat.is_mine ?? (chat.owner_id === user?.id),
      access_level: chat.access_level ?? undefined
    });
  };
  const canEdit = () => {
    return canEditResource({
      owner_id: chat.owner_id,
      is_mine: chat.is_mine ?? (chat.owner_id === user?.id),
      access_level: chat.access_level ?? undefined
    });
  };

  // Fetch entities when dropdown opens
  useEffect(() => {
    if (showEntityDropdown && entities.length === 0) {
      fetchEntities();
    }
  }, [showEntityDropdown, entities.length, fetchEntities]);

  const { data: messages = [], isLoading: loadingMessages } = useQuery({
    queryKey: ['messages', chat.id],
    queryFn: () => getMessages(chat.id),
  });

  const { data: participants = [], isLoading: loadingParticipants } = useQuery({
    queryKey: ['participants', chat.id],
    queryFn: () => getParticipants(chat.id),
  });

  // Scroll to bottom when messages load
  useEffect(() => {
    if (messages.length > 0 && messagesContainerRef.current) {
      messagesContainerRef.current.scrollTop = messagesContainerRef.current.scrollHeight;
    }
  }, [messages]);

  // Cleanup blob URLs on unmount to prevent memory leaks
  useEffect(() => {
    return () => {
      cleanupBlobUrls();
    };
  }, []);

  const updateNameMutation = useMutation({
    mutationFn: (name: string) => updateChat(chat.id, { custom_name: name }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['chats'] });
      queryClient.invalidateQueries({ queryKey: ['stats'] });
      setIsEditing(false);
      toast.success('Название обновлено');
    },
  });

  const updateTypeMutation = useMutation({
    mutationFn: (chatType: ChatTypeId) => updateChat(chat.id, { chat_type: chatType }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['chats'] });
      setShowTypeDropdown(false);
      toast.success('Тип чата изменён');
    },
  });

  const updateEntityMutation = useMutation({
    mutationFn: (entityId: number | null) => updateChat(chat.id, { entity_id: entityId === null ? -1 : entityId }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['chats'] });
      setShowEntityDropdown(false);
      toast.success('Контакт привязан');
    },
  });

  const deleteChatMutation = useMutation({
    mutationFn: () => deleteChat(chat.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['chats'] });
      toast.success('Чат удалён');
      navigate('/chats');
    },
    onError: () => {
      toast.error('Ошибка удаления чата');
    },
  });

  const handleDownloadReport = async (format: string) => {
    if (downloadingReport) return;

    setDownloadingReport(format);
    try {
      const blob = await downloadReport(chat.id, 'full_analysis', format);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `report_${chat.id}.${format}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      toast.success('Отчёт скачан');
    } catch (e) {
      console.error('downloadReport failed:', e);
      const msg = e instanceof Error ? e.message : '';
      toast.error(msg.includes('403') ? 'Нет доступа к отчёту' : 'Ошибка скачивания');
    } finally {
      setDownloadingReport(null);
    }
  };

  const formatTime = (dateString: string) => {
    // Ensure timestamp is parsed as UTC
    const utcDate = dateString.endsWith('Z') ? dateString : dateString + 'Z';
    const date = new Date(utcDate);
    return date.toLocaleString('ru-RU', {
      day: '2-digit',
      month: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const tabs = [
    { id: 'messages', label: 'Сообщения', icon: MessageSquare },
    { id: 'participants', label: 'Участники', icon: Users },
    { id: 'criteria', label: 'Критерии', icon: Settings },
    { id: 'reports', label: 'Отчёты', icon: FileText },
  ];

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Header */}
      <div className="p-4 border-b border-white/5 hidden lg:block">
        <div className="flex items-center gap-3">
          {isEditing ? (
            <div className="flex items-center gap-2 flex-1">
              <input
                type="text"
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
                className="flex-1 glass-light rounded-lg px-3 py-1.5 text-lg font-semibold focus:outline-none focus:ring-2 focus:ring-accent-500/50"
                autoFocus
              />
              <button
                onClick={() => updateNameMutation.mutate(editName)}
                className="p-2 rounded-lg bg-green-500/20 text-green-400 hover:bg-green-500/30"
              >
                <Check className="w-4 h-4" />
              </button>
              <button
                onClick={() => {
                  setIsEditing(false);
                  setEditName(chat.custom_name || chat.title);
                }}
                className="p-2 rounded-lg bg-red-500/20 text-red-400 hover:bg-red-500/30"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          ) : (
            <>
              <h2 className="text-xl font-semibold flex-1 truncate">
                {chat.custom_name || chat.title}
              </h2>
              {canEdit() && (
                <button
                  onClick={() => setIsEditing(true)}
                  className="p-2 rounded-lg hover:bg-dark-800/50 text-dark-400 hover:text-dark-200"
                >
                  <Edit3 className="w-4 h-4" />
                </button>
              )}
            </>
          )}
        </div>
        <div className="flex items-center gap-3 mt-2 flex-wrap">
          <p className="text-sm text-dark-400 flex-shrink-0">
            {chat.messages_count} сообщ. | {chat.participants_count} участн.
          </p>

          {/* Chat Type Selector - editable only for users with edit permission */}
          <div className="relative">
            <button
              onClick={() => canEdit() && setShowTypeDropdown(!showTypeDropdown)}
              className={clsx(
                'flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium bg-accent-500/20 text-accent-400 transition-colors',
                canEdit() ? 'hover:bg-accent-500/30 cursor-pointer' : 'cursor-default'
              )}
            >
              {(() => {
                const typeInfo = CHAT_TYPES.find(t => t.id === chat.chat_type);
                const Icon = typeInfo?.icon || MoreHorizontal;
                return (
                  <>
                    <Icon className="w-3.5 h-3.5" />
                    {typeInfo?.name || chat.chat_type}
                    {canEdit() && <ChevronDown className="w-3 h-3" />}
                  </>
                );
              })()}
            </button>

            {showTypeDropdown && canEdit() && (
              <div className="absolute top-full left-0 mt-1 w-48 glass rounded-xl border border-white/10 shadow-xl z-50 overflow-hidden">
                {CHAT_TYPES.map((type) => {
                  const Icon = type.icon;
                  const isActive = chat.chat_type === type.id;
                  return (
                    <button
                      key={type.id}
                      onClick={() => updateTypeMutation.mutate(type.id)}
                      disabled={updateTypeMutation.isPending}
                      className={clsx(
                        'w-full flex items-center gap-2 px-3 py-2 text-sm text-left transition-colors',
                        isActive
                          ? 'bg-accent-500/20 text-accent-400'
                          : 'text-dark-200 hover:bg-dark-800/50'
                      )}
                    >
                      <Icon className="w-4 h-4" />
                      {type.name}
                      {isActive && <Check className="w-3.5 h-3.5 ml-auto" />}
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          {/* Entity Selector - editable only for users with edit permission */}
          <div className="relative">
            <button
              onClick={() => canEdit() && setShowEntityDropdown(!showEntityDropdown)}
              className={clsx(
                'flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium transition-colors',
                chat.entity_id
                  ? 'bg-green-500/20 text-green-400'
                  : 'bg-purple-500/20 text-purple-400',
                canEdit()
                  ? (chat.entity_id ? 'hover:bg-green-500/30' : 'hover:bg-purple-500/30') + ' cursor-pointer'
                  : 'cursor-default'
              )}
            >
              {chat.entity_id ? (
                <>
                  <Link className="w-3.5 h-3.5" />
                  {chat.entity_name || 'Контакт'}
                </>
              ) : canEdit() ? (
                <>
                  <Unlink className="w-3.5 h-3.5" />
                  Привязать
                </>
              ) : null}
              {canEdit() && <ChevronDown className="w-3 h-3" />}
            </button>

            {showEntityDropdown && canEdit() && (
              <div className="absolute top-full left-0 mt-1 w-56 glass rounded-xl border border-white/10 shadow-xl z-50 overflow-hidden max-h-64 overflow-y-auto">
                {/* Unlink option */}
                {chat.entity_id && (
                  <button
                    onClick={() => updateEntityMutation.mutate(null)}
                    disabled={updateEntityMutation.isPending}
                    className="w-full flex items-center gap-2 px-3 py-2 text-sm text-left text-red-400 hover:bg-red-500/10 transition-colors border-b border-white/5"
                  >
                    <Unlink className="w-4 h-4" />
                    Отвязать контакт
                  </button>
                )}
                {entities.length === 0 ? (
                  <div className="px-3 py-4 text-sm text-dark-400 text-center">
                    <Loader2 className="w-4 h-4 animate-spin mx-auto mb-2" />
                    Загрузка...
                  </div>
                ) : (
                  entities.map((entity) => {
                    const isActive = chat.entity_id === entity.id;
                    return (
                      <button
                        key={entity.id}
                        onClick={() => updateEntityMutation.mutate(entity.id)}
                        disabled={updateEntityMutation.isPending}
                        className={clsx(
                          'w-full flex items-center gap-2 px-3 py-2 text-sm text-left transition-colors',
                          isActive
                            ? 'bg-green-500/20 text-green-400'
                            : 'text-dark-200 hover:bg-dark-800/50'
                        )}
                      >
                        <UserCheck className="w-4 h-4 flex-shrink-0" />
                        <div className="flex-1 min-w-0">
                          <div className="truncate">{entity.name}</div>
                          <div className="text-xs text-dark-500 truncate">{entity.type}</div>
                        </div>
                        {isActive && <Check className="w-3.5 h-3.5 flex-shrink-0" />}
                      </button>
                    );
                  })
                )}
              </div>
            )}
          </div>

          {/* Import History Button */}
          <button
            onClick={() => setShowImportModal(true)}
            className="p-1.5 rounded-lg text-dark-400 hover:text-accent-400 hover:bg-accent-500/10 transition-colors"
            title="Загрузить историю"
          >
            <Upload className="w-4 h-4" />
          </button>

          {/* Delete Button */}
          {canDelete() && (
            <button
              onClick={() => setShowDeleteConfirm(true)}
              className="p-1.5 rounded-lg text-dark-400 hover:text-red-400 hover:bg-red-500/10 transition-colors"
              title="Удалить чат"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      {/* Delete Confirmation Modal */}
      {showDeleteConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-dark-950/80">
          <div className="glass rounded-2xl max-w-sm w-full p-6 space-y-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-red-500/20 flex items-center justify-center">
                <Trash2 className="w-5 h-5 text-red-400" />
              </div>
              <div>
                <h3 className="font-semibold">Удалить чат?</h3>
                <p className="text-sm text-dark-400">Это действие необратимо</p>
              </div>
            </div>
            <p className="text-sm text-dark-300">
              Будут удалены все сообщения, участники и критерии оценки для чата "{chat.custom_name || chat.title}".
            </p>
            <div className="flex gap-3">
              <button
                onClick={() => setShowDeleteConfirm(false)}
                className="flex-1 py-2 rounded-xl glass-light hover:bg-white/10 text-sm font-medium transition-colors"
              >
                Отмена
              </button>
              <button
                onClick={() => deleteChatMutation.mutate()}
                disabled={deleteChatMutation.isPending}
                className="flex-1 py-2 rounded-xl bg-red-500 text-white text-sm font-medium hover:bg-red-600 disabled:opacity-50 transition-colors"
              >
                {deleteChatMutation.isPending ? 'Удаление...' : 'Удалить'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Tabs */}
      <Tabs.Root value={activeTab} onValueChange={setActiveTab} className="flex-1 flex flex-col overflow-hidden">
        <Tabs.List className="flex border-b border-white/5 px-4 overflow-x-auto scrollbar-none">
          {tabs.map((tab) => (
            <Tabs.Trigger
              key={tab.id}
              value={tab.id}
              className={clsx(
                'flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors',
                activeTab === tab.id
                  ? 'border-accent-500 text-accent-400'
                  : 'border-transparent text-dark-400 hover:text-dark-200'
              )}
            >
              <tab.icon className="w-4 h-4" />
              <span className="hidden sm:inline">{tab.label}</span>
            </Tabs.Trigger>
          ))}
        </Tabs.List>

        {/* Messages Tab */}
        <Tabs.Content value="messages" ref={messagesContainerRef} className="flex-1 overflow-y-auto p-4">
          {loadingMessages ? (
            <div className="flex items-center justify-center py-8">
              <div className="w-6 h-6 border-2 border-accent-500 border-t-transparent rounded-full animate-spin" />
            </div>
          ) : messages.length === 0 ? (
            <div className="text-center py-8">
              <MessageSquare className="w-12 h-12 mx-auto text-dark-600 mb-3" />
              <p className="text-dark-400">Сообщений пока нет</p>
            </div>
          ) : (
            <div className="space-y-3">
              {messages.map((message, index) => {
                // Only treat actual documents as documents (not photos/stickers/video notes)
                const isDocument = message.content_type === 'document' ||
                  (message.document_metadata && !['photo', 'sticker', 'video_note'].includes(message.content_type));

                return (
                  <motion.div
                    key={message.id}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: index * 0.02 }}
                    className="glass-light rounded-xl p-3 max-w-full"
                  >
                    <div className="flex items-center gap-2 mb-2">
                      <div className="w-8 h-8 rounded-full bg-accent-500/20 flex items-center justify-center text-xs font-medium text-accent-400">
                        {(message.first_name?.[0] || message.username?.[0] || '?').toUpperCase()}
                      </div>
                      <div className="flex-1 min-w-0">
                        <span className="font-medium text-sm">
                          {message.first_name || message.username || 'Unknown'}
                        </span>
                        {message.username && message.first_name && (
                          <span className="text-dark-500 text-xs ml-1">@{message.username}</span>
                        )}
                      </div>
                      <span className="text-xs text-dark-500">{formatTime(message.timestamp)}</span>
                    </div>

                    {isDocument ? (
                      <DocumentMessage message={message} />
                    ) : message.content_type === 'photo' ? (
                      <div className="space-y-2">
                        {(message.file_id || message.file_path) ? (
                          <AuthImage
                            src={getMediaUrl(message)}
                            alt="Photo"
                            className="max-w-xs max-w-full rounded-lg cursor-pointer hover:opacity-90 transition-opacity"
                            onClick={() => {
                              // Open in new tab with fetch
                              const url = getMediaUrl(message);
                              fetchWithAuth(url).then(blobUrl => window.open(blobUrl, '_blank'));
                            }}
                          />
                        ) : (
                          <div className="flex items-center gap-2 text-dark-400">
                            <Image className="w-5 h-5" />
                            <span className="text-sm">[Фото недоступно]</span>
                          </div>
                        )}
                        {message.content && !message.content.startsWith('[Photo') && !message.content.startsWith('[Фото') && (
                          <p className="text-sm text-dark-300"><TextWithLinks text={message.content} /></p>
                        )}
                      </div>
                    ) : message.content_type === 'video_note' ? (
                      <div className="space-y-2">
                        {(message.file_id || message.file_path) ? (
                          <AuthVideo
                            src={getMediaUrl(message)}
                            className="w-32 h-32 rounded-full object-cover cursor-pointer"
                            controls
                            preload="metadata"
                            isRound
                          />
                        ) : (
                          <div className="w-32 h-32 rounded-full bg-dark-700 flex items-center justify-center text-dark-400">
                            <span className="text-xs">Видео</span>
                          </div>
                        )}
                        {message.content && !message.content.startsWith('[Video') && !message.content.startsWith('[Видео') && !message.content.includes('transcription failed') && (
                          <p className="text-sm text-dark-300"><TextWithLinks text={message.content} /></p>
                        )}
                      </div>
                    ) : message.content_type === 'sticker' ? (
                      <div className="flex items-center gap-2">
                        {(message.file_id || message.file_path) && (
                          <AuthImage
                            src={getMediaUrl(message)}
                            alt="Sticker"
                            className="w-32 h-32 object-contain"
                          />
                        )}
                        {message.content.includes('[Sticker') || message.content.includes('[Стикер') ? (
                          <span className="text-2xl">{message.content.replace('[Sticker: ', '').replace('[Стикер]', '').replace(']', '')}</span>
                        ) : (
                          <span className="text-2xl">{message.content}</span>
                        )}
                      </div>
                    ) : message.content_type === 'voice' ? (
                      <div className="space-y-2">
                        {(message.file_id || message.file_path) ? (
                          <AuthAudio
                            src={getMediaUrl(message)}
                            className="w-full max-w-xs max-w-full"
                          />
                        ) : (
                          <div className="flex items-center gap-2 text-dark-400">
                            <span className="text-sm">[Голосовое сообщение недоступно]</span>
                          </div>
                        )}
                        {message.content && !message.content.startsWith('[Голосов') && !message.content.startsWith('[Voice') && (
                          <p className="text-sm text-dark-300"><TextWithLinks text={message.content} /></p>
                        )}
                      </div>
                    ) : message.content_type === 'video' ? (
                      <div className="space-y-2">
                        {(message.file_id || message.file_path) ? (
                          <AuthVideo
                            src={getMediaUrl(message)}
                            className="max-w-xs max-w-full rounded-lg"
                            controls
                            preload="metadata"
                          />
                        ) : (
                          <div className="flex items-center gap-2 text-dark-400">
                            <span className="text-sm">[Видео недоступно]</span>
                          </div>
                        )}
                        {message.content && !message.content.startsWith('[Видео') && !message.content.startsWith('[Video') && (
                          <p className="text-sm text-dark-300"><TextWithLinks text={message.content} /></p>
                        )}
                      </div>
                    ) : (
                      <>
                        <p className="text-sm text-dark-200 whitespace-pre-wrap break-words"><TextWithLinks text={message.content} /></p>
                        {message.content_type !== 'text' && (
                          <span className="inline-block mt-2 text-xs px-2 py-0.5 rounded-full bg-dark-700 text-dark-400">
                            {message.content_type}
                          </span>
                        )}
                      </>
                    )}
                  </motion.div>
                );
              })}
            </div>
          )}
        </Tabs.Content>

        {/* Participants Tab */}
        <Tabs.Content value="participants" className="flex-1 overflow-y-auto p-4">
          {loadingParticipants ? (
            <div className="flex items-center justify-center py-8">
              <div className="w-6 h-6 border-2 border-accent-500 border-t-transparent rounded-full animate-spin" />
            </div>
          ) : participants.length === 0 ? (
            <div className="text-center py-8">
              <Users className="w-12 h-12 mx-auto text-dark-600 mb-3" />
              <p className="text-dark-400">Участников пока нет</p>
            </div>
          ) : (
            <div className="space-y-2">
              {participants.map((participant, index) => (
                <motion.div
                  key={participant.telegram_user_id}
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: index * 0.05 }}
                  className="flex items-center gap-3 glass-light rounded-xl p-3"
                >
                  <div className="w-10 h-10 rounded-full bg-gradient-to-br from-accent-500/20 to-purple-500/20 flex items-center justify-center font-medium text-accent-400 flex-shrink-0">
                    {(participant.first_name?.[0] || participant.username?.[0] || '?').toUpperCase()}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="font-medium truncate">
                      {participant.first_name} {participant.last_name}
                    </p>
                    {participant.username && (
                      <p className="text-sm text-dark-400 truncate">@{participant.username}</p>
                    )}
                  </div>
                  <div className="text-right">
                    <p className="text-lg font-semibold text-accent-400">
                      {participant.messages_count}
                    </p>
                    <p className="text-xs text-dark-500">сообщ.</p>
                  </div>
                </motion.div>
              ))}
            </div>
          )}
        </Tabs.Content>

        {/* Criteria Tab */}
        <Tabs.Content value="criteria" className="flex-1 overflow-y-auto">
          <CriteriaPanel chatId={chat.id} chatType={chat.chat_type} />
        </Tabs.Content>

        {/* Reports Tab */}
        <Tabs.Content value="reports" className="flex-1 overflow-y-auto p-4">
          <div className="space-y-4">
            <div className="glass-light rounded-xl p-4">
              <h3 className="font-semibold mb-3">Создать отчёт</h3>
              <p className="text-sm text-dark-400 mb-4">
                Скачайте полный аналитический отчёт по этому чату
              </p>
              {downloadingReport && (
                <div className="flex items-center gap-2 mb-4 p-3 rounded-lg bg-accent-500/10 text-accent-400">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span className="text-sm">Генерация отчёта... Это может занять до минуты</span>
                </div>
              )}
              <div className="flex flex-wrap gap-2">
                <button
                  onClick={() => handleDownloadReport('pdf')}
                  disabled={!!downloadingReport}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg bg-red-500/20 text-red-400 hover:bg-red-500/30 disabled:opacity-50 disabled:cursor-wait transition-colors"
                >
                  {downloadingReport === 'pdf' ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Download className="w-4 h-4" />
                  )}
                  PDF
                </button>
                <button
                  onClick={() => handleDownloadReport('docx')}
                  disabled={!!downloadingReport}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-500/20 text-blue-400 hover:bg-blue-500/30 disabled:opacity-50 disabled:cursor-wait transition-colors"
                >
                  {downloadingReport === 'docx' ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Download className="w-4 h-4" />
                  )}
                  DOCX
                </button>
                <button
                  onClick={() => handleDownloadReport('markdown')}
                  disabled={!!downloadingReport}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg bg-purple-500/20 text-purple-400 hover:bg-purple-500/30 disabled:opacity-50 disabled:cursor-wait transition-colors"
                >
                  {downloadingReport === 'markdown' ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Download className="w-4 h-4" />
                  )}
                  Markdown
                </button>
              </div>
            </div>
          </div>
        </Tabs.Content>
      </Tabs.Root>

      {/* Import History Modal */}
      <ImportHistoryModal
        chatId={chat.id}
        chatTitle={chat.custom_name || chat.title}
        isOpen={showImportModal}
        onClose={() => setShowImportModal(false)}
      />
    </div>
  );
}
