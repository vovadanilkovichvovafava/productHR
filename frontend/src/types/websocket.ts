/**
 * WebSocket event types and payloads
 */

import type { Entity, Chat } from './index';

// ============================================
// Base WebSocket Event Types
// ============================================

export type WebSocketEventType =
  | 'ping'
  | 'call.progress'
  | 'call.completed'
  | 'call.failed'
  | 'entity.created'
  | 'entity.updated'
  | 'entity.deleted'
  | 'chat.created'
  | 'chat.updated'
  | 'chat.deleted'
  | 'chat.message'
  | 'form.submission';

// ============================================
// Call Event Payloads
// ============================================

export interface CallProgressPayload {
  id: number;
  progress: number;
  progress_stage: string;
  status: string;
}

export interface CallCompletedPayload {
  id: number;
  title: string;
  status: 'done';
  has_summary: boolean;
  has_transcript: boolean;
  duration_seconds?: number;
  speaker_stats?: Record<string, unknown>;
  progress: number;
  progress_stage: string;
}

export interface CallFailedPayload {
  id: number;
  status: 'failed';
  error_message: string;
  progress: number;
  progress_stage: string;
}

// ============================================
// Entity Event Payloads
// ============================================

/**
 * Payload for entity.created event
 * Contains full Entity object
 */
export type EntityCreatedPayload = Entity;

/**
 * Payload for entity.updated event
 * Contains full Entity object with updated fields
 */
export type EntityUpdatedPayload = Entity;

/**
 * Payload for entity.deleted event
 */
export interface EntityDeletedPayload {
  id: number;
}

// ============================================
// Chat Event Payloads
// ============================================

/**
 * Payload for chat.created event
 * Contains full Chat object
 */
export type ChatCreatedPayload = Chat;

/**
 * Payload for chat.updated event
 * Contains full Chat object with updated fields
 */
export type ChatUpdatedPayload = Chat;

/**
 * Payload for chat.deleted event
 */
export interface ChatDeletedPayload {
  id: number;
}

/**
 * Payload for chat.message event
 * Sent when a new message is added to a chat
 */
export interface ChatMessagePayload {
  chat_id: number;
  message_count?: number;
}

export interface FormSubmissionPayload {
  entity_id: number;
  form_id: number;
  dispatch_id: number;
  form_title: string;
  candidate_name: string | null;
}

// ============================================
// WebSocket Event Union Types
// ============================================

export type WebSocketPayload =
  | CallProgressPayload
  | CallCompletedPayload
  | CallFailedPayload
  | EntityCreatedPayload
  | EntityUpdatedPayload
  | EntityDeletedPayload
  | ChatCreatedPayload
  | ChatUpdatedPayload
  | ChatDeletedPayload
  | ChatMessagePayload
  | FormSubmissionPayload;

// ============================================
// WebSocket Event Structure (Discriminated Union)
// ============================================

interface BaseWebSocketMessage {
  timestamp: string;
}

export interface PingMessage extends BaseWebSocketMessage {
  type: 'ping';
  payload: Record<string, never>;
}

export interface CallProgressMessage extends BaseWebSocketMessage {
  type: 'call.progress';
  payload: CallProgressPayload;
}

export interface CallCompletedMessage extends BaseWebSocketMessage {
  type: 'call.completed';
  payload: CallCompletedPayload;
}

export interface CallFailedMessage extends BaseWebSocketMessage {
  type: 'call.failed';
  payload: CallFailedPayload;
}

export interface EntityCreatedMessage extends BaseWebSocketMessage {
  type: 'entity.created';
  payload: EntityCreatedPayload;
}

export interface EntityUpdatedMessage extends BaseWebSocketMessage {
  type: 'entity.updated';
  payload: EntityUpdatedPayload;
}

export interface EntityDeletedMessage extends BaseWebSocketMessage {
  type: 'entity.deleted';
  payload: EntityDeletedPayload;
}

export interface ChatCreatedMessage extends BaseWebSocketMessage {
  type: 'chat.created';
  payload: ChatCreatedPayload;
}

export interface ChatUpdatedMessage extends BaseWebSocketMessage {
  type: 'chat.updated';
  payload: ChatUpdatedPayload;
}

export interface ChatDeletedMessage extends BaseWebSocketMessage {
  type: 'chat.deleted';
  payload: ChatDeletedPayload;
}

export interface ChatMessageMessage extends BaseWebSocketMessage {
  type: 'chat.message';
  payload: ChatMessagePayload;
}

export interface FormSubmissionMessage extends BaseWebSocketMessage {
  type: 'form.submission';
  payload: FormSubmissionPayload;
}

/**
 * Discriminated union of all WebSocket messages.
 * TypeScript will narrow the payload type based on the `type` field.
 */
export type WebSocketMessage =
  | PingMessage
  | CallProgressMessage
  | CallCompletedMessage
  | CallFailedMessage
  | EntityCreatedMessage
  | EntityUpdatedMessage
  | EntityDeletedMessage
  | ChatCreatedMessage
  | ChatUpdatedMessage
  | ChatDeletedMessage
  | ChatMessageMessage
  | FormSubmissionMessage;

// ============================================
// WebSocket Hook Options Types
// ============================================

export interface WebSocketEventHandlers {
  onCallProgress?: (data: CallProgressPayload) => void;
  onCallCompleted?: (data: CallCompletedPayload) => void;
  onCallFailed?: (data: CallFailedPayload) => void;
  onEntityCreated?: (data: EntityCreatedPayload) => void;
  onEntityUpdated?: (data: EntityUpdatedPayload) => void;
  onEntityDeleted?: (data: EntityDeletedPayload) => void;
  onChatCreated?: (data: ChatCreatedPayload) => void;
  onChatUpdated?: (data: ChatUpdatedPayload) => void;
  onChatDeleted?: (data: ChatDeletedPayload) => void;
  onChatMessage?: (data: ChatMessagePayload) => void;
  onFormSubmission?: (data: FormSubmissionPayload) => void;
  /**
   * Любое событие, включая те, для которых нет отдельного обработчика.
   * Нужен модулям вроде хаба доступов: заводить типизированный колбэк на
   * каждое новое событие — лишняя связанность, а ловить их как-то надо.
   */
  onEvent?: (message: { type: string; payload: Record<string, unknown> }) => void;
}

export interface WebSocketConnectionOptions {
  autoReconnect?: boolean;
  reconnectInterval?: number;
}

export type UseWebSocketOptions = WebSocketEventHandlers & WebSocketConnectionOptions;

// ============================================
// WebSocket Status Type
// ============================================

export type WebSocketStatus = 'connecting' | 'connected' | 'disconnected' | 'reconnecting' | 'error';
