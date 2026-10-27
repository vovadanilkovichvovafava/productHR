import { useState, useEffect, useRef, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Eye, Edit, Trash2, Link2, LucideIcon } from 'lucide-react';

export interface ContextMenuItem {
  id: string;
  label: string;
  icon?: LucideIcon;
  onClick: () => void;
  danger?: boolean;
  disabled?: boolean;
  divider?: boolean;
}

interface ContextMenuProps {
  items: ContextMenuItem[];
  children: React.ReactNode;
  disabled?: boolean;
}

interface Position {
  x: number;
  y: number;
}

export default function ContextMenu({ items, children, disabled = false }: ContextMenuProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [position, setPosition] = useState<Position>({ x: 0, y: 0 });
  const menuRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const handleContextMenu = useCallback((e: React.MouseEvent) => {
    if (disabled) return;

    e.preventDefault();
    e.stopPropagation();

    // Calculate position, ensuring menu stays in viewport
    const menuWidth = 200;
    const menuHeight = items.length * 40;

    let x = e.clientX;
    let y = e.clientY;

    if (x + menuWidth > window.innerWidth) {
      x = window.innerWidth - menuWidth - 10;
    }
    if (y + menuHeight > window.innerHeight) {
      y = window.innerHeight - menuHeight - 10;
    }

    setPosition({ x, y });
    setIsOpen(true);
  }, [disabled, items.length]);

  const handleClickOutside = useCallback((e: MouseEvent) => {
    if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
      setIsOpen(false);
    }
  }, []);

  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Escape') {
      setIsOpen(false);
    }
  }, []);

  useEffect(() => {
    if (isOpen) {
      document.addEventListener('click', handleClickOutside);
      document.addEventListener('keydown', handleKeyDown);
      return () => {
        document.removeEventListener('click', handleClickOutside);
        document.removeEventListener('keydown', handleKeyDown);
      };
    }
  }, [isOpen, handleClickOutside, handleKeyDown]);

  const handleItemClick = (item: ContextMenuItem) => {
    if (item.disabled) return;
    setIsOpen(false);
    item.onClick();
  };

  return (
    <>
      <div ref={containerRef} onContextMenu={handleContextMenu}>
        {children}
      </div>

      <AnimatePresence>
        {isOpen && (
          <motion.div
            ref={menuRef}
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            transition={{ duration: 0.1 }}
            style={{ left: position.x, top: position.y }}
            className="fixed z-50 min-w-[180px] bg-gray-800 border border-white/10 rounded-lg shadow-xl overflow-hidden py-1"
          >
            {items.map((item, index) => (
              <div key={item.id}>
                {item.divider && index > 0 && (
                  <div className="my-1 border-t border-white/10" />
                )}
                <button
                  onClick={() => handleItemClick(item)}
                  disabled={item.disabled}
                  className={`
                    w-full px-3 py-2 flex items-center gap-3 text-sm text-left transition-colors
                    ${item.disabled
                      ? 'opacity-50 cursor-not-allowed'
                      : item.danger
                        ? 'hover:bg-red-500/20 text-red-400'
                        : 'hover:bg-white/10 text-white/80'
                    }
                  `}
                >
                  {item.icon && <item.icon className="w-4 h-4" />}
                  <span>{item.label}</span>
                </button>
              </div>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}

// Pre-built context menu configurations
export function createVacancyContextMenu(
  onOpen: () => void,
  onEdit: () => void,
  onDelete: () => void,
  onCopyLink: () => void
): ContextMenuItem[] {
  return [
    { id: 'open', label: 'Открыть', icon: Eye, onClick: onOpen },
    { id: 'edit', label: 'Редактировать', icon: Edit, onClick: onEdit },
    { id: 'copy-link', label: 'Копировать ссылку', icon: Link2, onClick: onCopyLink, divider: true },
    { id: 'delete', label: 'Удалить', icon: Trash2, onClick: onDelete, danger: true, divider: true },
  ];
}

export function createEntityContextMenu(
  onOpen: () => void,
  onEdit: () => void,
  onDelete: () => void,
  onCopyLink: () => void
): ContextMenuItem[] {
  return [
    { id: 'open', label: 'Открыть', icon: Eye, onClick: onOpen },
    { id: 'edit', label: 'Редактировать', icon: Edit, onClick: onEdit },
    { id: 'copy-link', label: 'Копировать ссылку', icon: Link2, onClick: onCopyLink, divider: true },
    { id: 'delete', label: 'Удалить', icon: Trash2, onClick: onDelete, danger: true, divider: true },
  ];
}
