import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  FileText,
  CheckSquare,
  Lightbulb,
  Clock,
  User,
  Copy,
  Check,
  RefreshCw,
  Edit3,
  X,
  Save,
  Link,
  Unlink,
  Download,
  Mic,
  Users
} from 'lucide-react';
import clsx from 'clsx';
import toast from 'react-hot-toast';
import { useCallStore } from '@/stores/callStore';
import { useEntityStore } from '@/stores/entityStore';
import { useAuthStore } from '@/stores/authStore';
import type { CallRecording } from '@/types';

interface CallDetailProps {
  call: CallRecording;
}

export default function CallDetail({ call }: CallDetailProps) {
  const { reprocessCall, updateCall, isLoading } = useCallStore();
  const { entities, fetchEntities } = useEntityStore();
  const { user, canEditResource } = useAuthStore();

  // Permission check for editing
  const canEdit = () => {
    return canEditResource({
      owner_id: call.owner_id,
      is_mine: call.is_mine ?? (call.owner_id === user?.id),
      access_level: call.access_level ?? undefined
    });
  };

  const [activeTab, setActiveTab] = useState<'transcript' | 'summary' | 'actions'>('summary');
  const [copied, setCopied] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [editTitle, setEditTitle] = useState(call.title || '');
  const [editEntityId, setEditEntityId] = useState<number | null>(call.entity_id || null);
  const [saving, setSaving] = useState(false);
  const copyTimeoutRef = useRef<ReturnType<typeof setTimeout>>();

  // Cleanup timeout on unmount to prevent memory leaks
  useEffect(() => {
    return () => {
      if (copyTimeoutRef.current) clearTimeout(copyTimeoutRef.current);
    };
  }, []);

  // Fetch entities for dropdown
  useEffect(() => {
    if (isEditing && entities.length === 0) {
      fetchEntities();
    }
  }, [isEditing]);

  // Sync edit state when call changes
  useEffect(() => {
    setEditTitle(call.title || '');
    setEditEntityId(call.entity_id || null);
  }, [call.id, call.title, call.entity_id]);

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    toast.success('Скопировано');
    if (copyTimeoutRef.current) clearTimeout(copyTimeoutRef.current);
    copyTimeoutRef.current = setTimeout(() => setCopied(false), 2000);
  };

  const handleReprocess = async () => {
    try {
      await reprocessCall(call.id);
      toast.success('Переобработка запущена');
    } catch {
      toast.error('Не удалось запустить переобработку');
    }
  };

  const handleSaveEdit = async () => {
    setSaving(true);
    try {
      await updateCall(call.id, {
        title: editTitle || undefined,
        entity_id: editEntityId === null ? -1 : editEntityId
      });
      toast.success('Изменения сохранены');
      setIsEditing(false);
    } catch {
      toast.error('Не удалось сохранить');
    } finally {
      setSaving(false);
    }
  };

  const handleCancelEdit = () => {
    setEditTitle(call.title || '');
    setEditEntityId(call.entity_id || null);
    setIsEditing(false);
  };

  // Get corrected duration - handles bug where minutes were stored as seconds
  const getCorrectedDuration = (): number => {
    if (!call.duration_seconds) return 0;

    // Find max timestamp from speakers to detect duration bug
    const maxEndTimestamp = call.speakers?.reduce((max, s) => Math.max(max, s.end || 0), 0) || 0;

    // If duration_seconds is much smaller than max speaker timestamp,
    // it was likely stored in minutes instead of seconds
    if (maxEndTimestamp > 0 && call.duration_seconds < maxEndTimestamp * 0.5) {
      return maxEndTimestamp;
    }

    return call.duration_seconds;
  };

  const correctedDuration = getCorrectedDuration();

  const formatDuration = (seconds?: number) => {
    if (!seconds) return '—';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}м ${secs}с`;
  };

  const formatTimeForExport = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const downloadFile = (content: string, filename: string) => {
    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
    toast.success(`Файл "${filename}" скачан`);
  };

  const handleExportTranscript = () => {
    if (!call.speakers || call.speakers.length === 0) {
      if (call.transcript) {
        downloadFile(call.transcript, `transcript_${call.id}.txt`);
      }
      return;
    }

    // Format transcript with timestamps and speakers
    const lines = call.speakers.map(segment => {
      const time = `[${formatTimeForExport(segment.start)}]`;
      return `${time} ${segment.speaker}:\n${segment.text}\n`;
    });

    const content = `Транскрипт: ${call.title || 'Звонок #' + call.id}\n` +
      `Дата: ${new Date(call.created_at).toLocaleString('ru-RU')}\n` +
      `Длительность: ${formatDuration(correctedDuration)}\n` +
      `${'='.repeat(50)}\n\n` +
      lines.join('\n');

    downloadFile(content, `transcript_${call.id}.txt`);
  };

  // Calculate speaker statistics
  const getSpeakerStats = () => {
    if (!call.speakers || call.speakers.length === 0) return [];

    const stats: Record<string, { talkTime: number; wordCount: number; segmentDuration: number }> = {};
    let totalSegmentDuration = 0;

    let maxEndTimestamp = 0;

    call.speakers.forEach(segment => {
      const speaker = segment.speaker;
      const segmentDur = segment.end - segment.start;
      const words = segment.text.split(/\s+/).filter(w => w.length > 0).length;

      if (!stats[speaker]) {
        stats[speaker] = { talkTime: 0, wordCount: 0, segmentDuration: 0 };
      }
      stats[speaker].segmentDuration += segmentDur;
      stats[speaker].wordCount += words;
      totalSegmentDuration += segmentDur;

      // Track max timestamp to detect duration bugs
      if (segment.end > maxEndTimestamp) {
        maxEndTimestamp = segment.end;
      }
    });

    // Fix for duration bug: if duration_seconds is much smaller than max speaker timestamp,
    // it was likely stored in minutes instead of seconds. Use max timestamp as fallback.
    let actualDuration = call.duration_seconds || totalSegmentDuration;
    if (call.duration_seconds && maxEndTimestamp > 0 && call.duration_seconds < maxEndTimestamp * 0.5) {
      // duration_seconds is suspiciously small compared to timestamps - use max timestamp
      actualDuration = maxEndTimestamp;
    }

    const scaleFactor = totalSegmentDuration > 0 ? actualDuration / totalSegmentDuration : 1;

    // Convert to array with percentages and WPM
    return Object.entries(stats).map(([speaker, data]) => {
      // Scale talkTime to match actual call duration
      const talkTime = data.segmentDuration * scaleFactor;
      const percentage = actualDuration > 0 ? (talkTime / actualDuration) * 100 : 0;
      const minutes = talkTime / 60;
      const wpm = minutes > 0 ? Math.round(data.wordCount / minutes) : 0;

      return {
        speaker,
        talkTime,
        percentage: Math.round(percentage),
        wordCount: data.wordCount,
        wpm
      };
    }).sort((a, b) => b.percentage - a.percentage);
  };

  const speakerStats = getSpeakerStats();

  const speakerColors = [
    { bg: 'bg-cyan-500', light: 'bg-cyan-500/20', text: 'text-cyan-400' },
    { bg: 'bg-purple-500', light: 'bg-purple-500/20', text: 'text-purple-400' },
    { bg: 'bg-green-500', light: 'bg-green-500/20', text: 'text-green-400' },
    { bg: 'bg-yellow-500', light: 'bg-yellow-500/20', text: 'text-yellow-400' },
    { bg: 'bg-pink-500', light: 'bg-pink-500/20', text: 'text-pink-400' },
    { bg: 'bg-orange-500', light: 'bg-orange-500/20', text: 'text-orange-400' },
  ];

  const handleExportAnalysis = () => {
    const sections: string[] = [
      `Анализ звонка: ${call.title || 'Звонок #' + call.id}`,
      `Дата: ${new Date(call.created_at).toLocaleString('ru-RU')}`,
      `Длительность: ${formatDuration(correctedDuration)}`,
      '='.repeat(50),
      ''
    ];

    // Add speaker statistics
    if (speakerStats.length > 0) {
      sections.push('🎤 СТАТИСТИКА УЧАСТНИКОВ', '-'.repeat(30));
      speakerStats.forEach(stat => {
        const talkMin = Math.floor(stat.talkTime / 60);
        const talkSec = Math.floor(stat.talkTime % 60);
        sections.push(`${stat.speaker}: ${stat.percentage}% (${talkMin}м ${talkSec}с) | ${stat.wpm} слов/мин`);
      });
      sections.push('');
    }

    if (call.summary) {
      sections.push('📋 РЕЗЮМЕ', '-'.repeat(30), call.summary, '');
    }

    if (call.key_points && call.key_points.length > 0) {
      sections.push('💡 КЛЮЧЕВЫЕ МОМЕНТЫ', '-'.repeat(30));
      call.key_points.forEach((point, i) => {
        sections.push(`${i + 1}. ${point}`);
      });
      sections.push('');
    }

    if (call.action_items && call.action_items.length > 0) {
      sections.push('✅ ЗАДАЧИ', '-'.repeat(30));
      call.action_items.forEach((item, i) => {
        sections.push(`${i + 1}. ${item}`);
      });
      sections.push('');
    }

    downloadFile(sections.join('\n'), `analysis_${call.id}.txt`);
  };

  return (
    <div className="p-6">
      {/* Edit Panel */}
      <AnimatePresence>
        {isEditing && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="bg-gradient-to-r from-purple-500/20 to-cyan-500/20 border border-purple-500/30 rounded-xl p-4 mb-6"
          >
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                <Edit3 size={20} className="text-purple-400" />
                Редактирование звонка
              </h3>
              <div className="flex gap-2">
                <button
                  onClick={handleCancelEdit}
                  className="px-3 py-1.5 rounded-lg bg-white/10 text-white/60 hover:bg-white/20 transition-colors flex items-center gap-2"
                >
                  <X size={16} />
                  Отмена
                </button>
                <button
                  onClick={handleSaveEdit}
                  disabled={saving}
                  className="px-3 py-1.5 rounded-lg bg-cyan-500/20 text-cyan-400 hover:bg-cyan-500/30 transition-colors flex items-center gap-2"
                >
                  {saving ? (
                    <div className="w-4 h-4 border-2 border-cyan-400 border-t-transparent rounded-full animate-spin" />
                  ) : (
                    <Save size={16} />
                  )}
                  Сохранить
                </button>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              {/* Title */}
              <div>
                <label className="block text-sm text-white/60 mb-2">
                  Название звонка
                </label>
                <input
                  type="text"
                  value={editTitle}
                  onChange={(e) => setEditTitle(e.target.value)}
                  placeholder="Например: Интервью с кандидатом"
                  className="w-full px-4 py-2 glass-light rounded-lg text-white placeholder:text-white/30 focus:outline-none focus:border-cyan-500/50"
                />
              </div>

              {/* Entity Link */}
              <div>
                <label className="block text-sm text-white/60 mb-2">
                  Связать с контактом
                </label>
                <div className="flex gap-2">
                  <select
                    value={editEntityId || ''}
                    onChange={(e) => setEditEntityId(e.target.value ? parseInt(e.target.value) : null)}
                    className="flex-1 px-4 py-2 glass-light rounded-lg text-white focus:outline-none focus:border-cyan-500/50 appearance-none cursor-pointer"
                  >
                    <option value="" className="bg-gray-900">Не связан</option>
                    {entities.map((entity) => (
                      <option key={entity.id} value={entity.id} className="bg-gray-900">
                        {entity.name} ({entity.type})
                      </option>
                    ))}
                  </select>
                  {editEntityId && (
                    <button
                      onClick={() => setEditEntityId(null)}
                      className="p-2 rounded-lg bg-red-500/20 text-red-400 hover:bg-red-500/30 transition-colors"
                      title="Отвязать"
                    >
                      <Unlink size={20} />
                    </button>
                  )}
                </div>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Status Banner - Failed */}
      {call.status === 'failed' && (
        <div className="bg-red-500/20 border border-red-500/30 rounded-xl p-4 mb-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-red-400 font-medium">Обработка не удалась</p>
              {call.error_message && (
                <p className="text-sm text-red-300/60 mt-1">{call.error_message}</p>
              )}
            </div>
            {canEdit() && (
              <button
                onClick={handleReprocess}
                disabled={isLoading}
                className="px-4 py-2 bg-red-500/20 text-red-400 rounded-lg hover:bg-red-500/30 transition-colors flex items-center gap-2"
              >
                <RefreshCw size={16} className={isLoading ? 'animate-spin' : ''} />
                Повторить
              </button>
            )}
          </div>
        </div>
      )}


      {call.status !== 'done' && call.status !== 'failed' && (
        <div className={clsx(
          'rounded-xl p-4 mb-6 border',
          call.status === 'recording'
            ? 'bg-red-500/20 border-red-500/30'
            : 'bg-cyan-500/20 border-cyan-500/30'
        )}>
          <div className="flex items-center gap-3">
            {call.status === 'recording' ? (
              <div className="w-4 h-4 bg-red-500 rounded-full animate-pulse" />
            ) : (
              <div className="w-5 h-5 border-2 border-cyan-400 border-t-transparent rounded-full animate-spin" />
            )}
            <div className="flex-1">
              <p className={clsx(
                'font-medium',
                call.status === 'recording' ? 'text-red-400' : 'text-cyan-400'
              )}>
                {call.status === 'recording' ? '● REC' : 'Обработка'}
              </p>
              <p className={clsx(
                'text-sm',
                call.status === 'recording' ? 'text-red-300/60' : 'text-cyan-300/60'
              )}>
                {call.status === 'transcribing' && 'Транскрибируем аудио...'}
                {call.status === 'analyzing' && 'Анализируем содержимое...'}
                {call.status === 'processing' && 'Обрабатываем аудио файл...'}
                {call.status === 'recording' && 'Fireflies бот записывает встречу. Завершите встречу для обработки.'}
                {call.status === 'connecting' && 'Подключаемся к встрече...'}
                {call.status === 'pending' && 'Ожидание...'}
              </p>
            </div>
            {call.status === 'recording' && call.started_at && (
              <div className="text-right">
                <p className="text-xs text-red-400/60">Начало</p>
                <p className="text-sm text-red-300">
                  {new Date(call.started_at).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })}
                </p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Info Cards */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        <div className="glass-light rounded-xl p-4">
          <div className="flex items-center gap-2 text-white/40 text-sm mb-2">
            <Clock size={16} />
            Длительность
          </div>
          <p className="text-2xl font-semibold text-white">
            {formatDuration(correctedDuration)}
          </p>
        </div>

        <div className="glass-light rounded-xl p-4">
          <div className="flex items-center gap-2 text-white/40 text-sm mb-2">
            <FileText size={16} />
            Источник
          </div>
          <p className="text-2xl font-semibold text-white capitalize">
            {call.source_type}
          </p>
        </div>

        <div className="glass-light rounded-xl p-4 relative group overflow-hidden">
          <div className="flex items-center gap-2 text-white/40 text-sm mb-2">
            <User size={16} className="flex-shrink-0" />
            Контакт
          </div>
          <div className="flex items-center justify-between gap-2 overflow-hidden min-w-0">
            <p className="text-lg font-semibold text-white truncate min-w-0">
              {call.entity_name || 'Не связан'}
            </p>
            {!isEditing && canEdit() && (
              <button
                onClick={() => setIsEditing(true)}
                className="opacity-0 group-hover:opacity-100 p-1.5 rounded-lg bg-white/10 hover:bg-white/20 transition-all flex-shrink-0"
                title="Редактировать"
              >
                <Edit3 size={14} className="text-white/60" />
              </button>
            )}
          </div>
          {call.entity_id && (
            <div className="mt-1 flex items-center gap-1 text-xs text-cyan-400/60">
              <Link size={12} className="flex-shrink-0" />
              Связан
            </div>
          )}
        </div>
      </div>

      {/* Speaker Statistics */}
      {call.status === 'done' && speakerStats.length > 0 && (
        <div className="glass-light rounded-xl p-4 mb-6 overflow-hidden">
          <h3 className="text-sm font-medium text-white/60 flex items-center gap-2 mb-4">
            <Users size={16} />
            Статистика участников
          </h3>
          <div className="space-y-3 overflow-hidden">
            {speakerStats.map((stat, idx) => {
              const colorSet = speakerColors[idx % speakerColors.length];
              return (
                <div key={stat.speaker} className="flex items-center gap-4 overflow-hidden min-w-0">
                  {/* Speaker name and icon */}
                  <div className="flex items-center gap-2 min-w-0 flex-1 overflow-hidden">
                    <div className={clsx(
                      'w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0',
                      colorSet.light
                    )}>
                      <Mic size={14} className={colorSet.text} />
                    </div>
                    <span className="text-white text-sm truncate min-w-0">{stat.speaker}</span>
                  </div>

                  {/* WPM */}
                  <div className="text-right w-16 flex-shrink-0">
                    <span className="text-white/60 text-xs">WPM</span>
                    <p className={clsx('text-sm font-medium', colorSet.text)}>{stat.wpm}</p>
                  </div>

                  {/* Percentage bar */}
                  <div className="w-32 flex-shrink-0 max-w-[8rem]">
                    <div className="flex justify-between text-xs mb-1 overflow-hidden">
                      <span className="text-white/40 truncate">{Math.floor(stat.talkTime / 60)}м {Math.floor(stat.talkTime % 60)}с</span>
                      <span className={clsx('font-medium flex-shrink-0 ml-1', colorSet.text)}>{stat.percentage}%</span>
                    </div>
                    <div className="h-2 bg-white/10 rounded-full overflow-hidden max-w-full">
                      <div
                        className={clsx('h-full rounded-full transition-all', colorSet.bg)}
                        style={{ width: `${stat.percentage}%` }}
                      />
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Title Display/Edit Button */}
      {(call.title || !isEditing) && (
        <div className="flex items-center gap-3 mb-6">
          {call.title && (
            <div className="flex-1 glass-light rounded-xl p-4">
              <div className="flex items-center gap-2 text-white/40 text-sm mb-1">
                <FileText size={14} />
                Название
              </div>
              <p className="text-white font-medium">{call.title}</p>
            </div>
          )}
          {!isEditing && canEdit() && (
            <button
              onClick={() => setIsEditing(true)}
              className="px-4 py-2 rounded-lg bg-purple-500/20 text-purple-400 hover:bg-purple-500/30 transition-colors flex items-center gap-2"
            >
              <Edit3 size={16} />
              {call.title || call.entity_name ? 'Редактировать' : 'Добавить название / связать'}
            </button>
          )}
        </div>
      )}

      {/* Tabs */}
      {call.status === 'done' && (
        <>
          <div className="flex gap-2 mb-6 overflow-x-auto flex-wrap">
            {[
              { id: 'summary', label: 'Резюме', icon: FileText },
              { id: 'transcript', label: 'Транскрипт', icon: FileText },
              { id: 'actions', label: 'Задачи', icon: CheckSquare }
            ].map((tab) => {
              const Icon = tab.icon;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id as typeof activeTab)}
                  className={clsx(
                    'px-4 py-2 rounded-lg text-sm flex items-center gap-2 transition-colors flex-shrink-0',
                    activeTab === tab.id
                      ? 'bg-cyan-500/20 text-cyan-400'
                      : 'glass-light text-white/60 hover:bg-white/10'
                  )}
                >
                  <Icon size={16} className="flex-shrink-0" />
                  <span className="whitespace-nowrap">{tab.label}</span>
                </button>
              );
            })}
          </div>

          {/* Tab Content */}
          <motion.div
            key={activeTab}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="glass-light rounded-xl p-6"
          >
            {activeTab === 'summary' && (
              <div className="space-y-6 overflow-hidden">
                {/* Action buttons for analysis */}
                {(call.summary || (call.key_points && call.key_points.length > 0) || (call.action_items && call.action_items.length > 0)) && (
                  <div className="flex justify-end gap-2 flex-wrap">
                    {canEdit() && (
                      <button
                        onClick={handleReprocess}
                        disabled={isLoading}
                        className="px-3 py-2 rounded-lg bg-purple-500/20 hover:bg-purple-500/30 transition-colors flex items-center gap-2 flex-shrink-0"
                        title="Переанализировать с обновлённым AI промптом"
                      >
                        <RefreshCw size={16} className={clsx('text-purple-400 flex-shrink-0', isLoading && 'animate-spin')} />
                        <span className="text-sm text-purple-400 whitespace-nowrap">Переанализировать</span>
                      </button>
                    )}
                    <button
                      onClick={handleExportAnalysis}
                      className="px-3 py-2 rounded-lg bg-cyan-500/20 hover:bg-cyan-500/30 transition-colors flex items-center gap-2 flex-shrink-0"
                      title="Скачать анализ"
                    >
                      <Download size={16} className="text-cyan-400 flex-shrink-0" />
                      <span className="text-sm text-cyan-400 whitespace-nowrap">Скачать</span>
                    </button>
                  </div>
                )}

                {call.summary && (
                  <div className="overflow-hidden">
                    <div className="flex items-center justify-between mb-3 gap-2">
                      <h3 className="text-lg font-semibold text-white flex items-center gap-2 min-w-0">
                        <FileText size={20} className="text-cyan-400 flex-shrink-0" />
                        <span className="truncate">Резюме</span>
                      </h3>
                      <button
                        onClick={() => handleCopy(call.summary || '')}
                        className="p-2 rounded-lg glass-light hover:bg-white/10 transition-colors flex-shrink-0"
                      >
                        {copied ? <Check size={16} className="text-green-400" /> : <Copy size={16} className="text-white/40" />}
                      </button>
                    </div>
                    <p className="text-white/80 whitespace-pre-wrap leading-relaxed break-words overflow-hidden">{call.summary}</p>
                  </div>
                )}

                {call.key_points && call.key_points.length > 0 && (
                  <div className="overflow-hidden">
                    <h3 className="text-lg font-semibold text-white flex items-center gap-2 mb-3">
                      <Lightbulb size={20} className="text-yellow-400 flex-shrink-0" />
                      <span className="truncate">Ключевые моменты</span>
                    </h3>
                    <ul className="space-y-2 overflow-hidden">
                      {call.key_points.map((point, idx) => (
                        <li key={idx} className="flex items-start gap-3 text-white/80 break-words overflow-hidden">
                          <span className="w-6 h-6 rounded-full bg-yellow-500/20 text-yellow-400 flex items-center justify-center text-xs flex-shrink-0 mt-0.5">
                            {idx + 1}
                          </span>
                          <span className="break-words overflow-hidden min-w-0">{point}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {!call.summary && (!call.key_points || call.key_points.length === 0) && (
                  <p className="text-white/40">Резюме недоступно</p>
                )}
              </div>
            )}

            {activeTab === 'transcript' && (
              <div className="overflow-hidden">
                <div className="flex items-center justify-between mb-4 gap-2 flex-wrap">
                  <h3 className="text-lg font-semibold text-white truncate min-w-0">Транскрипт</h3>
                  <div className="flex gap-2 flex-shrink-0 flex-wrap">
                    {(call.transcript || (call.speakers && call.speakers.length > 0)) && (
                      <>
                        <button
                          onClick={handleExportTranscript}
                          className="px-3 py-2 rounded-lg bg-cyan-500/20 hover:bg-cyan-500/30 transition-colors flex items-center gap-2 flex-shrink-0"
                          title="Скачать транскрипт как текстовый файл"
                        >
                          <Download size={16} className="text-cyan-400 flex-shrink-0" />
                          <span className="text-sm text-cyan-400 whitespace-nowrap">Скачать транскрипт</span>
                        </button>
                        <button
                          onClick={() => handleCopy(call.transcript || '')}
                          className="p-2 rounded-lg glass-light hover:bg-white/10 transition-colors flex-shrink-0"
                          title="Копировать"
                        >
                          {copied ? <Check size={16} className="text-green-400" /> : <Copy size={16} className="text-white/40" />}
                        </button>
                      </>
                    )}
                  </div>
                </div>

                {/* Speaker-based transcript (chat style) */}
                {call.speakers && call.speakers.length > 0 ? (
                  <div className="space-y-3 overflow-hidden max-w-full">
                    {call.speakers.map((segment, idx) => {
                      // Generate consistent color for each speaker
                      const speakerColors = [
                        { bg: 'bg-cyan-500/20', border: 'border-cyan-500/30', text: 'text-cyan-400' },
                        { bg: 'bg-purple-500/20', border: 'border-purple-500/30', text: 'text-purple-400' },
                        { bg: 'bg-green-500/20', border: 'border-green-500/30', text: 'text-green-400' },
                        { bg: 'bg-yellow-500/20', border: 'border-yellow-500/30', text: 'text-yellow-400' },
                        { bg: 'bg-pink-500/20', border: 'border-pink-500/30', text: 'text-pink-400' },
                        { bg: 'bg-orange-500/20', border: 'border-orange-500/30', text: 'text-orange-400' },
                      ];

                      // Get unique speakers to assign colors
                      const uniqueSpeakers = [...new Set(call.speakers?.map(s => s.speaker) || [])];
                      const speakerIndex = uniqueSpeakers.indexOf(segment.speaker);
                      const colorSet = speakerColors[speakerIndex % speakerColors.length];

                      const formatTime = (seconds: number) => {
                        const mins = Math.floor(seconds / 60);
                        const secs = Math.floor(seconds % 60);
                        return `${mins}:${secs.toString().padStart(2, '0')}`;
                      };

                      return (
                        <div
                          key={idx}
                          className={clsx(
                            'p-4 rounded-xl border overflow-hidden w-full max-w-full',
                            colorSet.bg,
                            colorSet.border
                          )}
                        >
                          <div className="flex items-center gap-3 mb-2 flex-wrap overflow-hidden min-w-0">
                            <div className={clsx(
                              'w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium flex-shrink-0',
                              colorSet.bg,
                              colorSet.text
                            )}>
                              <User size={16} />
                            </div>
                            <span className={clsx('font-medium truncate min-w-0', colorSet.text)}>
                              {segment.speaker}
                            </span>
                            <span className="px-2 py-0.5 rounded bg-white/10 text-white/50 text-xs flex items-center gap-1 ml-auto flex-shrink-0">
                              <Clock size={12} className="flex-shrink-0" />
                              <span className="whitespace-nowrap">{formatTime(segment.start)}</span>
                            </span>
                          </div>
                          <p className="text-white/80 leading-relaxed pl-11 break-words whitespace-pre-wrap overflow-hidden" style={{ overflowWrap: 'anywhere', wordBreak: 'break-word' }}>
                            {segment.text}
                          </p>
                        </div>
                      );
                    })}
                  </div>
                ) : call.transcript ? (
                  <div className="prose prose-invert max-w-full overflow-hidden">
                    <p className="text-white/80 whitespace-pre-wrap leading-relaxed break-words overflow-hidden" style={{ overflowWrap: 'anywhere', wordBreak: 'break-word' }}>{call.transcript}</p>
                  </div>
                ) : (
                  <p className="text-white/40">Транскрипт недоступен</p>
                )}
              </div>
            )}

            {activeTab === 'actions' && (
              <div className="overflow-hidden">
                <h3 className="text-lg font-semibold text-white flex items-center gap-2 mb-4">
                  <CheckSquare size={20} className="text-green-400 flex-shrink-0" />
                  <span className="truncate">Задачи</span>
                </h3>

                {call.action_items && call.action_items.length > 0 ? (
                  <ul className="space-y-3 overflow-hidden">
                    {call.action_items.map((item, idx) => (
                      <li key={idx} className="flex items-start gap-3 p-3 glass-light rounded-lg overflow-hidden">
                        <div className="w-5 h-5 rounded border border-green-500/50 flex items-center justify-center flex-shrink-0 mt-0.5">
                          <CheckSquare size={12} className="text-green-400 opacity-0" />
                        </div>
                        <span className="text-white/80 break-words overflow-hidden min-w-0">{item}</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-white/40">Задачи не обнаружены</p>
                )}
              </div>
            )}
          </motion.div>
        </>
      )}
    </div>
  );
}
