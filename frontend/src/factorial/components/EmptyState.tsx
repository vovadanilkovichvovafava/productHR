interface EmptyStateProps {
  emoji?: string;
  heading: string;
  description?: string;
  cta?: { label: string; onClick: () => void };
}

export default function EmptyState({ emoji = '📭', heading, description, cta }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-8 text-center gap-3">
      <div className="text-5xl">{emoji}</div>
      <h2 className="text-fx-base font-medium text-text-primary">{heading}</h2>
      {description && <p className="text-fx-sm text-text-primary max-w-md">{description}</p>}
      {cta && (
        <button
          type="button"
          onClick={cta.onClick}
          className="mt-3 px-4 py-2 rounded-fx-lg bg-primary hover:bg-primary-hover text-white text-fx-base font-medium"
        >
          {cta.label}
        </button>
      )}
    </div>
  );
}
