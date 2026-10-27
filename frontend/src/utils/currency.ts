/**
 * Currency formatting and conversion utilities for the HR-bot application.
 * Provides consistent salary and currency display across the frontend.
 */

/**
 * Map of currency codes to their symbols.
 */
export const CURRENCY_SYMBOLS: Record<string, string> = {
  RUB: '\u20bd',  // ₽
  USD: '$',
  EUR: '\u20ac',  // €
  KZT: '\u20b8',  // ₸
  UAH: '\u20b4',  // ₴
  BYN: 'Br',
  GEL: '\u20be',  // ₾
  AED: '\u062f.\u0625',  // د.إ
  TRY: '\u20ba',  // ₺
  GBP: '\u00a3',  // £
};

/**
 * List of supported currencies with their details.
 */
export const CURRENCY_OPTIONS = [
  { code: 'RUB', name: 'Russian Ruble' },
  { code: 'USD', name: 'US Dollar' },
  { code: 'EUR', name: 'Euro' },
  { code: 'KZT', name: 'Kazakhstani Tenge' },
  { code: 'UAH', name: 'Ukrainian Hryvnia' },
  { code: 'BYN', name: 'Belarusian Ruble' },
  { code: 'GEL', name: 'Georgian Lari' },
  { code: 'AED', name: 'UAE Dirham' },
  { code: 'TRY', name: 'Turkish Lira' },
  { code: 'GBP', name: 'British Pound' },
] as const;

export type CurrencyCode = typeof CURRENCY_OPTIONS[number]['code'];

/**
 * Валюты, доступные для ВЫБОРА при вводе зарплаты (по требованию — только рубль и
 * доллар). CURRENCY_SYMBOLS/OPTIONS остаются полными, чтобы старые данные в других
 * валютах корректно форматировались (formatSalary).
 */
export const SALARY_INPUT_CURRENCIES: Array<{ value: string; label: string }> = [
  { value: 'RUB', label: '₽' },
  { value: 'USD', label: '$' },
];

/**
 * Default base currency for conversions
 */
export const DEFAULT_BASE_CURRENCY: CurrencyCode = 'RUB';

/**
 * Exchange rates type - maps currency code to rate relative to base
 */
export type ExchangeRates = Record<string, number>;

/**
 * Gets the currency symbol for a given currency code.
 * @param currency - The currency code (e.g., 'RUB', 'USD')
 * @returns The currency symbol, or the currency code if not found
 */
export function getCurrencySymbol(currency: string): string {
  return CURRENCY_SYMBOLS[currency] || currency;
}

/**
 * Formats a number with space as thousands separator (Russian locale).
 * @param amount - The number to format
 * @returns Formatted string with space separators
 */
function formatNumber(amount: number): string {
  return new Intl.NumberFormat('ru-RU').format(amount);
}

/**
 * Formats a single currency amount with its symbol.
 * @param amount - The amount to format
 * @param currency - The currency code (default: 'RUB')
 * @returns Formatted string like "150 000 ₽"
 */
export function formatCurrency(amount: number, currency: string = 'RUB'): string {
  const symbol = getCurrencySymbol(currency);
  return `${formatNumber(amount)} ${symbol}`;
}

/**
 * Formats a salary range with currency symbol.
 * @param min - Minimum salary (optional)
 * @param max - Maximum salary (optional)
 * @param currency - The currency code (default: 'RUB')
 * @returns Formatted salary string like "150 000 - 250 000 ₽" or "Not specified"
 */
export function formatSalary(
  min?: number,
  max?: number,
  currency: string = 'RUB'
): string {
  const symbol = getCurrencySymbol(currency);

  // VacancyForm — одно поле «Зарплата» пишет ОДНО и то же число в min И max
  // (нет отдельных «от»/«до»). Без этой проверки такая запись показывалась
  // как псевдо-диапазон «100 000 - 100 000 ₽» вместо «100 000 ₽».
  if (min && max && min === max) {
    return `${formatNumber(min)} ${symbol}`;
  }
  if (min && max) {
    return `${formatNumber(min)} - ${formatNumber(max)} ${symbol}`;
  }
  if (min) {
    return `от ${formatNumber(min)} ${symbol}`;
  }
  if (max) {
    return `до ${formatNumber(max)} ${symbol}`;
  }
  return 'Не указана';
}

/**
 * Gets currency options formatted for dropdown display.
 * @returns Array of { value, label } objects like { value: 'RUB', label: 'RUB (₽)' }
 */
export function getCurrencyDropdownOptions(): Array<{ value: string; label: string }> {
  return CURRENCY_OPTIONS.map(({ code }) => ({
    value: code,
    label: `${code} (${getCurrencySymbol(code)})`,
  }));
}

/**
 * Convert an amount from one currency to another.
 *
 * @param amount - The amount to convert
 * @param fromCurrency - Source currency code (e.g., 'USD')
 * @param toCurrency - Target currency code (e.g., 'RUB')
 * @param rates - Exchange rates dictionary from the API
 * @returns Converted amount, or null if conversion not possible
 *
 * @example
 * // If rates are relative to RUB:
 * // rates["USD"] = 90 means 1 USD = 90 RUB
 * const rubAmount = convertCurrency(100, 'USD', 'RUB', rates);
 * // rubAmount = 9000
 */
export function convertCurrency(
  amount: number,
  fromCurrency: string,
  toCurrency: string,
  rates: ExchangeRates
): number | null {
  if (fromCurrency === toCurrency) {
    return amount;
  }

  if (!(fromCurrency in rates) || !(toCurrency in rates)) {
    console.warn(`Cannot convert ${fromCurrency} to ${toCurrency}: currency not in rates`);
    return null;
  }

  const fromRate = rates[fromCurrency];
  const toRate = rates[toCurrency];

  if (toRate === 0) {
    console.warn(`Cannot convert to ${toCurrency}: rate is zero`);
    return null;
  }

  // Convert: result = amount * fromRate / toRate
  const result = (amount * fromRate) / toRate;

  // Round to 2 decimal places
  return Math.round(result * 100) / 100;
}

/**
 * Convert an amount to the base currency (default: RUB).
 *
 * @param amount - The amount to convert
 * @param fromCurrency - Source currency code
 * @param rates - Exchange rates dictionary
 * @param baseCurrency - Target base currency (default: RUB)
 * @returns Amount in base currency, or null if conversion not possible
 */
export function convertToBaseCurrency(
  amount: number,
  fromCurrency: string,
  rates: ExchangeRates,
  baseCurrency: string = DEFAULT_BASE_CURRENCY
): number | null {
  return convertCurrency(amount, fromCurrency, baseCurrency, rates);
}

/**
 * Convert salary range to base currency for comparison.
 * Returns the maximum salary value (or minimum if max not available) in base currency.
 *
 * @param salaryMin - Minimum salary (optional)
 * @param salaryMax - Maximum salary (optional)
 * @param currency - The currency of the salary
 * @param rates - Exchange rates dictionary
 * @param baseCurrency - Target base currency for comparison
 * @returns Comparable salary value in base currency, or 0 if no salary
 */
export function getSalaryForComparison(
  salaryMin: number | undefined | null,
  salaryMax: number | undefined | null,
  currency: string,
  rates: ExchangeRates,
  baseCurrency: string = DEFAULT_BASE_CURRENCY
): number {
  // Use max salary if available, otherwise min
  const salaryValue = salaryMax ?? salaryMin ?? 0;

  if (salaryValue === 0) {
    return 0;
  }

  const converted = convertCurrency(salaryValue, currency, baseCurrency, rates);
  return converted ?? 0;
}

/**
 * Fallback exchange rates relative to RUB (used when API is unavailable).
 * These are approximate values updated manually.
 */
export const FALLBACK_RATES_TO_RUB: ExchangeRates = {
  RUB: 1.0,
  USD: 90.0,
  EUR: 98.0,
  KZT: 0.19,
  UAH: 2.4,
  BYN: 27.5,
  GEL: 33.0,
  AED: 24.5,
  TRY: 2.6,
  GBP: 115.0,
};
