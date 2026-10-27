import { getCurrencyDropdownOptions } from '@/utils';
import clsx from 'clsx';

interface CurrencySelectProps {
  value: string;
  onChange: (currency: string) => void;
  className?: string;
  disabled?: boolean;
}

/**
 * Currency dropdown selector that displays currencies with their symbols.
 * Format: "RUB (₽)", "USD ($)", "EUR (€)", etc.
 */
export default function CurrencySelect({
  value,
  onChange,
  className,
  disabled = false
}: CurrencySelectProps) {
  const options = getCurrencyDropdownOptions();

  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      disabled={disabled}
      className={clsx(
        'px-3 py-2 glass-light rounded-lg',
        'focus:outline-none focus:border-blue-500',
        'disabled:opacity-50 disabled:cursor-not-allowed',
        className
      )}
    >
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  );
}
