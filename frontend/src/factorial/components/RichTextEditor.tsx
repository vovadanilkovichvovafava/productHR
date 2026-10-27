import { useRef, useState, useEffect, useCallback } from 'react';
import {
  Type,
  Paperclip,
  Maximize2,
  X,
  Link as LinkIcon,
  Smile,
  Bold,
  Italic,
  Underline,
  Strikethrough,
  AlignLeft,
  List,
  ListOrdered,
  MoreHorizontal,
} from 'lucide-react';
import { cn } from '@/factorial/lib/cn';
import EmojiPicker from './EmojiPicker';

interface RichTextEditorProps {
  value?: string;
  onChange?: (html: string) => void;
  placeholder?: string;
  maxLength?: number;
  footerHint?: string;
}

export default function RichTextEditor({
  value = '',
  onChange,
  placeholder = 'Поделитесь, что в этом особенного',
  maxLength = 10000,
  footerHint,
}: RichTextEditorProps) {
  const editorRef = useRef<HTMLDivElement>(null);
  const [expanded, setExpanded] = useState(false);
  const [emojiOpen, setEmojiOpen] = useState(false);
  const [charCount, setCharCount] = useState(0);
  // Placeholder shows when there is no TEXT (matches Factorial: visible even with an
  // empty list/heading structure, hidden the instant real text is typed).
  const [isEmpty, setIsEmpty] = useState(true);
  const [active, setActive] = useState({
    bold: false,
    italic: false,
    underline: false,
    strike: false,
    h1: false,
    h2: false,
    h3: false,
    ul: false,
    ol: false,
  });

  // Seed initial HTML once on mount (uncontrolled contenteditable to avoid caret jumps).
  useEffect(() => {
    const el = editorRef.current;
    if (!el) return;
    if (value) {
      el.innerHTML = value;
    }
    const text = el.textContent ?? '';
    setIsEmpty(text.trim().length === 0);
    setCharCount(text.length);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const refreshActive = useCallback(() => {
    if (typeof document === 'undefined') return;
    // Only reflect format state when the selection lives inside our editor.
    const sel = document.getSelection();
    const el = editorRef.current;
    if (el && sel && sel.anchorNode && !el.contains(sel.anchorNode)) return;
    const block = (document.queryCommandValue('formatBlock') || '').toLowerCase();
    setActive({
      bold: document.queryCommandState('bold'),
      italic: document.queryCommandState('italic'),
      underline: document.queryCommandState('underline'),
      strike: document.queryCommandState('strikeThrough'),
      h1: block === 'h1',
      h2: block === 'h2',
      h3: block === 'h3',
      ul: document.queryCommandState('insertUnorderedList'),
      ol: document.queryCommandState('insertOrderedList'),
    });
  }, []);

  useEffect(() => {
    document.addEventListener('selectionchange', refreshActive);
    return () => document.removeEventListener('selectionchange', refreshActive);
  }, [refreshActive]);

  const handleInput = useCallback(() => {
    const el = editorRef.current;
    if (!el) return;
    const text = el.textContent ?? '';
    setIsEmpty(text.trim().length === 0);
    setCharCount(text.length);
    onChange?.(el.innerHTML);
  }, [onChange]);

  const exec = (command: string, arg?: string) => {
    editorRef.current?.focus();
    document.execCommand(command, false, arg);
    handleInput();
    refreshActive();
  };

  const toggleHeading = (tag: 'h1' | 'h2' | 'h3') => {
    const block = (document.queryCommandValue('formatBlock') || '').toLowerCase();
    exec('formatBlock', block === tag ? 'div' : tag);
  };

  // List toggle. Chrome's execCommand won't build a list on truly-empty content,
  // so when the field has no text we create the structure manually (matches Factorial,
  // which shows the bullet/number marker + placeholder on an empty field).
  const toggleList = (type: 'ul' | 'ol') => {
    const el = editorRef.current;
    if (!el) return;
    el.focus();
    const cmd = type === 'ul' ? 'insertUnorderedList' : 'insertOrderedList';
    const alreadyActive = document.queryCommandState(cmd);
    const noText = (el.textContent ?? '').trim() === '';
    if (noText && !alreadyActive) {
      el.innerHTML = `<${type}><li><br></li></${type}>`;
      const li = el.querySelector('li');
      if (li) {
        const range = document.createRange();
        range.selectNodeContents(li);
        range.collapse(true);
        const sel = window.getSelection();
        sel?.removeAllRanges();
        sel?.addRange(range);
      }
    } else if (noText && alreadyActive) {
      el.innerHTML = '';
    } else {
      document.execCommand(cmd);
    }
    handleInput();
    refreshActive();
  };

  const insertEmoji = (emoji: string) => {
    editorRef.current?.focus();
    document.execCommand('insertText', false, emoji);
    setEmojiOpen(false);
    handleInput();
  };

  const insertLink = () => {
    const url = window.prompt('Введите URL:');
    if (url) exec('createLink', url);
  };

  const btn = (activeFlag: boolean) =>
    cn(
      'w-8 h-8 rounded flex items-center justify-center transition-colors',
      activeFlag ? 'bg-teal-50 text-teal-700' : 'text-text-muted hover:bg-sidebar-hover',
    );

  return (
    <div>
      <div className="relative border border-card-border-soft rounded-fx-lg bg-white focus-within:border-border-hover">
      {/* Expand top-right */}
      <button
        type="button"
        className="absolute top-2 right-2 w-7 h-7 rounded-full border border-card-border-soft flex items-center justify-center hover:bg-sidebar-hover z-10 bg-white"
        title="Развернуть"
        aria-label="Развернуть"
      >
        <Maximize2 className="w-3.5 h-3.5 text-text-muted" />
      </button>

      {/* Editable surface — placeholder shown when there is no text (matches Factorial) */}
      <div className="relative">
        {isEmpty && (
          <div
            className={cn(
              'absolute top-3 text-fx-sm text-text-muted pointer-events-none select-none',
              // When an empty list is active, shift the placeholder past the bullet/number marker
              active.ul || active.ol ? 'left-[34px]' : 'left-3',
            )}
          >
            {placeholder}
          </div>
        )}
        <div
          ref={editorRef}
          contentEditable
          suppressContentEditableWarning
          onInput={handleInput}
          onKeyUp={refreshActive}
          onMouseUp={refreshActive}
          className="min-h-[80px] px-3 pt-3 pb-1 text-fx-sm focus:outline-none focus-visible:ring-0 focus-visible:ring-offset-0 [&_h1]:text-fx-2xl [&_h1]:font-semibold [&_h2]:text-fx-xl [&_h2]:font-semibold [&_h3]:text-fx-lg [&_h3]:font-semibold [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:list-decimal [&_ol]:pl-5 [&_a]:text-primary [&_a]:underline"
          role="textbox"
          aria-multiline="true"
        />
      </div>

      {/* Toolbar row */}
      <div className="flex items-center gap-1 px-2 pb-2 relative">
        {!expanded ? (
          <>
            <button
              type="button"
              onClick={() => setExpanded(true)}
              className="w-8 h-8 rounded border border-card-border-soft flex items-center justify-center hover:bg-sidebar-hover"
              title="Toolbar"
              aria-label="Форматирование"
            >
              <Type className="w-3.5 h-3.5 text-text-muted" />
            </button>
            <button
              type="button"
              className="w-8 h-8 rounded border border-card-border-soft flex items-center justify-center hover:bg-sidebar-hover"
              title="Прикрепить файл"
              aria-label="Прикрепить файл"
            >
              <Paperclip className="w-3.5 h-3.5 text-text-muted" />
            </button>
            <span className="text-fx-xs text-text-muted ml-2">
              {charCount}/{maxLength}
            </span>
          </>
        ) : (
          <div className="inline-flex items-center gap-0.5 origin-left animate-in fade-in zoom-in-95 slide-in-from-left-2 duration-200 ease-out">
            <button
              type="button"
              onClick={() => {
                setExpanded(false);
                setEmojiOpen(false);
              }}
              className="w-8 h-8 rounded flex items-center justify-center text-text-muted hover:bg-sidebar-hover"
              title="Закрыть"
              aria-label="Закрыть"
            >
              <X className="w-4 h-4" />
            </button>
            <span className="w-px h-5 bg-card-border-soft mx-0.5" />
            <button
              type="button"
              onClick={insertLink}
              className={btn(false)}
              title="Ссылка"
              aria-label="Ссылка"
            >
              <LinkIcon className="w-4 h-4" />
            </button>
            <button
              type="button"
              onClick={() => setEmojiOpen((o) => !o)}
              className={btn(emojiOpen)}
              title="Эмодзи"
              aria-label="Эмодзи"
            >
              <Smile className="w-4 h-4" />
            </button>
            <span className="w-px h-5 bg-card-border-soft mx-0.5" />
            <button
              type="button"
              onClick={() => exec('bold')}
              className={btn(active.bold)}
              title="Жирный"
              aria-label="Жирный"
            >
              <Bold className="w-4 h-4" />
            </button>
            <button
              type="button"
              onClick={() => exec('italic')}
              className={btn(active.italic)}
              title="Курсив"
              aria-label="Курсив"
            >
              <Italic className="w-4 h-4" />
            </button>
            <button
              type="button"
              onClick={() => exec('underline')}
              className={btn(active.underline)}
              title="Подчёркнутый"
              aria-label="Подчёркнутый"
            >
              <Underline className="w-4 h-4" />
            </button>
            <button
              type="button"
              onClick={() => exec('strikeThrough')}
              className={btn(active.strike)}
              title="Зачёркнутый"
              aria-label="Зачёркнутый"
            >
              <Strikethrough className="w-4 h-4" />
            </button>
            <span className="w-px h-5 bg-card-border-soft mx-0.5" />
            <button
              type="button"
              onClick={() => toggleHeading('h1')}
              className={cn(btn(active.h1), 'w-auto px-1.5 text-fx-xs font-semibold')}
              title="Заголовок 1"
            >
              H1
            </button>
            <button
              type="button"
              onClick={() => toggleHeading('h2')}
              className={cn(btn(active.h2), 'w-auto px-1.5 text-fx-xs font-semibold')}
              title="Заголовок 2"
            >
              H2
            </button>
            <button
              type="button"
              onClick={() => toggleHeading('h3')}
              className={cn(btn(active.h3), 'w-auto px-1.5 text-fx-xs font-semibold')}
              title="Заголовок 3"
            >
              H3
            </button>
            <span className="w-px h-5 bg-card-border-soft mx-0.5" />
            <button
              type="button"
              onClick={() => exec('justifyLeft')}
              className={btn(false)}
              title="Выравнивание"
              aria-label="Выравнивание"
            >
              <AlignLeft className="w-4 h-4" />
            </button>
            <button
              type="button"
              onClick={() => toggleList('ul')}
              className={btn(active.ul)}
              title="Маркированный список"
              aria-label="Маркированный список"
            >
              <List className="w-4 h-4" />
            </button>
            <button
              type="button"
              onClick={() => toggleList('ol')}
              className={btn(active.ol)}
              title="Нумерованный список"
              aria-label="Нумерованный список"
            >
              <ListOrdered className="w-4 h-4" />
            </button>
            <button
              type="button"
              className={btn(false)}
              title="Дополнительные опции"
              aria-label="Дополнительные опции"
            >
              <MoreHorizontal className="w-4 h-4" />
            </button>
          </div>
        )}

        {/* Emoji popover */}
        {emojiOpen && (
          <div className="absolute bottom-full left-0 mb-2 z-30">
            <EmojiPicker onSelect={insertEmoji} />
          </div>
        )}
      </div>
      </div>

      {footerHint && <p className="text-fx-xs text-text-muted text-right mt-1">{footerHint}</p>}
    </div>
  );
}
