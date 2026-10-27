import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Phone,
  Upload,
  Video,
  Clock,
  ChevronLeft,
  RefreshCw,
  Trash2,
  CheckCircle,
  XCircle,
  Loader2,
  Link2,
  User
} from 'lucide-react';
import toast from 'react-hot-toast';
import clsx from 'clsx';
import { useCallStore } from '@/stores/callStore';
import { useAuthStore } from '@/stores/authStore';
import { formatDate } from '@/utils';
import type { CallStatus, CallRecording } from '@/types';
import { CALL_STATUS_LABELS, CALL_STATUS_COLORS } from '@/types';
import CallRecorderModal from '@/components/calls/CallRecorderModal';
import CallDetail from '@/components/calls/CallDetail';
import ExternalLinksModal from '@/components/calls/ExternalLinksModal';

export default function CallsPage() {
  const { callId } = useParams();
  const navigate = useNavigate();
  const [showRecorderModal, setShowRecorderModal] = useState(false);
  const [showExternalLinksModal, setShowExternalLinksModal] = useState(false);

  const {
    user,
    canEditResource,
    canDeleteResource
  } = useAuthStore();

  const {
    calls,
    currentCall,
    activeRecording,
    isLoading,
    fetchCalls,
    fetchCall,
    deleteCall,
    reprocessCall,
    stopRecording,
    clearActiveRecording,
    pollStatus,
    stopPolling
  } = useCallStore();

  // Helper functions to check permissions
  const canEdit = (call: CallRecording) => {
    return canEditResource({
      owner_id: call.owner_id,
      is_mine: call.owner_id === user?.id,
      access_level: call.access_level ?? undefined
    });
  };

  const canDelete = (call: CallRecording) => {
    return canDeleteResource({
      owner_id: call.owner_id,
      is_mine: call.owner_id === user?.id,
      access_level: call.access_level ?? undefined
    });
  };

  // Backend already filters calls by access control (ownership, department, sharing)
  // No additional filtering needed on frontend
  const accessibleCalls = calls;

  // Fetch calls on mount
  useEffect(() => {
    fetchCalls();
  }, [fetchCalls]);

  // Fetch specific call when URL changes
  useEffect(() => {
    if (callId) {
      fetchCall(parseInt(callId));
    }
  }, [callId, fetchCall]);

  // Auto-refresh currentCall when activeRecording status changes
  useEffect(() => {
    if (activeRecording && callId && activeRecording.id === parseInt(callId)) {
      fetchCall(parseInt(callId));
    }
  }, [activeRecording?.status, activeRecording?.id, callId, fetchCall]);

  // Also refresh the calls list when activeRecording completes
  useEffect(() => {
    if (activeRecording && (activeRecording.status === 'done' || activeRecording.status === 'failed')) {
      fetchCalls();
    }
  }, [activeRecording?.status, fetchCalls]);

  // Start polling if currentCall is in an active state (for page refreshes)
  useEffect(() => {
    if (currentCall && !activeRecording) {
      const activeStatuses = ['pending', 'connecting', 'recording', 'processing', 'transcribing', 'analyzing'];
      if (activeStatuses.includes(currentCall.status)) {
        pollStatus(currentCall.id);
      }
    }
    // Cleanup polling when component unmounts or callId changes
    return () => {
      stopPolling();
    };
  }, [currentCall?.id, currentCall?.status, activeRecording, pollStatus, stopPolling]);

  const handleSelectCall = (id: number) => {
    navigate(`/calls/${id}`);
  };

  const handleBack = () => {
    navigate('/calls');
  };

  const handleDelete = async (call: CallRecording) => {
    if (!confirm('Вы уверены, что хотите удалить эту запись?')) return;

    try {
      await deleteCall(call.id);
      toast.success('Запись удалена');
      if (currentCall?.id === call.id) {
        navigate('/calls');
      }
    } catch {
      toast.error('Не удалось удалить запись');
    }
  };

  const handleReprocess = async (call: CallRecording) => {
    try {
      await reprocessCall(call.id);
      toast.success('Переобработка запущена');
    } catch {
      toast.error('Не удалось запустить переобработку');
    }
  };

  const formatDuration = (seconds?: number) => {
    if (!seconds) return '—';
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };


  const getStatusIcon = (status: CallStatus) => {
    switch (status) {
      case 'done':
        return <CheckCircle size={16} className="text-green-400" />;
      case 'failed':
        return <XCircle size={16} className="text-red-400" />;
      case 'recording':
        return <div className="w-3 h-3 bg-red-500 rounded-full animate-pulse" />;
      default:
        return <Loader2 size={16} className="text-cyan-400 animate-spin" />;
    }
  };

  return (
    <div className="h-full w-full max-w-full flex overflow-hidden">
      {/* Sidebar - Call List */}
      <motion.div
        initial={{ opacity: 0, x: -20 }}
        animate={{ opacity: 1, x: 0 }}
        className={clsx(
          'flex-shrink-0 border-r border-white/5 flex flex-col glass',
          currentCall ? 'w-80' : 'w-full max-w-2xl'
        )}
      >
        {/* Header */}
        <div className="p-4 border-b border-white/5">
          <div className="flex items-center justify-between mb-4 gap-2">
            <h1 className={clsx(
              "font-semibold text-white flex-shrink-0",
              currentCall ? "text-base" : "text-xl"
            )}>
              {currentCall ? "Звонки" : "Записи звонков"}
            </h1>
            <div className="flex items-center gap-1 flex-shrink-0">
              <button
                onClick={() => setShowExternalLinksModal(true)}
                className={clsx(
                  "rounded-lg bg-purple-500/20 text-purple-400 hover:bg-purple-500/30 transition-colors flex items-center gap-2 whitespace-nowrap",
                  currentCall ? "p-2" : "px-4 py-2"
                )}
                title="Добавить внешнюю ссылку (Google Docs, Drive, медиа)"
              >
                <Link2 size={18} className="flex-shrink-0" />
                {!currentCall && <span className="hidden sm:inline">Внешняя ссылка</span>}
              </button>
              <button
                onClick={() => setShowRecorderModal(true)}
                className={clsx(
                  "rounded-lg bg-cyan-500/20 text-cyan-400 hover:bg-cyan-500/30 transition-colors flex items-center gap-2 whitespace-nowrap",
                  currentCall ? "p-2" : "px-4 py-2"
                )}
                title="Новая запись"
              >
                <Phone size={18} className="flex-shrink-0" />
                {!currentCall && <span className="hidden sm:inline">Новая запись</span>}
              </button>
            </div>
          </div>

          {/* Active Recording Status */}
          <AnimatePresence>
            {activeRecording && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
                className="bg-gradient-to-r from-cyan-500/20 to-purple-500/20 rounded-xl p-4 border border-cyan-500/30"
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-medium text-white">
                    {activeRecording.status === 'recording' ? 'Запись идёт' : 'Обработка...'}
                  </span>
                  <span className={clsx('text-xs px-2 py-0.5 rounded-full', CALL_STATUS_COLORS[activeRecording.status])}>
                    {CALL_STATUS_LABELS[activeRecording.status]}
                  </span>
                </div>

                {activeRecording.status === 'recording' && (
                  <div className="flex items-center gap-4">
                    <div className="flex items-center gap-2">
                      <div className="w-2 h-2 bg-red-500 rounded-full animate-pulse" />
                      <span className="text-sm text-white/60">
                        {formatDuration(activeRecording.duration)}
                      </span>
                    </div>
                    <button
                      onClick={stopRecording}
                      className="px-3 py-1 bg-red-500/20 text-red-400 rounded-lg text-sm hover:bg-red-500/30 transition-colors"
                    >
                      Остановить
                    </button>
                  </div>
                )}

                {/* Progress bar for processing states */}
                {['pending', 'processing', 'transcribing', 'analyzing'].includes(activeRecording.status) && (
                  <div className="space-y-2">
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-white/60">
                        {activeRecording.progressStage || 'Ожидание...'}
                      </span>
                      <span className="text-cyan-400 font-medium">
                        {activeRecording.progress || 0}%
                      </span>
                    </div>
                    <div className="h-2 bg-white/10 rounded-full overflow-hidden">
                      <motion.div
                        className="h-full bg-gradient-to-r from-cyan-500 to-purple-500"
                        initial={{ width: 0 }}
                        animate={{ width: `${activeRecording.progress || 0}%` }}
                        transition={{ duration: 0.3, ease: "easeOut" }}
                      />
                    </div>
                  </div>
                )}

                {activeRecording.error && (
                  <p className="text-sm text-red-400 mt-2">{activeRecording.error}</p>
                )}

                {(activeRecording.status === 'done' || activeRecording.status === 'failed') && (
                  <button
                    onClick={clearActiveRecording}
                    className="text-xs text-white/40 hover:text-white/60 mt-2"
                  >
                    Скрыть
                  </button>
                )}
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* Call List */}
        <div className="flex-1 overflow-y-auto p-4 space-y-2">
          {isLoading && accessibleCalls.length === 0 ? (
            <div className="flex items-center justify-center py-8">
              <div className="w-6 h-6 border-2 border-cyan-400 border-t-transparent rounded-full animate-spin" />
            </div>
          ) : accessibleCalls.length === 0 ? (
            <div className="text-center py-8 text-white/40">
              <Phone className="mx-auto mb-2" size={40} />
              <p>Нет записей звонков</p>
              <button
                onClick={() => setShowRecorderModal(true)}
                className="mt-4 px-4 py-2 bg-cyan-500/20 text-cyan-400 rounded-lg hover:bg-cyan-500/30 transition-colors"
              >
                Записать первый звонок
              </button>
            </div>
          ) : (
            accessibleCalls.map((call) => {
              const isSelected = currentCall?.id === call.id;

              return (
                <motion.div
                  key={call.id}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  onClick={() => handleSelectCall(call.id)}
                  className={clsx(
                    'p-4 rounded-xl cursor-pointer transition-all group',
                    isSelected
                      ? 'bg-cyan-500/20 border border-cyan-500/30'
                      : 'glass-light hover:bg-white/10'
                  )}
                >
                  <div className="flex items-start gap-3 overflow-hidden">
                    <div className={clsx(
                      'p-2 rounded-lg flex-shrink-0',
                      isSelected ? 'bg-cyan-500/30' : 'bg-white/10'
                    )}>
                      {call.source_type === 'upload' ? (
                        <Upload size={20} className={isSelected ? 'text-cyan-400' : 'text-white/60'} />
                      ) : call.source_type === 'meet' || call.source_type === 'zoom' ? (
                        <Video size={20} className={isSelected ? 'text-cyan-400' : 'text-white/60'} />
                      ) : (
                        <Phone size={20} className={isSelected ? 'text-cyan-400' : 'text-white/60'} />
                      )}
                    </div>

                    <div className="flex-1 min-w-0 overflow-hidden">
                      <div className="flex items-center gap-2 mb-1 overflow-hidden min-w-0">
                        <div className="flex-shrink-0">{getStatusIcon(call.status)}</div>
                        <span className="text-sm font-medium text-white truncate min-w-0">
                          {call.title || call.entity_name || 'Звонок ' + call.source_type.toUpperCase()}
                        </span>
                      </div>

                      <div className="flex items-center gap-3 text-xs text-white/40 overflow-hidden min-w-0 flex-wrap">
                        <span className="flex items-center gap-1 flex-shrink-0">
                          <Clock size={12} />
                          {formatDuration(call.duration_seconds)}
                        </span>
                        <span className="flex-shrink-0">{formatDate(call.created_at, 'long')}</span>
                        {call.entity_name && call.title && (
                          <span className="text-cyan-400/60 truncate min-w-0">• {call.entity_name}</span>
                        )}
                        {/* Show owner for non-owned calls */}
                        {!call.is_mine && call.owner_name && (
                          <span className="flex items-center gap-1 text-blue-400 flex-shrink-0" title={`Владелец: ${call.owner_name}`}>
                            <User size={12} />
                            <span className="text-white/40">Владелец:</span>
                            <span className="truncate max-w-[80px]">{call.owner_name}</span>
                          </span>
                        )}
                      </div>

                      {call.summary && (
                        <p className="text-xs text-white/50 mt-2 line-clamp-2 break-words overflow-hidden">{call.summary}</p>
                      )}
                    </div>

                    {/* Quick Actions */}
                    <div className="opacity-0 group-hover:opacity-100 transition-opacity flex gap-1 flex-shrink-0">
                      {call.status === 'failed' && canEdit(call) && (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleReprocess(call);
                          }}
                          className="p-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-white/60 flex-shrink-0"
                          title="Переобработать"
                        >
                          <RefreshCw size={14} />
                        </button>
                      )}
                      {canDelete(call) && (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDelete(call);
                          }}
                          className="p-1.5 rounded-lg bg-red-500/20 hover:bg-red-500/30 text-red-400 flex-shrink-0"
                          title="Удалить"
                        >
                          <Trash2 size={14} />
                        </button>
                      )}
                    </div>
                  </div>
                </motion.div>
              );
            })
          )}
        </div>
      </motion.div>

      {/* Main Content - Call Detail */}
      <AnimatePresence mode="wait">
        {currentCall && (
          <motion.div
            key={currentCall.id}
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 20 }}
            className="flex-1 flex flex-col"
          >
            {/* Header */}
            <div className="p-4 border-b border-white/5 flex items-center gap-4 overflow-hidden">
              <button
                onClick={handleBack}
                className="p-2 rounded-lg glass-light hover:bg-white/10 transition-colors flex-shrink-0"
              >
                <ChevronLeft size={20} className="text-white/60" />
              </button>
              <div className="flex-1 min-w-0 overflow-hidden">
                <h2 className="text-xl font-semibold text-white truncate">
                  {currentCall.title || currentCall.entity_name || 'Звонок ' + currentCall.source_type.toUpperCase()}
                </h2>
                <p className="text-sm text-white/60 truncate">
                  {formatDate(currentCall.created_at, 'long')} • {formatDuration(currentCall.duration_seconds)}
                  {currentCall.entity_name && currentCall.title && ` • ${currentCall.entity_name}`}
                </p>
              </div>
              <span className={clsx('px-3 py-1 rounded-full text-sm flex-shrink-0', CALL_STATUS_COLORS[currentCall.status])}>
                {CALL_STATUS_LABELS[currentCall.status]}
              </span>
            </div>

            {/* Detail Content */}
            <div className="flex-1 overflow-y-auto">
              <CallDetail call={currentCall} />
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Recorder Modal */}
      <AnimatePresence>
        {showRecorderModal && (
          <CallRecorderModal
            onClose={() => setShowRecorderModal(false)}
            onSuccess={() => {
              setShowRecorderModal(false);
              toast.success('Запись начата');
            }}
          />
        )}
      </AnimatePresence>

      {/* External Links Modal */}
      <ExternalLinksModal
        isOpen={showExternalLinksModal}
        onClose={() => setShowExternalLinksModal(false)}
        onSuccess={(callId) => {
          setShowExternalLinksModal(false);
          toast.success('Ссылка обработана');
          fetchCalls();
          navigate(`/calls/${callId}`);
        }}
      />
    </div>
  );
}
