import type {
  Chat, Message, Participant, CriteriaPreset,
  ChatCriteria, AIConversation, AnalysisResult, Stats
} from '@/types';
import { deduplicatedGet, debouncedMutation, createStreamController } from './client';

// ============================================================
// CHATS API
// ============================================================

export const getChats = async (): Promise<Chat[]> => {
  const { data } = await deduplicatedGet<Chat[]>('/chats');
  return data;
};

export const getChat = async (id: number): Promise<Chat> => {
  const { data } = await deduplicatedGet<Chat>(`/chats/${id}`);
  return data;
};

export const updateChat = async (id: number, updates: {
  custom_name?: string;
  chat_type?: string;
  entity_id?: number;
  is_active?: boolean;
}): Promise<Chat> => {
  const { data } = await debouncedMutation<Chat>('patch', `/chats/${id}`, updates);
  return data;
};

export const deleteChat = async (id: number): Promise<void> => {
  await debouncedMutation<void>('delete', `/chats/${id}`);
};

export const getDeletedChats = async (): Promise<Chat[]> => {
  const { data } = await deduplicatedGet<Chat[]>('/chats/deleted/list');
  return data;
};

export const restoreChat = async (id: number): Promise<void> => {
  await debouncedMutation<void>('post', `/chats/${id}/restore`);
};

export const permanentDeleteChat = async (id: number): Promise<void> => {
  await debouncedMutation<void>('delete', `/chats/${id}/permanent`);
};

// ============================================================
// MESSAGES API
// ============================================================

export const getMessages = async (chatId: number, page = 1, limit = 500, contentType?: string): Promise<Message[]> => {
  const params: Record<string, string> = { page: String(page), limit: String(limit) };
  if (contentType) params.content_type = contentType;
  const { data } = await deduplicatedGet<Message[]>(`/chats/${chatId}/messages`, { params });
  return data;
};

export const getParticipants = async (chatId: number): Promise<Participant[]> => {
  const { data } = await deduplicatedGet<Participant[]>(`/chats/${chatId}/participants`);
  return data;
};

export const transcribeMessage = async (messageId: number): Promise<{ success: boolean; transcription: string; message_id: number }> => {
  const { data } = await debouncedMutation<{ success: boolean; transcription: string; message_id: number }>('post', `/chats/messages/${messageId}/transcribe`);
  return data;
};

// ============================================================
// CRITERIA API
// ============================================================

export const getCriteriaPresets = async (): Promise<CriteriaPreset[]> => {
  const { data } = await deduplicatedGet<CriteriaPreset[]>('/criteria/presets');
  return data;
};

export const createCriteriaPreset = async (preset: Omit<CriteriaPreset, 'id' | 'created_at' | 'created_by'>): Promise<CriteriaPreset> => {
  const { data } = await debouncedMutation<CriteriaPreset>('post', '/criteria/presets', preset);
  return data;
};

export const updateCriteriaPreset = async (id: number, preset: Omit<CriteriaPreset, 'id' | 'created_at' | 'created_by'>): Promise<CriteriaPreset> => {
  const { data } = await debouncedMutation<CriteriaPreset>('put', `/criteria/presets/${id}`, preset);
  return data;
};

export const deleteCriteriaPreset = async (id: number): Promise<void> => {
  await debouncedMutation<void>('delete', `/criteria/presets/${id}`);
};

export const getChatCriteria = async (chatId: number): Promise<ChatCriteria> => {
  const { data } = await deduplicatedGet<ChatCriteria>(`/criteria/chats/${chatId}`);
  return data;
};

export const updateChatCriteria = async (chatId: number, criteria: { name: string; description: string; weight: number; category: string }[]): Promise<ChatCriteria> => {
  const { data } = await debouncedMutation<ChatCriteria>('put', `/criteria/chats/${chatId}`, { criteria });
  return data;
};

// Default criteria by chat type
export interface DefaultCriteriaResponse {
  chat_type: string;
  criteria: { name: string; description: string; weight: number; category: string }[];
  is_custom: boolean;
  preset_id: number | null;
}

export const getDefaultCriteria = async (chatType: string): Promise<DefaultCriteriaResponse> => {
  const { data } = await deduplicatedGet<DefaultCriteriaResponse>(`/criteria/defaults/${chatType}`);
  return data;
};

export const setDefaultCriteria = async (
  chatType: string,
  criteria: { name: string; description: string; weight: number; category: string }[]
): Promise<DefaultCriteriaResponse> => {
  const { data } = await debouncedMutation<DefaultCriteriaResponse>('put', `/criteria/defaults/${chatType}`, { criteria });
  return data;
};

export const resetDefaultCriteria = async (chatType: string): Promise<void> => {
  await debouncedMutation<void>('delete', `/criteria/defaults/${chatType}`);
};

export const seedUniversalPresets = async (): Promise<{ message: string; created: string[] }> => {
  const { data } = await debouncedMutation<{ message: string; created: string[] }>('post', '/criteria/presets/seed-universal');
  return data;
};

// ============================================================
// AI API
// ============================================================

export const getAIHistory = async (chatId: number): Promise<AIConversation> => {
  const { data } = await deduplicatedGet<AIConversation>(`/chats/${chatId}/ai/history`);
  return data;
};

export const clearAIHistory = async (chatId: number): Promise<void> => {
  await debouncedMutation<void>('delete', `/chats/${chatId}/ai/history`);
};

export const getAnalysisHistory = async (chatId: number): Promise<AnalysisResult[]> => {
  const { data } = await deduplicatedGet<AnalysisResult[]>(`/chats/${chatId}/analysis-history`);
  return data;
};

// ============================================================
// STATS API
// ============================================================

export const getStats = async (): Promise<Stats> => {
  const { data } = await deduplicatedGet<Stats>('/stats');
  return data;
};

// ============================================================
// STREAMING HELPERS
// ============================================================

export interface StreamOptions {
  onChunk: (chunk: string) => void;
  onDone: () => void;
  onError?: (error: Error) => void;
  signal?: AbortSignal;
}

/**
 * Internal helper to process SSE stream
 */
const processSSEStream = async (
  reader: ReadableStreamDefaultReader<Uint8Array>,
  onChunk: (chunk: string) => void,
  onDone: () => void,
  signal?: AbortSignal
): Promise<void> => {
  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      // Check if aborted
      if (signal?.aborted) {
        await reader.cancel();
        return;
      }

      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');

      // Keep the last incomplete line in buffer
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = line.slice(6);
          if (data === '[DONE]') {
            onDone();
          } else {
            try {
              const parsed = JSON.parse(data);
              if (parsed.content) {
                onChunk(parsed.content);
              }
            } catch {
              // Ignore parse errors for incomplete chunks
            }
          }
        }
      }
    }

    // Process remaining buffer
    if (buffer.startsWith('data: ')) {
      const data = buffer.slice(6);
      if (data === '[DONE]') {
        onDone();
      } else {
        try {
          const parsed = JSON.parse(data);
          if (parsed.content) {
            onChunk(parsed.content);
          }
        } catch {
          // Ignore parse errors
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
};

/**
 * Stream AI message with AbortController support
 * Returns a cleanup function to abort the request
 */
export const streamAIMessage = async (
  chatId: number,
  message: string,
  onChunk: (chunk: string) => void,
  onDone: () => void,
  signal?: AbortSignal
): Promise<() => void> => {
  const streamId = `ai-message-${chatId}-${Date.now()}`;
  const { controller, cleanup } = createStreamController(streamId);

  // Use provided signal or create our own
  const effectiveSignal = signal || controller.signal;

  try {
    const response = await fetch(`/api/chats/${chatId}/ai/message`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      credentials: 'include',
      body: JSON.stringify({ message }),
      signal: effectiveSignal,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Server error' }));
      throw new Error(error.detail || 'AI error');
    }

    const reader = response.body?.getReader();
    if (!reader) {
      cleanup();
      return cleanup;
    }

    // Process stream in background
    processSSEStream(reader, onChunk, onDone, effectiveSignal)
      .catch((error) => {
        if (error.name !== 'AbortError') {
          console.error('Stream processing error:', error);
        }
      })
      .finally(cleanup);

    return cleanup;
  } catch (error) {
    cleanup();
    if ((error as Error).name === 'AbortError') {
      console.debug('AI message stream aborted');
      return cleanup;
    }
    throw error;
  }
};

/**
 * Stream quick action with AbortController support
 * Returns a cleanup function to abort the request
 */
export const streamQuickAction = async (
  chatId: number,
  action: string,
  onChunk: (chunk: string) => void,
  onDone: () => void,
  signal?: AbortSignal
): Promise<() => void> => {
  const streamId = `quick-action-${chatId}-${action}-${Date.now()}`;
  const { controller, cleanup } = createStreamController(streamId);

  // Use provided signal or create our own
  const effectiveSignal = signal || controller.signal;

  try {
    const response = await fetch(`/api/chats/${chatId}/ai/message`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      credentials: 'include',
      body: JSON.stringify({ quick_action: action }),
      signal: effectiveSignal,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Server error' }));
      throw new Error(error.detail || 'AI error');
    }

    const reader = response.body?.getReader();
    if (!reader) {
      cleanup();
      return cleanup;
    }

    // Process stream in background
    processSSEStream(reader, onChunk, onDone, effectiveSignal)
      .catch((error) => {
        if (error.name !== 'AbortError') {
          console.error('Stream processing error:', error);
        }
      })
      .finally(cleanup);

    return cleanup;
  } catch (error) {
    cleanup();
    if ((error as Error).name === 'AbortError') {
      console.debug('Quick action stream aborted');
      return cleanup;
    }
    throw error;
  }
};

// ============================================================
// REPORTS API
// ============================================================

export const downloadReport = async (chatId: number, reportType: string, format: string): Promise<Blob> => {
  const response = await fetch(`/api/chats/${chatId}/report`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    credentials: 'include',
    body: JSON.stringify({ report_type: reportType, format }),
  });

  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }

  return response.blob();
};

// ============================================================
// IMPORT API
// ============================================================

export interface ImportResult {
  success: boolean;
  imported: number;
  skipped: number;
  errors: string[];
  total_errors: number;
}

// Generate UUID for import tracking
const generateImportId = () => {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = Math.random() * 16 | 0;
    const v = c === 'x' ? r : (r & 0x3 | 0x8);
    return v.toString(16);
  });
};

export const importTelegramHistory = async (
  chatId: number,
  file: File,
  autoProcess: boolean = true,
  importId?: string
): Promise<ImportResult> => {
  const formData = new FormData();
  formData.append('file', file);

  let url = `/api/chats/${chatId}/import?auto_process=${autoProcess}`;
  if (importId) {
    url += `&import_id=${importId}`;
  }

  const response = await fetch(url, {
    method: 'POST',
    credentials: 'include',
    body: formData,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Import error' }));
    throw new Error(error.detail || 'Import error');
  }

  return response.json();
};

// Import progress tracking
export interface ImportProgress {
  status: 'starting' | 'processing' | 'completed' | 'error' | 'not_found';
  phase?: 'reading_file' | 'importing' | 'processing_media' | 'done';
  current: number;
  total: number;
  imported: number;
  skipped: number;
  current_file?: string | null;
  error?: string;
}

export const getImportProgress = async (chatId: number, importId: string): Promise<ImportProgress> => {
  const response = await fetch(`/api/chats/${chatId}/import/progress/${importId}`, {
    credentials: 'include',
  });
  return response.json();
};

export { generateImportId };

// Cleanup badly imported messages
export interface CleanupResult {
  success: boolean;
  deleted: number;
  mode?: string;
}

export type CleanupMode = 'bad' | 'today' | 'all_imported' | 'all' | 'clear_all' | 'duplicates';

export const cleanupBadImport = async (chatId: number, mode: CleanupMode = 'bad'): Promise<CleanupResult> => {
  const response = await fetch(`/api/chats/${chatId}/import/cleanup?mode=${mode}`, {
    method: 'DELETE',
    credentials: 'include',
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Cleanup error' }));
    throw new Error(error.detail || 'Cleanup error');
  }

  return response.json();
};

// ============================================================
// MEDIA TRANSCRIPTION API
// ============================================================

export interface TranscribeAllResult {
  success: boolean;
  transcribed: number;
  total_found: number;
  errors: number;
}

export const transcribeAllMedia = async (chatId: number): Promise<TranscribeAllResult> => {
  const response = await fetch(`/api/chats/${chatId}/transcribe-all`, {
    method: 'POST',
    credentials: 'include',
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Transcription error' }));
    throw new Error(error.detail || 'Transcription error');
  }

  return response.json();
};

export interface RepairVideoResult {
  repaired: number;
  total: number;
  message?: string;
}

export const repairVideoNotes = async (chatId: number, file: File): Promise<RepairVideoResult> => {
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch(`/api/chats/${chatId}/repair-video-notes`, {
    method: 'POST',
    credentials: 'include',
    body: formData,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Video repair error' }));
    throw new Error(error.detail || 'Video repair error');
  }

  return response.json();
};
