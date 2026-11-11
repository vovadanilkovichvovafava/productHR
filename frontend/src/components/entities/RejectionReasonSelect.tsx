import { useEffect, useMemo, useRef, useState } from "react";
import clsx from "clsx";
import { Check, ChevronDown, Search } from "lucide-react";

import { REJECTION_REASONS } from "@/constants/hrStages";

/**
 * «Причина отказа» в окне смены этапа (Мария, 11.11.2026; вид — как в
 * Huntflow: поле, по нажатию список с поиском и галочкой у выбранной).
 */
export function RejectionReasonSelect({
  value,
  onChange,
}: {
  value: string | null;
  onChange: (reason: string | null) => void;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const rootRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    searchRef.current?.focus();
    const close = (e: PointerEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, [open]);

  const options = useMemo(() => {
    const q = query.trim().toLowerCase().replace(/ё/g, "е");
    return q
      ? REJECTION_REASONS.filter((r) => r.toLowerCase().replace(/ё/g, "е").includes(q))
      : REJECTION_REASONS;
  }, [query]);

  return (
    <div className="hf-reject-reason" ref={rootRef}>
      <button
        type="button"
        className={clsx("hf-reject-reason-field", !value && "hf-reject-reason-empty")}
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <span className="truncate">{value || "Причина отказа"}</span>
        <ChevronDown className={clsx("hf-reject-reason-caret", open && "rotate-180")} />
      </button>
      {open && (
        <div className="hf-reject-reason-menu" role="listbox">
          <label className="hf-reject-reason-search">
            <Search className="h-4 w-4 shrink-0 text-[var(--hf-main-500)]" />
            <input
              ref={searchRef}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Поиск..."
              onKeyDown={(e) => {
                if (e.key === "Escape") setOpen(false);
                if (e.key === "Enter" && options.length === 1) {
                  e.preventDefault();
                  onChange(options[0]);
                  setOpen(false);
                }
              }}
            />
          </label>
          <div className="hf-reject-reason-list huntflow-scrollbar">
            {options.map((r) => (
              <button
                key={r}
                type="button"
                role="option"
                aria-selected={value === r}
                className="hf-reject-reason-option"
                onClick={() => {
                  onChange(value === r ? null : r);
                  setOpen(false);
                  setQuery("");
                }}
              >
                <span className="hf-reject-reason-check">
                  {value === r && <Check className="h-4 w-4" />}
                </span>
                {r}
              </button>
            ))}
            {options.length === 0 && (
              <div className="hf-reject-reason-none">Ничего не нашли — напишите причину в комментарии</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
