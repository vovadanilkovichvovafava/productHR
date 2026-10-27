import { cn } from '@/factorial/lib/cn';

interface Step {
  number: number;
  label: string;
}

export default function StepNavigator({
  steps,
  activeStep,
}: {
  steps: Step[];
  activeStep: number;
}) {
  return (
    <div className="space-y-1">
      {steps.map((s) => {
        const active = s.number === activeStep;
        const completed = s.number < activeStep;
        return (
          <div
            key={s.number}
            className={cn(
              'flex items-center gap-3 px-3 py-2 rounded-fx-lg text-fx-sm',
              active && 'bg-rose-50 font-medium text-text-primary',
              !active && 'text-text-muted'
            )}
          >
            <span
              className={cn(
                'w-6 h-6 rounded-full flex items-center justify-center text-fx-xs font-medium border',
                active && 'bg-primary text-white border-primary',
                completed && 'bg-primary text-white border-primary',
                !active && !completed && 'border-border'
              )}
            >
              {completed ? '✓' : s.number}
            </span>
            <span className="truncate">{s.label}</span>
          </div>
        );
      })}
    </div>
  );
}
