import { useEffect, useRef, useState } from 'react';
import { Upload, MoreVertical, Trash2 } from 'lucide-react';
import { cn } from '@/factorial/lib/cn';

interface FileDropZoneProps {
  hint?: string;
  /** Optional second hint line (e.g. "1200x600px") */
  subHint?: string;
  accept?: string;
  /** Visual height: 'sm' (~170px) or 'lg' (~280px, Factorial default for posts) */
  size?: 'sm' | 'lg';
}

interface Preview {
  url: string;
  type: 'image' | 'video';
  name: string;
}

export default function FileDropZone({
  hint,
  subHint,
  accept = 'image/*,video/*,image/gif',
  size = 'lg',
}: FileDropZoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const minH = size === 'lg' ? 'min-h-[280px]' : 'min-h-[170px]';

  // Revoke object URL on unmount / when preview changes away
  useEffect(() => {
    return () => {
      if (preview) URL.revokeObjectURL(preview.url);
    };
  }, [preview]);

  const handleFile = (file: File) => {
    if (preview) URL.revokeObjectURL(preview.url);
    const url = URL.createObjectURL(file);
    const type: 'image' | 'video' = file.type.startsWith('video') ? 'video' : 'image';
    setPreview({ url, type, name: file.name });
  };

  const onInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) handleFile(f);
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files?.[0];
    if (f) handleFile(f);
  };

  const removeMedia = () => {
    if (preview) URL.revokeObjectURL(preview.url);
    setPreview(null);
    setMenuOpen(false);
    if (inputRef.current) inputRef.current.value = '';
  };

  // FILLED state — media preview + ⋮ menu (matches Factorial)
  if (preview) {
    const deleteLabel = preview.type === 'video' ? 'Удалить видео' : 'Удалить изображение';
    return (
      <div className={cn('relative rounded-card overflow-hidden border border-card-border-soft bg-slate-900', minH)}>
        {preview.type === 'video' ? (
          <video src={preview.url} controls className="w-full h-full max-h-[280px] object-contain bg-black" />
        ) : (
          <img src={preview.url} alt={preview.name} className="w-full h-full max-h-[280px] object-cover" />
        )}

        {/* ⋮ menu button — top-right */}
        <div className="absolute top-3 right-3">
          <button
            type="button"
            onClick={() => setMenuOpen((o) => !o)}
            className="w-8 h-8 rounded-full bg-white shadow-card flex items-center justify-center hover:bg-sidebar-hover"
            title="Опции"
            aria-label="Опции"
          >
            <MoreVertical className="w-4 h-4 text-text-secondary" />
          </button>
          {menuOpen && (
            <>
              <div className="fixed inset-0 z-10" onClick={() => setMenuOpen(false)} />
              <div className="absolute right-0 mt-1 z-20 bg-white rounded-fx-lg shadow-card-hover border border-card-border-soft py-1 min-w-[170px]">
                <button
                  type="button"
                  onClick={removeMedia}
                  className="w-full text-left px-4 py-2 text-fx-sm text-primary hover:bg-sidebar-hover flex items-center gap-2"
                >
                  <Trash2 className="w-4 h-4" /> {deleteLabel}
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    );
  }

  // EMPTY state — drop zone
  return (
    <div
      onClick={() => inputRef.current?.click()}
      onDragOver={(e) => {
        e.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={onDrop}
      className={cn(
        'border-2 border-dashed rounded-card p-8 flex flex-col items-center justify-center text-center gap-2 cursor-pointer transition-colors',
        minH,
        dragOver ? 'border-primary bg-primary/5' : 'border-card-border-soft hover:bg-sidebar-hover/30',
      )}
    >
      <Upload className="w-5 h-5 text-text-muted" />
      <p className="text-fx-sm font-medium text-text-primary">Перетащите сюда или нажмите.</p>
      {hint && <p className="text-fx-xs text-text-muted">{hint}</p>}
      {subHint && <p className="text-fx-xs text-text-muted">{subHint}</p>}
      <input ref={inputRef} type="file" accept={accept} className="hidden" onChange={onInputChange} />
    </div>
  );
}
