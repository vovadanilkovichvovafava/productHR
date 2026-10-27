import { useState, useRef, useEffect, useReducer, useCallback } from 'react';
import { motion } from 'framer-motion';
import { X, Upload, Video, Link as LinkIcon, User, FileText } from 'lucide-react';
import clsx from 'clsx';
import { useCallStore } from '@/stores/callStore';
import { getEntities, uploadTextCall } from '@/services/api';
import toast from 'react-hot-toast';
import type { Entity } from '@/types';
import { backdropClose } from '@/utils/backdropClose';

interface CallRecorderModalProps {
  onClose: () => void;
  onSuccess: (callId: number) => void;
}

type RecordMode = 'upload' | 'bot';

// Reducer for entity search state (related states that change together)
interface EntitySearchState {
  entities: Entity[];
  selectedEntityId: number | null;
  searchQuery: string;
  showDropdown: boolean;
}

type EntitySearchAction =
  | { type: 'SET_ENTITIES'; entities: Entity[] }
  | { type: 'SELECT_ENTITY'; entityId: number }
  | { type: 'CLEAR_SELECTION' }
  | { type: 'UPDATE_SEARCH'; query: string }
  | { type: 'SHOW_DROPDOWN' }
  | { type: 'HIDE_DROPDOWN' };

function entitySearchReducer(state: EntitySearchState, action: EntitySearchAction): EntitySearchState {
  switch (action.type) {
    case 'SET_ENTITIES':
      return { ...state, entities: action.entities };
    case 'SELECT_ENTITY':
      return {
        ...state,
        selectedEntityId: action.entityId,
        searchQuery: '',
        showDropdown: false
      };
    case 'CLEAR_SELECTION':
      return {
        ...state,
        selectedEntityId: null,
        searchQuery: ''
      };
    case 'UPDATE_SEARCH':
      return {
        ...state,
        searchQuery: action.query,
        selectedEntityId: null,
        showDropdown: true
      };
    case 'SHOW_DROPDOWN':
      return { ...state, showDropdown: true };
    case 'HIDE_DROPDOWN':
      return { ...state, showDropdown: false };
    default:
      return state;
  }
}

const initialEntitySearchState: EntitySearchState = {
  entities: [],
  selectedEntityId: null,
  searchQuery: '',
  showDropdown: false
};

export default function CallRecorderModal({ onClose, onSuccess }: CallRecorderModalProps) {
  const { uploadCall, startBot, isLoading } = useCallStore();
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Form states (independent, rarely change together)
  const [mode, setMode] = useState<RecordMode>('bot');
  const [file, setFile] = useState<File | null>(null);
  const [meetingUrl, setMeetingUrl] = useState('');
  const [botName, setBotName] = useState('HR Recorder');

  // Entity search state (related states that change together)
  const [entitySearch, dispatchEntitySearch] = useReducer(entitySearchReducer, initialEntitySearchState);

  useEffect(() => {
    loadEntities();
  }, []);

  const loadEntities = async () => {
    try {
      const data = await getEntities({ limit: 100 });
      dispatchEntitySearch({ type: 'SET_ENTITIES', entities: data });
    } catch (err) {
      console.error('Failed to load entities:', err);
    }
  };

  const filteredEntities = entitySearch.entities.filter((e) =>
    e.name.toLowerCase().includes(entitySearch.searchQuery.toLowerCase())
  );

  const selectedEntity = entitySearch.entities.find((e) => e.id === entitySearch.selectedEntityId);

  // Close dropdown on click outside or Escape
  const dropdownContainerRef = useRef<HTMLDivElement>(null);

  const handleClickOutside = useCallback((e: PointerEvent) => {
    if (
      dropdownContainerRef.current &&
      !dropdownContainerRef.current.contains(e.target as Node)
    ) {
      dispatchEntitySearch({ type: 'HIDE_DROPDOWN' });
    }
  }, []);

  const handleEscapeKey = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Escape') {
      dispatchEntitySearch({ type: 'HIDE_DROPDOWN' });
    }
  }, []);

  useEffect(() => {
    if (entitySearch.showDropdown) {
      document.addEventListener('pointerdown', handleClickOutside);
      document.addEventListener('keydown', handleEscapeKey);
      return () => {
        document.removeEventListener('pointerdown', handleClickOutside);
        document.removeEventListener('keydown', handleEscapeKey);
      };
    }
  }, [entitySearch.showDropdown, handleClickOutside, handleEscapeKey]);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0];
    if (selected) {
      setFile(selected);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const dropped = e.dataTransfer.files[0];
    if (dropped) {
      setFile(dropped);
    }
  };

  // Detect if file is a text/document type (not audio/video)
  const isTextFile = (f: File): boolean => {
    const textExtensions = ['.txt', '.csv', '.md', '.rtf', '.log', '.pdf', '.doc', '.docx', '.html', '.htm'];
    const ext = f.name.toLowerCase().slice(f.name.lastIndexOf('.'));
    return textExtensions.includes(ext);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    try {
      let callId: number;

      if (mode === 'upload') {
        if (!file) return;

        if (isTextFile(file)) {
          // Text/document file - use text upload endpoint (skip transcription)
          const result = await uploadTextCall(
            file,
            entitySearch.selectedEntityId || undefined
          );
          callId = result.id;
          toast.success('Текстовый файл загружен. AI анализ запущен.');
        } else {
          // Audio/video file - use standard upload
          callId = await uploadCall(file, entitySearch.selectedEntityId || undefined);
        }
      } else {
        if (!meetingUrl) return;
        callId = await startBot(meetingUrl, botName, entitySearch.selectedEntityId || undefined);
      }

      onSuccess(callId);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Ошибка загрузки';
      toast.error(message);
    }
  };

  const isValidUrl = (url: string) => {
    return url.includes('meet.google.com') || url.includes('zoom.us');
  };

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4"
      {...backdropClose(onClose)}
    >
      <motion.div
        initial={{ scale: 0.95, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        exit={{ scale: 0.95, opacity: 0 }}
        className="glass rounded-2xl w-full max-w-lg max-w-[calc(100%-2rem)] max-h-[90vh] overflow-hidden flex flex-col shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-white/10 flex-shrink-0 gap-4 overflow-hidden">
          <h2 className="text-xl font-semibold text-white truncate min-w-0">Новая запись</h2>
          <button
            onClick={onClose}
            className="p-2 rounded-lg hover:bg-white/10 transition-colors flex-shrink-0"
          >
            <X size={20} className="text-white/60" />
          </button>
        </div>

        {/* Mode Tabs */}
        <div className="flex p-4 gap-2 border-b border-white/10 flex-shrink-0">
          <button
            onClick={() => setMode('bot')}
            className={clsx(
              'flex-1 p-3 rounded-lg flex items-center justify-center gap-2 transition-colors',
              mode === 'bot'
                ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/50'
                : 'glass-light text-white/60 hover:bg-white/10'
            )}
          >
            <Video size={20} />
            Присоединиться к встрече
          </button>
          <button
            onClick={() => setMode('upload')}
            className={clsx(
              'flex-1 p-3 rounded-lg flex items-center justify-center gap-2 transition-colors',
              mode === 'upload'
                ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/50'
                : 'glass-light text-white/60 hover:bg-white/10'
            )}
          >
            <Upload size={20} />
            Загрузить файл
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="p-6 space-y-6 overflow-y-auto flex-1">
          {mode === 'upload' ? (
            <>
              {/* File Upload */}
              <div
                onDrop={handleDrop}
                onDragOver={(e) => e.preventDefault()}
                onClick={() => fileInputRef.current?.click()}
                className={clsx(
                  'border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors',
                  file
                    ? 'border-cyan-500/50 bg-cyan-500/10'
                    : 'border-white/20 hover:border-white/40'
                )}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="audio/*,video/*,.mp3,.mp4,.wav,.m4a,.webm,.ogg,.txt,.csv,.md,.rtf,.log,.pdf,.doc,.docx,.html,.htm"
                  onChange={handleFileChange}
                  className="hidden"
                />
                {file ? (
                  <div className="flex flex-col items-center overflow-hidden max-w-full">
                    {isTextFile(file) ? (
                      <FileText size={40} className="text-blue-400 mb-3 flex-shrink-0" />
                    ) : (
                      <Upload size={40} className="text-cyan-400 mb-3 flex-shrink-0" />
                    )}
                    <p className="text-white font-medium truncate max-w-full px-4">{file.name}</p>
                    <p className="text-sm text-white/40 mt-1">
                      {(file.size / 1024 / 1024).toFixed(2)} MB
                      {isTextFile(file) && ' · Текстовый файл (без транскрибации)'}
                    </p>
                  </div>
                ) : (
                  <div className="flex flex-col items-center">
                    <Upload size={40} className="text-white/40 mb-3" />
                    <p className="text-white/60">Перетащите файл сюда</p>
                    <p className="text-sm text-white/40 mt-1">
                      или нажмите для выбора
                    </p>
                    <p className="text-xs text-white/30 mt-3">
                      Аудио/Видео: MP3, MP4, WAV, M4A, WebM, OGG
                    </p>
                    <p className="text-xs text-white/30 mt-1">
                      Текст: TXT, CSV, PDF, DOC, DOCX, MD, HTML
                    </p>
                  </div>
                )}
              </div>
            </>
          ) : (
            <>
              {/* Meeting URL */}
              <div>
                <label className="block text-sm font-medium text-white/60 mb-2">
                  Ссылка на встречу
                </label>
                <div className="relative">
                  <LinkIcon className="absolute left-3 top-1/2 -translate-y-1/2 text-white/40" size={18} />
                  <input
                    type="url"
                    value={meetingUrl}
                    onChange={(e) => setMeetingUrl(e.target.value)}
                    className={clsx(
                      'w-full pl-10 pr-4 py-2 glass-light border rounded-lg text-white placeholder-white/40 focus:outline-none',
                      meetingUrl && !isValidUrl(meetingUrl)
                        ? 'border-red-500/50 focus:border-red-500/50'
                        : 'border-white/10 focus:border-cyan-500/50'
                    )}
                    placeholder="https://meet.google.com/xxx-xxxx-xxx"
                  />
                </div>
                {meetingUrl && !isValidUrl(meetingUrl) && (
                  <p className="text-red-400 text-xs mt-1">
                    Поддерживаются только Google Meet и Zoom
                  </p>
                )}
              </div>

              {/* Bot Name */}
              <div>
                <label className="block text-sm font-medium text-white/60 mb-2">
                  Имя бота
                </label>
                <input
                  type="text"
                  value={botName}
                  onChange={(e) => setBotName(e.target.value)}
                  className="w-full px-4 py-2 glass-light rounded-lg text-white placeholder-white/40 focus:outline-none focus:border-cyan-500/50"
                  placeholder="HR Recorder"
                />
              </div>
            </>
          )}

          {/* Link to Entity */}
          <div className="relative" ref={dropdownContainerRef}>
            <label className="block text-sm font-medium text-white/60 mb-2">
              Связать с контактом (опционально)
            </label>
            <div className="relative overflow-hidden">
              <User className="absolute left-3 top-1/2 -translate-y-1/2 text-white/40 flex-shrink-0" size={18} />
              <input
                type="text"
                value={selectedEntity ? selectedEntity.name : entitySearch.searchQuery}
                onChange={(e) => dispatchEntitySearch({ type: 'UPDATE_SEARCH', query: e.target.value })}
                onFocus={() => dispatchEntitySearch({ type: 'SHOW_DROPDOWN' })}
                className="w-full pl-10 pr-10 py-2 glass-light rounded-lg text-white placeholder-white/40 focus:outline-none focus:border-cyan-500/50 truncate"
                placeholder="Поиск контактов..."
              />
              {entitySearch.selectedEntityId && (
                <button
                  type="button"
                  onClick={() => dispatchEntitySearch({ type: 'CLEAR_SELECTION' })}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-white/40 hover:text-white/60 flex-shrink-0"
                >
                  <X size={16} />
                </button>
              )}
            </div>

            {/* Entity Dropdown */}
            {entitySearch.showDropdown && !entitySearch.selectedEntityId && (
              <motion.div
                initial={{ opacity: 0, y: -10 }}
                animate={{ opacity: 1, y: 0 }}
                className="absolute z-10 w-full mt-1 bg-gray-800 border border-white/10 rounded-lg shadow-lg max-h-48 overflow-y-auto"
              >
                {filteredEntities.length > 0 ? (
                  filteredEntities.slice(0, 10).map((entity) => (
                    <button
                      key={entity.id}
                      type="button"
                      onClick={() => dispatchEntitySearch({ type: 'SELECT_ENTITY', entityId: entity.id })}
                      className="w-full px-4 py-2 text-left hover:bg-white/10 transition-colors flex items-center gap-3 overflow-hidden min-w-0"
                    >
                      <User size={16} className="text-white/40 flex-shrink-0" />
                      <div className="overflow-hidden min-w-0 flex-1">
                        <p className="text-white text-sm truncate">{entity.name}</p>
                        <p className="text-xs text-white/40 truncate">{entity.type}</p>
                      </div>
                    </button>
                  ))
                ) : (
                  <div className="px-4 py-3 text-white/40 text-sm">Контакты не найдены</div>
                )}
              </motion.div>
            )}
          </div>

          {/* Actions */}
          <div className="flex gap-3 pt-4 flex-shrink-0 flex-wrap">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 px-4 py-2 glass-light text-white/60 rounded-lg hover:bg-white/10 transition-colors min-w-[120px]"
            >
              Отмена
            </button>
            <button
              type="submit"
              disabled={isLoading || (mode === 'upload' ? !file : !meetingUrl || !isValidUrl(meetingUrl))}
              className="flex-1 px-4 py-2 bg-cyan-500 text-white rounded-lg hover:bg-cyan-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 min-w-[120px]"
            >
              {isLoading && (
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin flex-shrink-0" />
              )}
              <span className="whitespace-nowrap">{mode === 'upload' ? 'Загрузить и обработать' : 'Начать запись'}</span>
            </button>
          </div>
        </form>
      </motion.div>
    </motion.div>
  );
}
