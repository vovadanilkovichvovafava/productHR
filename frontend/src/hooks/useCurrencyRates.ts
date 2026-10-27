import { useState, useEffect, useCallback, useRef } from 'react';
import { getExchangeRates, type ExchangeRatesResponse } from '@/services/api';
import {
  type ExchangeRates,
  FALLBACK_RATES_TO_RUB,
  DEFAULT_BASE_CURRENCY,
  convertCurrency,
  convertToBaseCurrency,
  getSalaryForComparison,
} from '@/utils/currency';

/**
 * Cache TTL in milliseconds (24 hours)
 */
const CACHE_TTL_MS = 24 * 60 * 60 * 1000;

/**
 * Local storage key for cached rates
 */
const CACHE_KEY = 'hr_currency_rates';

interface CachedRates {
  rates: ExchangeRates;
  baseCurrency: string;
  timestamp: number;
  isFallback: boolean;
}

/**
 * Get cached rates from localStorage
 */
function getCachedRates(): CachedRates | null {
  try {
    const cached = localStorage.getItem(CACHE_KEY);
    if (!cached) return null;

    const data = JSON.parse(cached) as CachedRates;
    const elapsed = Date.now() - data.timestamp;

    // Return cached data if still valid
    if (elapsed < CACHE_TTL_MS) {
      return data;
    }

    return null;
  } catch {
    return null;
  }
}

/**
 * Save rates to localStorage cache
 */
function setCachedRates(
  rates: ExchangeRates,
  baseCurrency: string,
  isFallback: boolean
): void {
  try {
    const data: CachedRates = {
      rates,
      baseCurrency,
      timestamp: Date.now(),
      isFallback,
    };
    localStorage.setItem(CACHE_KEY, JSON.stringify(data));
  } catch {
    // localStorage might be full or disabled
    console.warn('Failed to cache exchange rates');
  }
}

/**
 * Return type for the useCurrencyRates hook
 */
export interface UseCurrencyRatesReturn {
  /** Exchange rates relative to base currency */
  rates: ExchangeRates;
  /** Base currency for the rates */
  baseCurrency: string;
  /** Whether rates are still loading */
  isLoading: boolean;
  /** Error message if fetching failed */
  error: string | null;
  /** Whether current rates are fallback (not from API) */
  isFallback: boolean;
  /** Last update timestamp */
  lastUpdated: Date | null;
  /** Force refresh rates from API */
  refresh: () => Promise<void>;
  /** Convert amount between currencies */
  convert: (amount: number, from: string, to: string) => number | null;
  /** Convert amount to base currency */
  toBaseCurrency: (amount: number, from: string) => number | null;
  /** Get comparable salary value in base currency */
  getComparableSalary: (
    salaryMin: number | undefined | null,
    salaryMax: number | undefined | null,
    currency: string
  ) => number;
}

/**
 * Hook for managing currency exchange rates with caching.
 *
 * Features:
 * - Automatic fetching on mount
 * - Local storage caching (24-hour TTL)
 * - Fallback rates when API is unavailable
 * - Conversion utilities
 *
 * @param baseCurrency - Base currency for rates (default: RUB)
 *
 * @example
 * ```tsx
 * const { rates, isLoading, convert, toBaseCurrency } = useCurrencyRates();
 *
 * // Convert 100 USD to RUB
 * const rubAmount = convert(100, 'USD', 'RUB');
 *
 * // Convert salary for comparison
 * const comparableSalary = getComparableSalary(50000, 80000, 'USD');
 * ```
 */
export function useCurrencyRates(
  baseCurrency: string = DEFAULT_BASE_CURRENCY
): UseCurrencyRatesReturn {
  const [rates, setRates] = useState<ExchangeRates>(FALLBACK_RATES_TO_RUB);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isFallback, setIsFallback] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [currentBaseCurrency, setCurrentBaseCurrency] = useState(baseCurrency);

  // Track if component is mounted
  const isMountedRef = useRef(true);

  /**
   * Fetch rates from API or cache
   */
  const fetchRates = useCallback(
    async (forceRefresh: boolean = false) => {
      setIsLoading(true);
      setError(null);

      // Check cache first (unless forcing refresh)
      if (!forceRefresh) {
        const cached = getCachedRates();
        if (cached && cached.baseCurrency === baseCurrency) {
          if (isMountedRef.current) {
            setRates(cached.rates);
            setIsFallback(cached.isFallback);
            setLastUpdated(new Date(cached.timestamp));
            setCurrentBaseCurrency(cached.baseCurrency);
            setIsLoading(false);
          }
          return;
        }
      }

      // Fetch from API
      try {
        const response: ExchangeRatesResponse = await getExchangeRates(
          baseCurrency,
          forceRefresh
        );

        if (isMountedRef.current) {
          setRates(response.rates);
          setIsFallback(response.is_fallback);
          setCurrentBaseCurrency(response.base_currency);
          setLastUpdated(
            response.last_updated ? new Date(response.last_updated) : new Date()
          );

          // Cache the rates
          setCachedRates(
            response.rates,
            response.base_currency,
            response.is_fallback
          );
        }
      } catch (err) {
        console.error('Failed to fetch exchange rates:', err);
        if (isMountedRef.current) {
          setError('Failed to load exchange rates');
          // Use fallback rates
          setRates(FALLBACK_RATES_TO_RUB);
          setIsFallback(true);
        }
      } finally {
        if (isMountedRef.current) {
          setIsLoading(false);
        }
      }
    },
    [baseCurrency]
  );

  // Fetch rates on mount and when base currency changes
  useEffect(() => {
    isMountedRef.current = true;
    fetchRates();

    return () => {
      isMountedRef.current = false;
    };
  }, [fetchRates]);

  /**
   * Force refresh rates from API
   */
  const refresh = useCallback(async () => {
    await fetchRates(true);
  }, [fetchRates]);

  /**
   * Convert amount between currencies
   */
  const convert = useCallback(
    (amount: number, from: string, to: string): number | null => {
      return convertCurrency(amount, from, to, rates);
    },
    [rates]
  );

  /**
   * Convert amount to base currency
   */
  const toBaseCurrency = useCallback(
    (amount: number, from: string): number | null => {
      return convertToBaseCurrency(amount, from, rates, currentBaseCurrency);
    },
    [rates, currentBaseCurrency]
  );

  /**
   * Get comparable salary value in base currency
   */
  const getComparableSalary = useCallback(
    (
      salaryMin: number | undefined | null,
      salaryMax: number | undefined | null,
      currency: string
    ): number => {
      return getSalaryForComparison(
        salaryMin,
        salaryMax,
        currency,
        rates,
        currentBaseCurrency
      );
    },
    [rates, currentBaseCurrency]
  );

  return {
    rates,
    baseCurrency: currentBaseCurrency,
    isLoading,
    error,
    isFallback,
    lastUpdated,
    refresh,
    convert,
    toBaseCurrency,
    getComparableSalary,
  };
}

export default useCurrencyRates;
