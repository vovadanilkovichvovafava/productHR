import { create } from 'zustand';
import type { CallRecording, CallStatus } from '@/types';
import * as api from '@/services/api';
import { logger } from '@/utils/logger';

interface ActiveRecording {
  id: number;
  status: CallStatus;
  duration: number;
  error?: string;
  progress?: number;
  progressStage?: string;
}

interface CallState {
  calls: CallRecording[];
  currentCall: CallRecording | null;
  activeRecording: ActiveRecording | null;
  isLoading: boolean;
  error: string | null;
  pollingInterval: ReturnType<typeof setInterval> | null;
  pollingAbortController: AbortController | null;
  useWebSocket: boolean; // Whether WebSocket is connected (disables polling)

  // Actions
  fetchCalls: (entityId?: number) => Promise<void>;
  fetchCall: (id: number) => Promise<void>;
  uploadCall: (file: File, entityId?: number) => Promise<number>;
  startBot: (url: string, botName: string, entityId?: number) => Promise<number>;
  stopRecording: () => Promise<void>;
  deleteCall: (id: number) => Promise<void>;
  reprocessCall: (id: number) => Promise<void>;
  updateCall: (id: number, data: { title?: string; entity_id?: number }) => Promise<void>;
  pollStatus: (id: number) => void;
  stopPolling: () => void;
  clearActiveRecording: () => void;
  clearError: () => void;
  // Cleanup method to prevent memory leaks
  cleanup: () => void;

  // WebSocket event handlers
  setWebSocketConnected: (connected: boolean) => void;
  handleCallProgress: (data: { id: number; progress: number; progress_stage: string; status: string }) => void;
  handleCallCompleted: (data: { id: number; title?: string; has_summary?: boolean; has_transcript?: boolean; duration_seconds?: number; speaker_stats?: Record<string, unknown> }) => void;
  handleCallFailed: (data: { id: number; error_message: string }) => void;
}

export const useCallStore = create<CallState>((set, get) => ({
  calls: [],
  currentCall: null,
  activeRecording: null,
  isLoading: false,
  error: null,
  pollingInterval: null,
  pollingAbortController: null,
  useWebSocket: false,

  fetchCalls: async (entityId) => {
    set({ isLoading: true, error: null });
    try {
      const calls = await api.getCalls({ entity_id: entityId });
      set({ calls, isLoading: false });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch calls';
      set({ error: message, isLoading: false });
    }
  },

  fetchCall: async (id) => {
    set({ isLoading: true, error: null });
    try {
      const call = await api.getCall(id);
      set({ currentCall: call, isLoading: false });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch call';
      set({ error: message, isLoading: false });
    }
  },

  uploadCall: async (file, entityId) => {
    set({ isLoading: true, error: null });
    try {
      const result = await api.uploadCallRecording(file, entityId);
      set({
        activeRecording: { id: result.id, status: 'processing' as CallStatus, duration: 0 },
        isLoading: false
      });
      get().pollStatus(result.id);
      return result.id;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to upload call';
      set({ error: message, isLoading: false });
      throw err;
    }
  },

  startBot: async (url, botName, entityId) => {
    set({ isLoading: true, error: null });
    try {
      const result = await api.startCallBot({ source_url: url, bot_name: botName, entity_id: entityId });
      set({
        activeRecording: { id: result.id, status: (result.status || 'recording') as CallStatus, duration: 0 },
        isLoading: false
      });
      get().pollStatus(result.id);
      // Also fetch the full call to update currentCall
      get().fetchCall(result.id);
      return result.id;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to start recording bot';
      set({ error: message, isLoading: false });
      throw err;
    }
  },

  stopRecording: async () => {
    const { activeRecording } = get();
    if (!activeRecording) return;

    try {
      await api.stopCallRecording(activeRecording.id);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to stop recording';
      set({ error: message });
    }
  },

  deleteCall: async (id) => {
    set({ isLoading: true, error: null });
    try {
      await api.deleteCall(id);
      set((state) => ({
        calls: state.calls.filter((c) => c.id !== id),
        currentCall: state.currentCall?.id === id ? null : state.currentCall,
        isLoading: false
      }));
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to delete call';
      set({ error: message, isLoading: false });
      throw err;
    }
  },

  reprocessCall: async (id) => {
    set({ isLoading: true, error: null });
    try {
      await api.reprocessCall(id);
      set({
        activeRecording: { id, status: 'processing' as CallStatus, duration: 0 },
        isLoading: false
      });
      get().pollStatus(id);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to reprocess call';
      set({ error: message, isLoading: false });
      throw err;
    }
  },

  updateCall: async (id, data) => {
    set({ isLoading: true, error: null });
    try {
      const result = await api.updateCall(id, data);
      // Update current call if it matches
      set((state) => ({
        currentCall: state.currentCall?.id === id
          ? { ...state.currentCall, title: result.title, entity_id: result.entity_id, entity_name: result.entity_name }
          : state.currentCall,
        calls: state.calls.map((c) =>
          c.id === id ? { ...c, title: result.title, entity_id: result.entity_id, entity_name: result.entity_name } : c
        ),
        isLoading: false
      }));
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to update call';
      set({ error: message, isLoading: false });
      throw err;
    }
  },

  pollStatus: (id) => {
    // Don't poll if WebSocket is connected - real-time updates will come via WebSocket
    if (get().useWebSocket) {
      logger.log('[CallStore] WebSocket connected, skipping polling');
      return;
    }

    // Clear any existing polling
    get().stopPolling();

    // Create new AbortController for this polling session
    const abortController = new AbortController();

    // Request notification permission
    if ('Notification' in window && Notification.permission === 'default') {
      Notification.requestPermission();
    }

    const interval = setInterval(async () => {
      // Stop polling if WebSocket became connected
      if (get().useWebSocket) {
        get().stopPolling();
        return;
      }
      try {
        const status = await api.getCallStatus(id, abortController.signal);

        const prevStatus = get().activeRecording?.status;
        set({
          activeRecording: {
            id,
            status: status.status,
            duration: status.duration_seconds || 0,
            error: status.error_message,
            progress: status.progress || 0,
            progressStage: status.progress_stage || ''
          }
        });

        // If status changed, also refetch the full call data
        if (prevStatus !== status.status) {
          get().fetchCall(id);
        }

        // Stop polling when done or failed
        if (status.status === 'done' || status.status === 'failed') {
          get().stopPolling();
          // Refresh calls list and current call
          get().fetchCalls();
          get().fetchCall(id);

          // Send browser notification if page is hidden
          if (document.hidden && 'Notification' in window && Notification.permission === 'granted') {
            const title = status.status === 'done' ? 'Запись обработана' : 'Ошибка обработки';
            const body = status.status === 'done'
              ? 'Транскрипт и анализ готовы'
              : (status.error_message || 'Не удалось обработать запись');
            new Notification(title, { body, icon: '/favicon.ico' });
          }
        }
      } catch (err) {
        // Only stop polling if it's not an abort error (which is expected on cleanup)
        if (err instanceof Error && err.name !== 'AbortError' && err.name !== 'CanceledError') {
          get().stopPolling();
        }
      }
    }, 3000); // Poll every 3 seconds

    set({ pollingInterval: interval, pollingAbortController: abortController });
  },

  stopPolling: () => {
    const { pollingInterval, pollingAbortController } = get();

    // Abort any in-flight requests
    if (pollingAbortController) {
      pollingAbortController.abort();
    }

    // Clear the interval
    if (pollingInterval) {
      clearInterval(pollingInterval);
    }

    set({ pollingInterval: null, pollingAbortController: null });
  },

  clearActiveRecording: () => {
    get().stopPolling();
    set({ activeRecording: null });
  },

  clearError: () => set({ error: null }),

  // Cleanup all polling and abort controllers to prevent memory leaks
  cleanup: () => {
    const { pollingInterval, pollingAbortController } = get();

    // Abort any in-flight requests
    if (pollingAbortController) {
      pollingAbortController.abort();
    }

    // Clear the interval
    if (pollingInterval) {
      clearInterval(pollingInterval);
    }

    // Reset state
    set({
      pollingInterval: null,
      pollingAbortController: null,
      activeRecording: null,
      useWebSocket: false,
    });
  },

  // WebSocket event handlers
  setWebSocketConnected: (connected) => {
    set({ useWebSocket: connected });
    // Stop polling when WebSocket is connected
    if (connected) {
      get().stopPolling();
    }
  },

  handleCallProgress: (data) => {
    const { activeRecording } = get();

    // Update activeRecording if this is the call we're tracking
    if (activeRecording?.id === data.id || !activeRecording) {
      set({
        activeRecording: {
          id: data.id,
          status: data.status as CallStatus,
          duration: 0,
          progress: data.progress,
          progressStage: data.progress_stage
        }
      });
    }

    logger.log(`[WebSocket] Call ${data.id} progress: ${data.progress}% - ${data.progress_stage}`);
  },

  handleCallCompleted: (data) => {
    const { activeRecording } = get();

    // Update activeRecording
    if (activeRecording?.id === data.id) {
      set({
        activeRecording: {
          ...activeRecording,
          status: 'done' as CallStatus,
          progress: 100,
          progressStage: 'Готово',
          duration: data.duration_seconds || 0
        }
      });
    }

    // Refresh calls list and current call
    get().fetchCalls();
    get().fetchCall(data.id);

    // Send browser notification if page is hidden
    if (document.hidden && 'Notification' in window && Notification.permission === 'granted') {
      const title = data.title || 'Запись';
      new Notification('Запись обработана', {
        body: `"${title}" - транскрипт и анализ готовы`,
        icon: '/favicon.ico'
      });
    }

    logger.log(`[WebSocket] Call ${data.id} completed`);
  },

  handleCallFailed: (data) => {
    const { activeRecording } = get();

    // Update activeRecording
    if (activeRecording?.id === data.id) {
      set({
        activeRecording: {
          ...activeRecording,
          status: 'failed' as CallStatus,
          progress: 0,
          progressStage: 'Ошибка',
          error: data.error_message
        }
      });
    }

    // Refresh calls list
    get().fetchCalls();
    get().fetchCall(data.id);

    // Send browser notification if page is hidden
    if (document.hidden && 'Notification' in window && Notification.permission === 'granted') {
      new Notification('Ошибка обработки', {
        body: data.error_message || 'Не удалось обработать запись',
        icon: '/favicon.ico'
      });
    }

    logger.log(`[WebSocket] Call ${data.id} failed: ${data.error_message}`);
  }
}));
