import { useRef, useCallback, ReactNode } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';

interface VirtualListProps<T> {
  items: T[];
  estimateSize: number;
  renderItem: (item: T, index: number, virtualRow: { size: number; start: number }) => ReactNode;
  className?: string;
  overscan?: number;
  getItemKey?: (item: T, index: number) => string | number;
}

/**
 * A virtualized list component that only renders visible items.
 * Use for lists with more than ~50 items for better performance.
 *
 * @param items - Array of items to render
 * @param estimateSize - Estimated height of each row in pixels
 * @param renderItem - Function to render each item
 * @param className - Optional className for the scroll container
 * @param overscan - Number of items to render outside visible area (default: 5)
 * @param getItemKey - Optional function to get unique key for each item
 */
export function VirtualList<T>({
  items,
  estimateSize,
  renderItem,
  className = '',
  overscan = 5,
  getItemKey,
}: VirtualListProps<T>) {
  const parentRef = useRef<HTMLDivElement>(null);

  const getKey = useCallback(
    (index: number) => {
      if (getItemKey) {
        return getItemKey(items[index], index);
      }
      return index;
    },
    [items, getItemKey]
  );

  const virtualizer = useVirtualizer({
    count: items.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => estimateSize,
    overscan,
    getItemKey: getKey,
  });

  const virtualItems = virtualizer.getVirtualItems();

  return (
    <div
      ref={parentRef}
      className={`overflow-auto ${className}`}
      style={{ contain: 'strict' }}
    >
      <div
        style={{
          height: `${virtualizer.getTotalSize()}px`,
          width: '100%',
          position: 'relative',
        }}
      >
        {virtualItems.map((virtualRow) => (
          <div
            key={virtualRow.key}
            data-index={virtualRow.index}
            ref={virtualizer.measureElement}
            style={{
              position: 'absolute',
              top: 0,
              left: 0,
              width: '100%',
              transform: `translateY(${virtualRow.start}px)`,
            }}
          >
            {renderItem(items[virtualRow.index], virtualRow.index, {
              size: virtualRow.size,
              start: virtualRow.start,
            })}
          </div>
        ))}
      </div>
    </div>
  );
}

export default VirtualList;
