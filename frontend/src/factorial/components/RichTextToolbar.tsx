import { Bold, Italic, Code as CodeIcon, Link as LinkIcon, Type } from 'lucide-react';

export default function RichTextToolbar() {
  return (
    <div className="flex items-center gap-1 px-2 py-1.5 border border-card-border-soft border-b-0 rounded-t-lg bg-sidebar-hover/30">
      <button
        type="button"
        className="p-1 hover:bg-white rounded inline-flex items-center gap-1 text-text-muted text-fx-xs"
      >
        <Type className="w-3.5 h-3.5" />
      </button>
      <span className="w-px h-4 bg-card-border-soft mx-1" />
      <button type="button" className="p-1 hover:bg-white rounded text-text-muted">
        <Bold className="w-3.5 h-3.5" />
      </button>
      <button type="button" className="p-1 hover:bg-white rounded text-text-muted">
        <Italic className="w-3.5 h-3.5" />
      </button>
      <span className="w-px h-4 bg-card-border-soft mx-1" />
      <button type="button" className="p-1 hover:bg-white rounded text-text-muted">
        <CodeIcon className="w-3.5 h-3.5" />
      </button>
      <button type="button" className="p-1 hover:bg-white rounded text-text-muted">
        <LinkIcon className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}
