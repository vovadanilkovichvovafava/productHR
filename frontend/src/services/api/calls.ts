import type { CallRecording, CallStatus } from '@/types';
import api, { deduplicatedGet, debouncedMutation } from './client';

// ============================================================
// CALLS API
// ============================================================

export const getCalls = async (params?: {
  entity_id?: number;
  status?: CallStatus;
  limit?: number;
  offset?: number;
}): Promise<CallRecording[]> => {
  const searchParams: Record<string, string> = {};
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined) searchParams[key] = String(value);
    });
  }
  const { data } = await deduplicatedGet<CallRecording[]>('/calls', { params: searchParams });
  return data;
};

export const getCall = async (id: number): Promise<CallRecording> => {
  const { data } = await deduplicatedGet<CallRecording>(`/calls/${id}`);
  return data;
};

export const uploadCallRecording = async (
  file: File,
  entityId?: number
): Promise<{ id: number; status: string }> => {
  const formData = new FormData();
  formData.append('file', file);
  if (entityId) {
    formData.append('entity_id', String(entityId));
  }

  const response = await fetch('/api/calls/upload', {
    method: 'POST',
    credentials: 'include',
    body: formData,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Upload error' }));
    throw new Error(error.detail || 'Upload failed');
  }

  return response.json();
};

export const startCallBot = async (botData: {
  source_url: string;
  bot_name?: string;
  entity_id?: number;
}): Promise<{ id: number; status: string }> => {
  const { data } = await debouncedMutation<{ id: number; status: string }>('post', '/calls/start-bot', botData);
  return data;
};

export const getCallStatus = async (
  id: number,
  signal?: AbortSignal
): Promise<{
  status: CallStatus;
  duration_seconds?: number;
  error_message?: string;
  progress?: number;
  progress_stage?: string;
}> => {
  // Don't deduplicate status calls - they need fresh data each time
  const { data } = await api.get(`/calls/${id}/status`, { signal });
  return data;
};

export const stopCallRecording = async (id: number): Promise<void> => {
  await debouncedMutation<void>('post', `/calls/${id}/stop`);
};

export const deleteCall = async (id: number): Promise<void> => {
  await debouncedMutation<void>('delete', `/calls/${id}`);
};

export const linkCallToEntity = async (callId: number, entityId: number): Promise<void> => {
  await debouncedMutation<void>('post', `/calls/${callId}/link-entity/${entityId}`);
};

export const uploadTextCall = async (
  file: File,
  entityId?: number,
  title?: string
): Promise<{ id: number; status: string }> => {
  const formData = new FormData();
  formData.append('file', file);
  if (entityId) {
    formData.append('entity_id', String(entityId));
  }
  if (title) {
    formData.append('title', title);
  }

  const response = await fetch('/api/calls/upload-text', {
    method: 'POST',
    credentials: 'include',
    body: formData,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Upload error' }));
    throw new Error(error.detail || 'Upload failed');
  }

  return response.json();
};

export const reprocessCall = async (id: number): Promise<{ success: boolean; status: string }> => {
  const { data } = await debouncedMutation<{ success: boolean; status: string }>('post', `/calls/${id}/reprocess`);
  return data;
};

export const updateCall = async (
  id: number,
  callData: { title?: string; entity_id?: number }
): Promise<{ id: number; title?: string; entity_id?: number; entity_name?: string; success: boolean }> => {
  const { data } = await debouncedMutation<{ id: number; title?: string; entity_id?: number; entity_name?: string; success: boolean }>('patch', `/calls/${id}`, callData);
  return data;
};

// ============================================================
// EXTERNAL LINKS API
// ============================================================

export type ExternalLinkType = 'google_doc' | 'google_sheet' | 'google_form' | 'google_drive' | 'direct_media' | 'fireflies' | 'unknown';

export interface DetectLinkTypeResponse {
  url: string;
  link_type: ExternalLinkType;
  can_process: boolean;
  message?: string;
}

export interface ProcessURLResponse {
  call_id: number;
  status: string;
  message: string;
}

export const detectExternalLinkType = async (url: string): Promise<DetectLinkTypeResponse> => {
  const { data } = await deduplicatedGet<DetectLinkTypeResponse>('/external/detect-type', { params: { url } });
  return data;
};

export const processExternalURL = async (urlData: {
  url: string;
  title?: string;
  entity_id?: number;
}): Promise<ProcessURLResponse> => {
  const { data } = await debouncedMutation<ProcessURLResponse>('post', '/external/process-url', urlData);
  return data;
};

export const getExternalProcessingStatus = async (callId: number): Promise<{
  id: number;
  status: string;
  progress: number;
  progress_stage: string;
  error_message?: string;
  title?: string;
}> => {
  // Don't deduplicate status calls - they need fresh data each time
  const { data } = await api.get(`/external/status/${callId}`);
  return data;
};

export const getSupportedExternalTypes = async (): Promise<{
  supported_types: Array<{
    type: string;
    description: string;
    examples: string[];
  }>;
}> => {
  const { data } = await deduplicatedGet<{
    supported_types: Array<{
      type: string;
      description: string;
      examples: string[];
    }>;
  }>('/external/supported-types');
  return data;
};

// ============================================================
// CURRENCY API
// ============================================================

export interface ExchangeRatesResponse {
  rates: Record<string, number>;
  base_currency: string;
  last_updated: string | null;
  is_fallback: boolean;
  supported_currencies: string[];
}

export interface CurrencyConversionRequest {
  amount: number;
  from_currency: string;
  to_currency: string;
}

export interface CurrencyConversionResponse {
  original_amount: number;
  from_currency: string;
  to_currency: string;
  converted_amount: number;
  rate: number;
}

export interface SupportedCurrency {
  code: string;
  name: string;
  symbol: string;
}

export interface SupportedCurrenciesResponse {
  currencies: SupportedCurrency[];
  default_base: string;
}

/**
 * Get exchange rates for all supported currencies.
 * @param base - Base currency for rates (default: RUB)
 * @param refresh - Force refresh from API (bypass cache)
 * @returns Exchange rates relative to base currency
 */
export const getExchangeRates = async (
  base: string = 'RUB',
  refresh: boolean = false
): Promise<ExchangeRatesResponse> => {
  const params: Record<string, string> = { base };
  if (refresh) params.refresh = 'true';
  const { data } = await deduplicatedGet<ExchangeRatesResponse>('/currency/rates', { params });
  return data;
};

/**
 * Convert an amount between currencies using the API.
 * @param request - Conversion request with amount and currencies
 * @returns Converted amount and rate
 */
export const convertCurrencyApi = async (
  request: CurrencyConversionRequest
): Promise<CurrencyConversionResponse> => {
  // Currency conversion can be called frequently, no debounce needed
  const { data } = await api.post('/currency/convert', request);
  return data;
};

/**
 * Get list of supported currencies.
 * @returns List of supported currencies with names and symbols
 */
export const getSupportedCurrencies = async (): Promise<SupportedCurrenciesResponse> => {
  const { data } = await deduplicatedGet<SupportedCurrenciesResponse>('/currency/supported');
  return data;
};
