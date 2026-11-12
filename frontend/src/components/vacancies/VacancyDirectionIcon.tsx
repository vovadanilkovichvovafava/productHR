import {
  BadgeDollarSign,
  BarChart3,
  Briefcase,
  Clapperboard,
  Code2,
  Folder,
  Headphones,
  Palette,
  PenLine,
  Scale,
  Target,
  TrendingUp,
  UserSearch,
  Wallet,
  type LucideIcon,
} from "lucide-react";
import type { VacancyDirection } from "@/utils/vacancyDirection";

// Значок направления вакансии: левая панель («Мои вакансии») и поле
// «Направление» в форме вакансии. Иконка и оттенок плашки — здесь, правила
// угадывания — utils/vacancyDirection.ts.

export const DIRECTION_ICONS: Record<VacancyDirection, { Icon: LucideIcon; hue: number }> = {
  traffic: { Icon: Target, hue: 210 },
  video: { Icon: Clapperboard, hue: 335 },
  design: { Icon: Palette, hue: 290 },
  content: { Icon: PenLine, hue: 30 },
  analytics: { Icon: BarChart3, hue: 185 },
  dev: { Icon: Code2, hue: 250 },
  recruiting: { Icon: UserSearch, hue: 160 },
  legal: { Icon: Scale, hue: 0 },
  finance: { Icon: Wallet, hue: 45 },
  support: { Icon: Headphones, hue: 15 },
  growth: { Icon: TrendingUp, hue: 140 },
  sales: { Icon: BadgeDollarSign, hue: 95 },
  management: { Icon: Briefcase, hue: 225 },
  other: { Icon: Folder, hue: 220 },
};

/** Иконка без плашки — для строк выпадающего списка в форме. */
export function VacancyDirectionGlyph({ direction, className }: { direction: VacancyDirection; className?: string }) {
  const { Icon, hue } = DIRECTION_ICONS[direction];
  return (
    <Icon
      aria-hidden="true"
      strokeWidth={1.9}
      className={className}
      style={{ color: `hsl(${hue} 65% 45%)` }}
    />
  );
}
