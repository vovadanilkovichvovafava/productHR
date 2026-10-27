import { useRef } from 'react';

interface TimePickerFactorialProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}

/**
 * Factorial-style time input — simple HH:MM text input.
 * On focus, selects the HH portion (like Factorial does).
 * No popup picker — user types directly.
 */
export default function TimePickerFactorial({
  value,
  onChange,
  placeholder = '--:--',
}: TimePickerFactorialProps) {
  const ref = useRef<HTMLInputElement>(null);

  const handleFocus = () => {
    // Select HH portion (chars 0-2) on focus, like Factorial does
    setTimeout(() => {
      if (ref.current) {
        ref.current.setSelectionRange(0, 2);
      }
    }, 0);
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    let raw = e.target.value.replace(/[^0-9:]/g, '');
    // Auto-insert colon after 2 digits if user typed 4 numbers
    if (raw.length === 2 && !raw.includes(':') && value.length === 1) {
      raw = raw + ':';
    }
    if (raw.length > 5) raw = raw.slice(0, 5);
    onChange(raw);
  };

  return (
    <input
      ref={ref}
      type="text"
      value={value}
      onChange={handleChange}
      onFocus={handleFocus}
      placeholder={placeholder}
      maxLength={5}
      className="w-full px-3 py-2 rounded-fx-lg border border-card-border-soft bg-white text-fx-sm text-text-primary focus:outline-none focus:border-border-hover placeholder:text-text-muted"
    />
  );
}
