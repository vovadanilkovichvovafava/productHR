import { useEffect, useRef, useCallback, useState } from 'react';
import { useAuthStore } from '@/stores/authStore';
import { logger } from '@/utils/logger';
import type {
  WebSocketStatus,
  WebSocketMessage,
  UseWebSocketOptions,
  CallProgressPayload,
  CallCompletedPayload,
  CallFailedPayload
} from '@/types/websocket';

// Re-export types for backwards compatibility
export type { WebSocketStatus };
export type { CallProgressPayload as CallProgressEvent };
export type { CallCompletedPayload as CallCompletedEvent };
export type { CallFailedPayload as CallFailedEvent };

// Re-export WebSocketEvent for backwards compatibility
export interface WebSocketEvent {
  type: string;
  payload: Record<string, unknown>;
  timestamp: string;
}

// Exponential backoff configuration
const INITIAL_RECONNECT_DELAY = 1000;  // 1 second
const MAX_RECONNECT_DELAY = 60000;     // 60 seconds
const BACKOFF_MULTIPLIER = 2;
const JITTER_FACTOR = 0.3;             // ±30% randomization

/**
 * Calculate reconnection delay with exponential backoff and jitter.
 * This prevents thundering herd when many clients reconnect simultaneously.
 */
function calculateBackoffDelay(attempt: number): number {
  const baseDelay = Math.min(
    INITIAL_RECONNECT_DELAY * Math.pow(BACKOFF_MULTIPLIER, attempt),
    MAX_RECONNECT_DELAY
  );
  // Add jitter: ±30% randomization
  const jitter = baseDelay * JITTER_FACTOR * (Math.random() * 2 - 1);
  return Math.round(baseDelay + jitter);
}

export function useWebSocket(options: UseWebSocketOptions = {}) {
  const {
    onCallProgress,
    onCallCompleted,
    onCallFailed,
    onEntityCreated,
    onEntityUpdated,
    onEntityDeleted,
    onChatCreated,
    onChatUpdated,
    onChatDeleted,
    onChatMessage,
    onFormSubmission,
    onEvent,
    autoReconnect = true,
    reconnectInterval = 3000,  // Kept for backwards compatibility, but overridden by backoff
  } = options;

  const [status, setStatus] = useState<WebSocketStatus>('disconnected');
  const [error, setError] = useState<Error | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout>>();
  const isManualClose = useRef(false);
  const reconnectAttemptRef = useRef(0);
  const lastEventTimestampRef = useRef<string | null>(null);

  const { user } = useAuthStore();

  const connect = useCallback(() => {
    // Don't connect if no user is logged in
    if (!user) {
      return;
    }

    // Close existing connection
    if (wsRef.current) {
      isManualClose.current = true;
      wsRef.current.close();
    }

    setStatus('connecting');
    setError(null);
    isManualClose.current = false;

    // Build WebSocket URL with optional since_timestamp for state sync
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    // Token is in httpOnly cookie, so we need to get it from a special endpoint
    // For now, we'll use the cookie-based auth - backend will read cookie from WebSocket handshake
    let wsUrl = `${protocol}//${host}/ws`;

    // STATE SYNC: If reconnecting, request missed events since last received timestamp
    if (lastEventTimestampRef.current) {
      wsUrl += `?since=${encodeURIComponent(lastEventTimestampRef.current)}`;
    }

    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        logger.log('[WebSocket] Connected');
        setStatus('connected');
        setError(null);
        // Reset reconnect attempt counter on successful connection
        reconnectAttemptRef.current = 0;
      };

      ws.onclose = (event) => {
        logger.log('[WebSocket] Disconnected:', event.code, event.reason);
        wsRef.current = null;

        if (isManualClose.current) {
          setStatus('disconnected');
          reconnectAttemptRef.current = 0;
          return;
        }

        // Auto-reconnect if enabled and not manually closed
        if (autoReconnect && user) {
          setStatus('reconnecting');

          // Calculate delay with exponential backoff and jitter
          const delay = calculateBackoffDelay(reconnectAttemptRef.current);
          reconnectAttemptRef.current += 1;

          logger.log(`[WebSocket] Reconnecting in ${delay}ms (attempt ${reconnectAttemptRef.current})`);

          reconnectTimeoutRef.current = setTimeout(() => {
            logger.log('[WebSocket] Attempting to reconnect...');
            connect();
          }, delay);
        } else {
          setStatus('disconnected');
        }
      };

      ws.onerror = (event) => {
        logger.error('[WebSocket] Error:', event);
        setError(new Error('WebSocket connection error'));
        setStatus('error');
      };

      ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data) as WebSocketMessage;
          logger.log('[WebSocket] Message:', message.type, message.payload);

          // STATE SYNC: Track last event timestamp for reconnection
          if ('timestamp' in message && message.timestamp) {
            lastEventTimestampRef.current = message.timestamp as string;
          }

          // Общий колбэк — до разбора по типам: модули с собственными
          // событиями (хаб доступов) подписываются через него, не расширяя
          // union и не заводя колбэк на каждое новое имя.
          onEvent?.(message as unknown as { type: string; payload: Record<string, unknown> });

          // Handle different event types using discriminated union
          // TypeScript narrows payload type automatically based on message.type
          switch (message.type) {
            case 'ping':
              // Ignore ping events
              break;

            case 'call.progress':
              onCallProgress?.(message.payload);
              break;

            case 'call.completed':
              onCallCompleted?.(message.payload);
              break;

            case 'call.failed':
              onCallFailed?.(message.payload);
              break;

            case 'entity.created':
              onEntityCreated?.(message.payload);
              break;

            case 'entity.updated':
              onEntityUpdated?.(message.payload);
              break;

            case 'entity.deleted':
              onEntityDeleted?.(message.payload);
              break;

            case 'chat.created':
              onChatCreated?.(message.payload);
              break;

            case 'chat.updated':
              onChatUpdated?.(message.payload);
              break;

            case 'chat.deleted':
              onChatDeleted?.(message.payload);
              break;

            case 'chat.message':
              onChatMessage?.(message.payload);
              break;

            case 'form.submission':
              onFormSubmission?.(message.payload);
              break;

            default: {
              // Exhaustiveness check - TypeScript will error if we miss a case
              const _exhaustive: never = message;
              logger.log('[WebSocket] Unknown event type:', (_exhaustive as WebSocketMessage).type);
            }
          }
        } catch (err) {
          logger.error('[WebSocket] Failed to parse message:', err);
        }
      };
    } catch (err) {
      logger.error('[WebSocket] Failed to create connection:', err);
      setError(err instanceof Error ? err : new Error('Failed to connect'));
      setStatus('error');
    }
  }, [user, autoReconnect, reconnectInterval, onCallProgress, onCallCompleted, onCallFailed, onEntityCreated, onEntityUpdated, onEntityDeleted, onChatCreated, onChatUpdated, onChatDeleted, onChatMessage, onFormSubmission]);

  const disconnect = useCallback(() => {
    isManualClose.current = true;
    reconnectAttemptRef.current = 0;  // Reset backoff on manual disconnect
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
    }
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setStatus('disconnected');
  }, []);

  // Connect when user logs in, disconnect when logs out
  useEffect(() => {
    if (user) {
      connect();
    } else {
      disconnect();
    }

    return () => {
      disconnect();
    };
  }, [user, connect, disconnect]);

  return {
    status,
    isConnected: status === 'connected',
    error,
    connect,
    disconnect,
  };
}
