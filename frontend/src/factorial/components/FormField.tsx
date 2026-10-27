import { ReactNode } from 'react';

export default function FormField({
  label,
  required,
  error,
  hint,
  children,
}: {
  label: string;
  required?: boolean;
  error?: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <label className="text-fx-sm text-text-primary font-medium">
        {label}
        {required && <span className="text-primary ml-1">*</span>}
      </label>
      {children}
      {hint && <p className="text-fx-xs text-text-muted">{hint}</p>}
      {error && <p className="text-fx-xs text-primary">{error}</p>}
    </div>
  );
}
