import clsx from "clsx";

/**
 * Глаз «показать / скрыть» для блоков левой панели (владелец, 11.11.2026:
 * «иконку глазика, анимированную» вместо стрелок и слов «Скрыть/Показать»).
 *
 * open — блок виден (глаз открыт); закрыт — глаз перечёркнут. При смене
 * глаз моргает (key перезапускает анимацию), черта прорисовывается или
 * стирается. Без анимации для тех, у кого она выключена в системе.
 */
export function EyeToggleIcon({ open, className }: { open: boolean; className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={clsx("hf-eye", !open && "hf-eye-off", className)}
    >
      <g key={open ? "open" : "closed"} className="hf-eye-ball">
        <path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12Z" />
        <circle cx="12" cy="12" r="3" />
      </g>
      <line className="hf-eye-slash" x1="4" y1="4" x2="20" y2="20" />
    </svg>
  );
}
