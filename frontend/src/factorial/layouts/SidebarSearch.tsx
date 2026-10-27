import { Search } from 'lucide-react';

export default function SidebarSearch() {
  return (
    <button
      type="button"
      className="w-full flex items-center gap-2 px-3 py-2 rounded-fx-lg bg-sidebar-hover hover:bg-border text-text-muted text-fx-sm transition-colors"
    >
      <Search className="w-4 h-4" />
      <span className="flex-1 text-left">Поиск...</span>
      <span className="text-fx-xs text-text-muted/70 font-mono">
        <kbd className="px-1.5 py-0.5 bg-white rounded border border-border text-[10px]">Ctrl</kbd>
        <span className="mx-0.5">K</span>
      </span>
    </button>
  );
}
