import clsx from "clsx";

/**
 * Маленький Huntflow-спиннер загрузки (.hf-loading-spinner). Вынесён из
 * AllCandidatesPage в общий модуль, чтобы и страница, и CandidateVacancyCard
 * импортировали его отсюда — без циклического импорта page ↔ component.
 */
export function HfLoadingSpinner({
  size,
  stroke,
  className,
}: {
  size?: number | string;
  stroke?: number | string;
  className?: string;
}) {
  return (
    <span
      className={clsx("hf-loading-spinner", className)}
      style={
        size || stroke
          ? {
              width: size,
              height: size,
              borderWidth: stroke,
            }
          : undefined
      }
      aria-hidden="true"
    />
  );
}
