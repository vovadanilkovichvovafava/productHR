/**
 * API Module - Re-exports from modular API structure
 *
 * This file provides backward compatibility by re-exporting everything
 * from the new modular API structure in /api/ folder.
 *
 * For new code, prefer importing directly from specific modules:
 * - import { login, getCurrentUser } from '@/services/api/auth'
 * - import { getChats, getMessages } from '@/services/api/chats'
 * - import { getEntities, createEntity } from '@/services/api/entities'
 * - import { getCalls, uploadCallRecording } from '@/services/api/calls'
 * - import { getVacancies, createVacancy } from '@/services/api/vacancies'
 * - import api from '@/services/api/client'
 */

// Re-export everything from the modular API
export * from './api/index';

// Default export is the axios instance
export { default } from './api/client';
