import { describe, it, expect } from 'vitest';
import {
  CURRENCY_SYMBOLS,
  getCurrencySymbol,
  formatCurrency,
  formatSalary,
  getCurrencyDropdownOptions,
  CURRENCY_OPTIONS,
  convertCurrency,
  convertToBaseCurrency,
  getSalaryForComparison,
  FALLBACK_RATES_TO_RUB,
  DEFAULT_BASE_CURRENCY,
  type ExchangeRates,
} from '../currency';

describe('Currency Utilities', () => {
  describe('CURRENCY_SYMBOLS', () => {
    it('should contain all required currency symbols', () => {
      expect(CURRENCY_SYMBOLS.RUB).toBe('\u20bd');
      expect(CURRENCY_SYMBOLS.USD).toBe('$');
      expect(CURRENCY_SYMBOLS.EUR).toBe('\u20ac');
      expect(CURRENCY_SYMBOLS.KZT).toBe('\u20b8');
      expect(CURRENCY_SYMBOLS.UAH).toBe('\u20b4');
      expect(CURRENCY_SYMBOLS.BYN).toBe('Br');
      expect(CURRENCY_SYMBOLS.GEL).toBe('\u20be');
      expect(CURRENCY_SYMBOLS.AED).toBe('\u062f.\u0625');
      expect(CURRENCY_SYMBOLS.TRY).toBe('\u20ba');
      expect(CURRENCY_SYMBOLS.GBP).toBe('\u00a3');
    });

    it('should have correct display symbols', () => {
      // Verify the actual symbols render correctly
      expect(CURRENCY_SYMBOLS.RUB).toBe('\u20bd'); // ₽
      expect(CURRENCY_SYMBOLS.EUR).toBe('\u20ac'); // €
      expect(CURRENCY_SYMBOLS.TRY).toBe('\u20ba'); // ₺
      expect(CURRENCY_SYMBOLS.GBP).toBe('\u00a3'); // £
    });

    it('should have 10 supported currencies', () => {
      expect(Object.keys(CURRENCY_SYMBOLS)).toHaveLength(10);
    });
  });

  describe('getCurrencySymbol', () => {
    it('should return the correct symbol for known currencies', () => {
      expect(getCurrencySymbol('RUB')).toBe('\u20bd');
      expect(getCurrencySymbol('USD')).toBe('$');
      expect(getCurrencySymbol('EUR')).toBe('\u20ac');
      expect(getCurrencySymbol('KZT')).toBe('\u20b8');
      expect(getCurrencySymbol('UAH')).toBe('\u20b4');
      expect(getCurrencySymbol('BYN')).toBe('Br');
      expect(getCurrencySymbol('GEL')).toBe('\u20be');
      expect(getCurrencySymbol('AED')).toBe('\u062f.\u0625');
      expect(getCurrencySymbol('TRY')).toBe('\u20ba');
      expect(getCurrencySymbol('GBP')).toBe('\u00a3');
    });

    it('should return the currency code for unknown currencies', () => {
      expect(getCurrencySymbol('XYZ')).toBe('XYZ');
      expect(getCurrencySymbol('UNKNOWN')).toBe('UNKNOWN');
    });

    it('should return empty string for empty input', () => {
      expect(getCurrencySymbol('')).toBe('');
    });

    it('should be case-sensitive', () => {
      // Lowercase codes are not mapped
      expect(getCurrencySymbol('usd')).toBe('usd');
      expect(getCurrencySymbol('eur')).toBe('eur');
    });
  });

  describe('formatCurrency', () => {
    it('should format amounts with RUB symbol by default', () => {
      expect(formatCurrency(150000)).toBe('150\u00a0000 \u20bd');
    });

    it('should format amounts with space as thousands separator', () => {
      expect(formatCurrency(1000000, 'RUB')).toBe('1\u00a0000\u00a0000 \u20bd');
      expect(formatCurrency(250000, 'USD')).toBe('250\u00a0000 $');
    });

    it('should format amounts with different currencies', () => {
      expect(formatCurrency(100000, 'USD')).toBe('100\u00a0000 $');
      expect(formatCurrency(100000, 'EUR')).toBe('100\u00a0000 \u20ac');
      expect(formatCurrency(100000, 'KZT')).toBe('100\u00a0000 \u20b8');
      expect(formatCurrency(100000, 'GBP')).toBe('100\u00a0000 \u00a3');
    });

    it('should handle small amounts', () => {
      expect(formatCurrency(500, 'RUB')).toBe('500 \u20bd');
      expect(formatCurrency(99, 'USD')).toBe('99 $');
    });

    it('should handle zero amount', () => {
      expect(formatCurrency(0, 'RUB')).toBe('0 \u20bd');
      expect(formatCurrency(0, 'USD')).toBe('0 $');
    });

    it('should handle very large amounts', () => {
      expect(formatCurrency(1000000000, 'USD')).toContain('$');
      expect(formatCurrency(1000000000, 'RUB')).toContain('\u20bd');
    });

    it('should handle amounts just under 1000', () => {
      expect(formatCurrency(999, 'RUB')).toBe('999 \u20bd');
    });

    it('should handle amounts at exactly 1000', () => {
      expect(formatCurrency(1000, 'RUB')).toBe('1\u00a0000 \u20bd');
    });

    it('should use currency code for unknown currency', () => {
      expect(formatCurrency(1000, 'XYZ')).toBe('1\u00a0000 XYZ');
    });
  });

  describe('formatSalary', () => {
    describe('with both min and max', () => {
      it('should format salary range with RUB', () => {
        const result = formatSalary(150000, 250000, 'RUB');
        expect(result).toBe('150\u00a0000 - 250\u00a0000 \u20bd');
      });

      it('should format salary range with USD', () => {
        expect(formatSalary(50000, 100000, 'USD')).toBe('50\u00a0000 - 100\u00a0000 $');
      });

      it('should format salary range with EUR', () => {
        expect(formatSalary(40000, 80000, 'EUR')).toBe('40\u00a0000 - 80\u00a0000 \u20ac');
      });

      it('should format salary range with GBP', () => {
        expect(formatSalary(30000, 50000, 'GBP')).toBe('30\u00a0000 - 50\u00a0000 \u00a3');
      });
    });

    describe('with only min value', () => {
      it('should format "from X" with RUB', () => {
        const result = formatSalary(100000, undefined, 'RUB');
        expect(result).toBe('от 100\u00a0000 \u20bd');
      });

      it('should format "from X" with USD', () => {
        expect(formatSalary(5000, undefined, 'USD')).toBe('от 5\u00a0000 $');
      });
    });

    describe('with only max value', () => {
      it('should format "up to X" with RUB', () => {
        const result = formatSalary(undefined, 200000, 'RUB');
        expect(result).toBe('до 200\u00a0000 \u20bd');
      });

      it('should format "up to X" with EUR', () => {
        expect(formatSalary(undefined, 10000, 'EUR')).toBe('до 10\u00a0000 \u20ac');
      });
    });

    describe('with no values', () => {
      it('should return "Not specified" with no arguments', () => {
        expect(formatSalary()).toBe('Не указана');
      });

      it('should return "Not specified" with both undefined', () => {
        expect(formatSalary(undefined, undefined)).toBe('Не указана');
      });

      it('should return "Not specified" regardless of currency', () => {
        expect(formatSalary(undefined, undefined, 'USD')).toBe('Не указана');
        expect(formatSalary(undefined, undefined, 'EUR')).toBe('Не указана');
      });
    });

    describe('default currency', () => {
      it('should use RUB as default currency', () => {
        const result = formatSalary(100000, 200000);
        expect(result).toContain('\u20bd');
      });
    });

    describe('edge cases with zero', () => {
      it('should treat zero min as not specified', () => {
        expect(formatSalary(0, 100000, 'RUB')).toBe('до 100\u00a0000 \u20bd');
      });

      it('should treat zero max as not specified', () => {
        expect(formatSalary(100000, 0, 'RUB')).toBe('от 100\u00a0000 \u20bd');
      });

      it('should return not specified when both are zero', () => {
        expect(formatSalary(0, 0, 'RUB')).toBe('Не указана');
      });
    });

    describe('thousands separator', () => {
      it('should add separator for large salaries', () => {
        const result = formatSalary(1500000, 2500000, 'RUB');
        expect(result).toContain('1\u00a0500\u00a0000');
        expect(result).toContain('2\u00a0500\u00a0000');
      });

      it('should not add separator for small salaries', () => {
        expect(formatSalary(500, 999, 'USD')).toBe('500 - 999 $');
      });
    });

    describe('all supported currencies', () => {
      it('should work with KZT', () => {
        expect(formatSalary(500000, 800000, 'KZT')).toContain('\u20b8');
      });

      it('should work with UAH', () => {
        expect(formatSalary(30000, 50000, 'UAH')).toContain('\u20b4');
      });

      it('should work with BYN', () => {
        expect(formatSalary(2000, 4000, 'BYN')).toContain('Br');
      });

      it('should work with GEL', () => {
        expect(formatSalary(3000, 5000, 'GEL')).toContain('\u20be');
      });

      it('should work with AED', () => {
        expect(formatSalary(15000, 25000, 'AED')).toContain('\u062f.\u0625');
      });

      it('should work with TRY', () => {
        expect(formatSalary(50000, 80000, 'TRY')).toContain('\u20ba');
      });
    });

    describe('equal min and max', () => {
      it('should format as single value, not a pseudo-range (VacancyForm single field writes min=max)', () => {
        expect(formatSalary(150000, 150000, 'RUB')).toBe('150\u00a0000 \u20bd');
      });
    });
  });

  describe('getCurrencyDropdownOptions', () => {
    it('should return array of currency options', () => {
      const options = getCurrencyDropdownOptions();
      expect(Array.isArray(options)).toBe(true);
      expect(options.length).toBe(CURRENCY_OPTIONS.length);
    });

    it('should have value and label for each option', () => {
      const options = getCurrencyDropdownOptions();
      options.forEach((option) => {
        expect(option).toHaveProperty('value');
        expect(option).toHaveProperty('label');
        expect(typeof option.value).toBe('string');
        expect(typeof option.label).toBe('string');
      });
    });

    it('should format labels as "CODE (symbol)"', () => {
      const options = getCurrencyDropdownOptions();
      const rubOption = options.find((o) => o.value === 'RUB');
      const usdOption = options.find((o) => o.value === 'USD');
      const eurOption = options.find((o) => o.value === 'EUR');

      expect(rubOption?.label).toBe('RUB (\u20bd)');
      expect(usdOption?.label).toBe('USD ($)');
      expect(eurOption?.label).toBe('EUR (\u20ac)');
    });

    it('should include all supported currencies', () => {
      const options = getCurrencyDropdownOptions();
      const values = options.map((o) => o.value);

      expect(values).toContain('RUB');
      expect(values).toContain('USD');
      expect(values).toContain('EUR');
      expect(values).toContain('KZT');
      expect(values).toContain('UAH');
      expect(values).toContain('BYN');
      expect(values).toContain('GEL');
      expect(values).toContain('AED');
      expect(values).toContain('TRY');
      expect(values).toContain('GBP');
    });

    it('should format GBP correctly', () => {
      const options = getCurrencyDropdownOptions();
      const gbpOption = options.find((o) => o.value === 'GBP');
      expect(gbpOption?.label).toBe('GBP (\u00a3)');
    });
  });

  describe('CURRENCY_OPTIONS', () => {
    it('should contain all required currencies', () => {
      const codes = CURRENCY_OPTIONS.map((c) => c.code);
      expect(codes).toContain('RUB');
      expect(codes).toContain('USD');
      expect(codes).toContain('EUR');
      expect(codes).toContain('KZT');
      expect(codes).toContain('UAH');
      expect(codes).toContain('BYN');
      expect(codes).toContain('GEL');
      expect(codes).toContain('AED');
      expect(codes).toContain('TRY');
      expect(codes).toContain('GBP');
    });

    it('should have name for each currency', () => {
      CURRENCY_OPTIONS.forEach((currency) => {
        expect(currency).toHaveProperty('code');
        expect(currency).toHaveProperty('name');
        expect(currency.name.length).toBeGreaterThan(0);
      });
    });

    it('should have 10 currencies', () => {
      expect(CURRENCY_OPTIONS).toHaveLength(10);
    });
  });

  describe('convertCurrency', () => {
    const sampleRates: ExchangeRates = {
      RUB: 1.0,
      USD: 90.0,
      EUR: 98.0,
      GBP: 115.0,
    };

    it('should return same amount when converting to same currency', () => {
      expect(convertCurrency(100, 'USD', 'USD', sampleRates)).toBe(100);
    });

    it('should convert USD to RUB correctly', () => {
      const result = convertCurrency(100, 'USD', 'RUB', sampleRates);
      expect(result).toBe(9000);
    });

    it('should convert RUB to USD correctly', () => {
      const result = convertCurrency(9000, 'RUB', 'USD', sampleRates);
      expect(result).toBe(100);
    });

    it('should convert between non-base currencies', () => {
      // 100 EUR * 98 / 90 = 108.89 USD
      const result = convertCurrency(100, 'EUR', 'USD', sampleRates);
      expect(result).toBeCloseTo(108.89, 1);
    });

    it('should return null for unknown from currency', () => {
      const result = convertCurrency(100, 'XXX', 'RUB', sampleRates);
      expect(result).toBeNull();
    });

    it('should return null for unknown to currency', () => {
      const result = convertCurrency(100, 'USD', 'XXX', sampleRates);
      expect(result).toBeNull();
    });

    it('should handle zero amount', () => {
      expect(convertCurrency(0, 'USD', 'RUB', sampleRates)).toBe(0);
    });

    it('should handle negative amounts', () => {
      expect(convertCurrency(-100, 'USD', 'RUB', sampleRates)).toBe(-9000);
    });

    it('should round to 2 decimal places', () => {
      const result = convertCurrency(99.99, 'USD', 'RUB', sampleRates);
      // 99.99 * 90 = 8999.1
      expect(result).toBe(8999.1);
    });
  });

  describe('convertToBaseCurrency', () => {
    const sampleRates: ExchangeRates = {
      RUB: 1.0,
      USD: 90.0,
      EUR: 98.0,
    };

    it('should convert to RUB by default', () => {
      const result = convertToBaseCurrency(100, 'USD', sampleRates);
      expect(result).toBe(9000);
    });

    it('should convert RUB to RUB as-is', () => {
      const result = convertToBaseCurrency(100, 'RUB', sampleRates);
      expect(result).toBe(100);
    });

    it('should convert to custom base currency', () => {
      // 100 RUB * 1 / 90 = 1.11 USD
      const result = convertToBaseCurrency(100, 'RUB', sampleRates, 'USD');
      expect(result).toBeCloseTo(1.11, 1);
    });
  });

  describe('getSalaryForComparison', () => {
    const sampleRates: ExchangeRates = {
      RUB: 1.0,
      USD: 90.0,
      EUR: 98.0,
    };

    it('should return max salary converted to base currency', () => {
      // 5000 USD max salary = 450000 RUB
      const result = getSalaryForComparison(3000, 5000, 'USD', sampleRates);
      expect(result).toBe(450000);
    });

    it('should return min salary if max not available', () => {
      // 3000 USD min salary = 270000 RUB
      const result = getSalaryForComparison(3000, undefined, 'USD', sampleRates);
      expect(result).toBe(270000);
    });

    it('should return 0 if no salary specified', () => {
      const result = getSalaryForComparison(undefined, undefined, 'USD', sampleRates);
      expect(result).toBe(0);
    });

    it('should return 0 if null salary specified', () => {
      const result = getSalaryForComparison(null, null, 'USD', sampleRates);
      expect(result).toBe(0);
    });

    it('should return RUB salaries as-is when base is RUB', () => {
      const result = getSalaryForComparison(100000, 200000, 'RUB', sampleRates);
      expect(result).toBe(200000);
    });

    it('should handle EUR salaries', () => {
      // 1000 EUR * 98 = 98000 RUB
      const result = getSalaryForComparison(500, 1000, 'EUR', sampleRates);
      expect(result).toBe(98000);
    });
  });

  describe('FALLBACK_RATES_TO_RUB', () => {
    it('should have all supported currencies', () => {
      const currencies = ['RUB', 'USD', 'EUR', 'KZT', 'UAH', 'BYN', 'GEL', 'AED', 'TRY', 'GBP'];
      currencies.forEach((currency) => {
        expect(FALLBACK_RATES_TO_RUB[currency]).toBeDefined();
        expect(FALLBACK_RATES_TO_RUB[currency]).toBeGreaterThan(0);
      });
    });

    it('should have RUB rate as 1', () => {
      expect(FALLBACK_RATES_TO_RUB.RUB).toBe(1.0);
    });

    it('should have reasonable USD rate (between 50 and 150 RUB)', () => {
      expect(FALLBACK_RATES_TO_RUB.USD).toBeGreaterThan(50);
      expect(FALLBACK_RATES_TO_RUB.USD).toBeLessThan(150);
    });

    it('should have reasonable EUR rate (higher than USD)', () => {
      expect(FALLBACK_RATES_TO_RUB.EUR).toBeGreaterThan(FALLBACK_RATES_TO_RUB.USD);
    });
  });

  describe('DEFAULT_BASE_CURRENCY', () => {
    it('should be RUB', () => {
      expect(DEFAULT_BASE_CURRENCY).toBe('RUB');
    });
  });
});
