import { useEffect, useRef } from 'react';
import type { MouseEventHandler, RefObject } from 'react';
import type { LucideIcon } from 'lucide-react';
import { HuntflowActionChip } from './HuntflowControls';
import { HuntflowRichInput } from './HuntflowRichInput';

export type HuntflowComposerAction = {
  label: string;
  icon: LucideIcon;
  onClick: MouseEventHandler<HTMLButtonElement>;
  disabled?: boolean;
  loading?: boolean;
  loadingLabel?: string;
  className?: string;
};

type HuntflowComposerProps = {
  value: string;
  onChange: (value: string) => void;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  placeholder: string;
  onSubmit: () => void;
  onCancel?: () => void;
  saving?: boolean;
  saveLabel?: string;
  savingLabel?: string;
  actions?: HuntflowComposerAction[];
  showMention?: boolean;
  collapsedRows?: number;
  expandedRows?: number;
  disabled?: boolean;
  wrapperClassName?: string;
  collapsedClassName?: string;
  textareaRef?: RefObject<HTMLTextAreaElement | null>;
};

const defaultCollapsedClassName =
  'h-[58px] w-full resize-none rounded-[var(--hf-radius-s)] border border-[var(--hf-main-300)] bg-[var(--hf-white)] px-[var(--hf-space-xxl)] py-[14px] text-[length:var(--hf-fs-s)] leading-[var(--hf-lh-primary)] text-[var(--hf-main-900)] placeholder:text-[var(--hf-main-600)] focus:border-[var(--hf-cyan-500)] focus:outline-none disabled:opacity-50';

export function HuntflowComposer({
  value,
  onChange,
  open,
  onOpenChange,
  placeholder,
  onSubmit,
  onCancel,
  saving = false,
  saveLabel = 'Сохранить',
  savingLabel = 'Сохраняем...',
  actions = [],
  showMention = false,
  collapsedRows = 1,
  disabled = false,
  wrapperClassName,
  collapsedClassName = defaultCollapsedClassName,
  textareaRef,
}: HuntflowComposerProps) {
  const rootRef = useRef<HTMLDivElement>(null);
  const localTextareaRef = useRef<HTMLTextAreaElement | null>(null);
  const activeTextareaRef = textareaRef || localTextareaRef;
  const isExpanded = open || value.trim().length > 0;
  const setTextareaNode = (node: HTMLTextAreaElement | null) => {
    localTextareaRef.current = node;
    if (textareaRef) {
      (textareaRef as { current: HTMLTextAreaElement | null }).current = node;
    }
  };

  useEffect(() => {
    const handler = (event: MouseEvent) => {
      if (
        rootRef.current &&
        !rootRef.current.contains(event.target as Node) &&
        !value.trim()
      ) {
        onOpenChange(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [onOpenChange, value]);

  useEffect(() => {
    if (isExpanded) {
      requestAnimationFrame(() => activeTextareaRef.current?.focus());
    }
  }, [activeTextareaRef, isExpanded]);

  const handleCancel = () => {
    if (onCancel) {
      onCancel();
      return;
    }
    onChange('');
    onOpenChange(false);
  };

  if (!isExpanded) {
    return (
      <div ref={rootRef} className={wrapperClassName}>
        <textarea
          ref={setTextareaNode}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onFocus={() => onOpenChange(true)}
          placeholder={placeholder}
          rows={collapsedRows}
          disabled={disabled || saving}
          className={`hf-composer-textarea ${collapsedClassName}`}
        />
      </div>
    );
  }

  return (
    <div ref={rootRef} className={wrapperClassName}>
      <div className="w-full overflow-hidden rounded-[var(--hf-radius-s)] border border-[var(--hf-cyan-500)] bg-transparent text-[var(--hf-main-900)]">
        <HuntflowRichInput
          value={value}
          onChange={onChange}
          placeholder={placeholder}
          showMention={showMention}
          onEnterSubmit={onSubmit}
          autoFocus
          disabled={disabled || saving}
          toolbarClassName="flex h-[45px] items-center gap-[2px] border-b border-[var(--hf-ui-border)] px-[10px]"
          editableClassName="block min-h-[56px] max-h-[200px] w-full overflow-y-auto border-0 bg-transparent px-[var(--hf-space-xxl)] py-[var(--hf-space-l)] text-[length:var(--hf-fs-s)] leading-[var(--hf-lh-primary)] text-[var(--hf-main-900)] outline-none disabled:opacity-50"
        />
        {actions.length > 0 && (
          <div className="flex h-[53px] items-start gap-[var(--hf-space-s)] px-[var(--hf-space-xxl)] pb-[16px] pt-[8px]">
            {actions.map((action) => (
              <HuntflowActionChip
                key={action.label}
                icon={action.icon}
                label={action.label}
                displayLabel={action.loading ? action.loadingLabel || 'Загрузка...' : action.label}
                onClick={action.onClick}
                disabled={action.disabled}
                loading={action.loading}
                className={action.className}
              />
            ))}
          </div>
        )}
      </div>
      <div className="mt-[10px] flex h-[32px] items-start gap-[var(--hf-space-s)]">
        <button
          type="button"
          onClick={onSubmit}
          disabled={!value.trim() || saving || disabled}
          className="inline-flex h-[32px] items-center justify-center rounded-[var(--hf-radius-s)] border border-transparent bg-[var(--hf-black-alpha-05)] px-[12px] text-[length:var(--hf-fs-xxs)] font-medium leading-[var(--hf-lh-secondary)] text-[color:var(--hf-black-alpha-25)] transition-colors enabled:bg-[var(--hf-main-900)] enabled:text-[var(--hf-white)] enabled:hover:bg-[var(--hf-main-800)] disabled:cursor-default"
        >
          {saving ? savingLabel : saveLabel}
        </button>
        <button
          type="button"
          onClick={handleCancel}
          disabled={saving || disabled}
          className="inline-flex h-[32px] items-center justify-center rounded-[var(--hf-radius-s)] border border-transparent bg-[var(--hf-black-alpha-06)] px-[12px] text-[length:var(--hf-fs-xxs)] font-medium leading-[var(--hf-lh-secondary)] text-[var(--hf-main-900)] transition-colors hover:bg-[var(--hf-black-alpha-08)] disabled:opacity-50"
        >
          Отмена
        </button>
      </div>
    </div>
  );
}
