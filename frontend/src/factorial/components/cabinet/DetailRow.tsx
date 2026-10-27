export default function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4 py-2.5 border-b border-card-border-soft last:border-0">
      <span className="text-fx-sm text-text-muted shrink-0">{label}</span>
      <span className="text-fx-sm text-text-primary text-right">{value}</span>
    </div>
  );
}
