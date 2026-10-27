import { deduplicatedGet } from './client';

// «Расход ИИ» (21.10.2026): сколько и на что уходит Claude. Пишет сервер на
// каждый вызов (services/ai_usage.py), здесь только сводка — владельцу и админам.

export interface AiUsageRow {
  caller: string | null;
  label: string;
  model: string | null;
  calls: number;
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cost_usd: number;
  errors: number;
}

export interface AiUsageSummary {
  days: number;
  total_cost_usd: number;
  total_calls: number;
  by_caller: AiUsageRow[];
  by_day: Array<{ day: string; calls: number; cost_usd: number }>;
  last_errors: Array<{ at: string | null; label: string; error: string | null }>;
}

export const getAiUsage = async (days: number): Promise<AiUsageSummary> => {
  const { data } = await deduplicatedGet<AiUsageSummary>('/ai-usage', { params: { days } });
  return data;
};
