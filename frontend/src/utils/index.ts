/**
 * Utility functions barrel export.
 */

export {
  CURRENCY_SYMBOLS,
  CURRENCY_OPTIONS,
  getCurrencySymbol,
  formatCurrency,
  formatSalary,
  getCurrencyDropdownOptions,
  SALARY_INPUT_CURRENCIES,
} from './currency';
export type { CurrencyCode } from './currency';

export {
  getLocalStorage,
  setLocalStorage,
  removeLocalStorage,
} from './localStorage';

export {
  formatDate,
  formatRelativeTime,
  isToday,
  isPast,
} from './date';
export type { DateFormatType } from './date';

/**
 * Safely extract error detail message from an API error response.
 * FastAPI 422 responses return `detail` as an array of objects ({type, loc, msg, input, ctx}),
 * which crashes React if rendered directly (React error #31).
 */
export function getErrorDetail(error: unknown, fallback: string): string {
  const err = error as { response?: { data?: { detail?: unknown; error?: string; message?: string } }; message?: string };
  const detail = err?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0];
    if (typeof first === 'object' && first !== null && 'msg' in first) {
      return String(first.msg);
    }
    // Pydantic v2 format
    if (typeof first === 'string') return first;
  }
  // Fallback to other error formats
  if (typeof err?.response?.data?.error === 'string') return err.response.data.error;
  if (typeof err?.response?.data?.message === 'string') return err.response.data.message;
  if (typeof err?.message === 'string' && err.message !== 'Request failed with status code 500') return err.message;
  return fallback;
}
