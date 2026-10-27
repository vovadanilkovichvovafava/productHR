import { useState } from 'react';
import { X } from 'lucide-react';

interface PromoBannerProps {
  heading: string;
  description: string;
  ctaLabel: string;
  onCta: () => void;
}

export default function PromoBanner({ heading, description, ctaLabel, onCta }: PromoBannerProps) {
  const [open, setOpen] = useState(true);
  if (!open) return null;
  return (
    <div className="bg-violet-50 rounded-card border border-violet-100 px-4 py-3 flex items-center justify-between gap-3">
      <div>
        <p className="text-fx-sm font-semibold text-violet-900">{heading}</p>
        <p className="text-fx-xs text-violet-700 mt-0.5">{description}</p>
      </div>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onCta}
          className="px-3 py-1.5 rounded-fx-lg bg-white text-fx-xs font-medium hover:bg-violet-100 transition-colors"
        >
          {ctaLabel}
        </button>
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="p-1 rounded hover:bg-violet-100"
          aria-label="Close"
        >
          <X className="w-3.5 h-3.5 text-violet-700" />
        </button>
      </div>
    </div>
  );
}
