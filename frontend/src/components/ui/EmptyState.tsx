import { motion } from 'framer-motion';
import {
  LucideIcon,
  Briefcase,
  Users,
  Search,
  Inbox,
  Upload,
  Plus,
  Filter,
  AlertCircle,
  RefreshCw,
  UserPlus,
  FolderOpen,
  Sparkles,
  Target,
  MessageSquare,
  Phone,
  Clock
} from 'lucide-react';
import { Link } from 'react-router-dom';
import clsx from 'clsx';
import { ReactNode } from 'react';

// Animation variants
const containerVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: {
    opacity: 1,
    y: 0,
    transition: {
      duration: 0.4,
      ease: 'easeOut',
      staggerChildren: 0.1
    }
  }
};

const itemVariants = {
  hidden: { opacity: 0, y: 10 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.3 }
  }
};

const iconVariants = {
  hidden: { scale: 0.8, opacity: 0 },
  visible: {
    scale: 1,
    opacity: 1,
    transition: {
      type: 'spring',
      stiffness: 200,
      damping: 15
    }
  }
};

export type EmptyStateVariant = 'primary' | 'search' | 'filter' | 'error';

interface ActionButton {
  label: string;
  onClick: () => void;
  variant?: 'primary' | 'secondary' | 'ghost';
  icon?: LucideIcon;
}

interface EmptyStateProps {
  icon?: LucideIcon;
  title: string;
  description?: string;
  actions?: ActionButton[];
  link?: {
    label: string;
    to: string;
  };
  className?: string;
  size?: 'sm' | 'md' | 'lg';
  variant?: EmptyStateVariant;
  tips?: string[];
  illustration?: ReactNode;
  query?: string;
  animated?: boolean;
}

export default function EmptyState({
  icon: Icon = Inbox,
  title,
  description,
  actions,
  link,
  className,
  size = 'md',
  variant = 'primary',
  tips,
  illustration,
  query,
  animated = true
}: EmptyStateProps) {
  const sizeStyles = {
    sm: {
      container: 'py-8',
      icon: 'w-10 h-10',
      illustrationSize: 'w-20 h-20',
      title: 'text-base',
      description: 'text-sm',
      button: 'px-3 py-1.5 text-sm',
      iconBg: 'w-16 h-16'
    },
    md: {
      container: 'py-12',
      icon: 'w-12 h-12',
      illustrationSize: 'w-28 h-28',
      title: 'text-lg',
      description: 'text-sm',
      button: 'px-4 py-2',
      iconBg: 'w-20 h-20'
    },
    lg: {
      container: 'py-16',
      icon: 'w-16 h-16',
      illustrationSize: 'w-36 h-36',
      title: 'text-xl',
      description: 'text-base',
      button: 'px-5 py-2.5',
      iconBg: 'w-24 h-24'
    }
  };

  const variantStyles = {
    primary: {
      iconBg: 'bg-gradient-to-br from-cyan-500/20 to-blue-500/20 border-cyan-500/30',
      iconColor: 'text-cyan-400',
      titleColor: 'text-white/80',
      descColor: 'text-white/50'
    },
    search: {
      iconBg: 'bg-gradient-to-br from-amber-500/20 to-orange-500/20 border-amber-500/30',
      iconColor: 'text-amber-400',
      titleColor: 'text-white/80',
      descColor: 'text-white/50'
    },
    filter: {
      iconBg: 'bg-gradient-to-br from-purple-500/20 to-pink-500/20 border-purple-500/30',
      iconColor: 'text-purple-400',
      titleColor: 'text-white/80',
      descColor: 'text-white/50'
    },
    error: {
      iconBg: 'bg-gradient-to-br from-red-500/20 to-rose-500/20 border-red-500/30',
      iconColor: 'text-red-400',
      titleColor: 'text-white/80',
      descColor: 'text-white/50'
    }
  };

  const styles = sizeStyles[size];
  const variantStyle = variantStyles[variant];

  const Wrapper = animated ? motion.div : 'div';
  const wrapperProps = animated ? {
    variants: containerVariants,
    initial: 'hidden',
    animate: 'visible'
  } : {};

  const ItemWrapper = animated ? motion.div : 'div';
  const itemProps = animated ? { variants: itemVariants } : {};

  return (
    <Wrapper
      className={clsx('text-center flex flex-col items-center', styles.container, className)}
      {...wrapperProps}
      role="status"
      aria-label={title}
    >
      {/* Illustration or Icon */}
      <ItemWrapper {...(animated ? { variants: iconVariants } : {})}>
        {illustration ? (
          <div className={clsx('mb-6', styles.illustrationSize)}>
            {illustration}
          </div>
        ) : (
          <div
            className={clsx(
              'rounded-2xl border flex items-center justify-center mb-6',
              styles.iconBg,
              variantStyle.iconBg
            )}
          >
            <Icon className={clsx(styles.icon, variantStyle.iconColor)} aria-hidden="true" />
          </div>
        )}
      </ItemWrapper>

      {/* Title */}
      <ItemWrapper {...itemProps}>
        <h3 className={clsx('font-semibold', styles.title, variantStyle.titleColor)}>
          {query ? title.replace('{query}', query) : title}
        </h3>
      </ItemWrapper>

      {/* Description */}
      {description && (
        <ItemWrapper {...itemProps}>
          <p className={clsx('mt-2 max-w-md', styles.description, variantStyle.descColor)}>
            {description}
          </p>
        </ItemWrapper>
      )}

      {/* Tips */}
      {tips && tips.length > 0 && (
        <ItemWrapper {...itemProps}>
          <div className="mt-4 p-4 glass-light rounded-xl max-w-md">
            <p className="text-xs text-white/40 uppercase tracking-wider mb-2">Советы</p>
            <ul className="space-y-1.5">
              {tips.map((tip) => (
                <li key={tip} className="text-sm text-white/60 flex items-start gap-2">
                  <span className="text-cyan-400 flex-shrink-0">-</span>
                  {tip}
                </li>
              ))}
            </ul>
          </div>
        </ItemWrapper>
      )}

      {/* Actions */}
      {actions && actions.length > 0 && (
        <ItemWrapper {...itemProps}>
          <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
            {actions.map((actionItem) => {
              const ActionIcon = actionItem.icon;
              const buttonVariantStyles = {
                primary: 'bg-cyan-600 hover:bg-cyan-500 text-white',
                secondary: 'glass-light hover:bg-white/10 text-white/80',
                ghost: 'hover:bg-dark-800/50 text-white/60 hover:text-white/80'
              };
              return (
                <button
                  key={actionItem.label}
                  onClick={actionItem.onClick}
                  className={clsx(
                    'rounded-lg transition-all duration-200',
                    'flex items-center gap-2',
                    styles.button,
                    buttonVariantStyles[actionItem.variant || 'primary']
                  )}
                >
                  {ActionIcon && <ActionIcon className="w-4 h-4" aria-hidden="true" />}
                  {actionItem.label}
                </button>
              );
            })}
          </div>
        </ItemWrapper>
      )}

      {/* Link */}
      {link && (
        <ItemWrapper {...itemProps}>
          <Link
            to={link.to}
            className={clsx(
              'mt-4 text-cyan-400 hover:text-cyan-300 transition-colors inline-flex items-center gap-1',
              styles.description
            )}
          >
            {link.label} &rarr;
          </Link>
        </ItemWrapper>
      )}
    </Wrapper>
  );
}

// ===== SPECIALIZED EMPTY STATES =====

// Illustration components for visual appeal
function CandidatesIllustration({ className }: { className?: string }) {
  return (
    <div className={clsx('relative', className)}>
      <div className="absolute inset-0 bg-gradient-to-br from-cyan-500/10 to-purple-500/10 rounded-full blur-xl" />
      <div className="relative flex items-center justify-center">
        <div className="w-12 h-12 rounded-full bg-cyan-500/20 border border-cyan-500/30 flex items-center justify-center -mr-4 z-10">
          <Users className="w-6 h-6 text-cyan-400" />
        </div>
        <div className="w-10 h-10 rounded-full bg-purple-500/20 border border-purple-500/30 flex items-center justify-center -mr-3 z-0">
          <UserPlus className="w-5 h-5 text-purple-400" />
        </div>
        <div className="w-8 h-8 rounded-full bg-blue-500/20 border border-blue-500/30 flex items-center justify-center">
          <Sparkles className="w-4 h-4 text-blue-400" />
        </div>
      </div>
    </div>
  );
}

function VacanciesIllustration({ className }: { className?: string }) {
  return (
    <div className={clsx('relative', className)}>
      <div className="absolute inset-0 bg-gradient-to-br from-blue-500/10 to-indigo-500/10 rounded-full blur-xl" />
      <div className="relative flex items-center justify-center gap-2">
        <div className="w-14 h-14 rounded-xl bg-blue-500/20 border border-blue-500/30 flex items-center justify-center">
          <Briefcase className="w-7 h-7 text-blue-400" />
        </div>
        <div className="flex flex-col gap-1">
          <div className="w-16 h-2 bg-white/10 rounded-full" />
          <div className="w-12 h-2 bg-white/10 rounded-full" />
          <div className="w-10 h-2 bg-white/10 rounded-full" />
        </div>
      </div>
    </div>
  );
}

function SearchIllustration({ className }: { className?: string }) {
  return (
    <div className={clsx('relative', className)}>
      <div className="absolute inset-0 bg-gradient-to-br from-amber-500/10 to-orange-500/10 rounded-full blur-xl" />
      <div className="relative">
        <div className="w-16 h-16 rounded-full border-2 border-amber-500/40 flex items-center justify-center">
          <Search className="w-8 h-8 text-amber-400" />
        </div>
        <div className="absolute -bottom-1 -right-1 w-6 h-6 rounded-full bg-amber-500/20 border border-amber-500/30 flex items-center justify-center">
          <span className="text-xs text-amber-400">?</span>
        </div>
      </div>
    </div>
  );
}

function KanbanIllustration({ className }: { className?: string }) {
  return (
    <div className={clsx('relative', className)}>
      <div className="absolute inset-0 bg-gradient-to-br from-blue-500/10 to-cyan-500/10 rounded-full blur-xl" />
      <div className="relative flex items-center gap-2">
        {[1, 2, 3].map((i) => (
          <div
            key={i}
            className={clsx(
              'w-8 rounded-lg glass-light flex flex-col items-center py-2 gap-1',
              i === 1 && 'h-16',
              i === 2 && 'h-20',
              i === 3 && 'h-12'
            )}
          >
            {Array.from({ length: i }).map((_, j) => (
              <div key={`kanban-item-${i}-${j}`} className="w-5 h-3 bg-blue-500/20 rounded" />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

function AnalysisIllustration({ className }: { className?: string }) {
  return (
    <div className={clsx('relative', className)}>
      <div className="absolute inset-0 bg-gradient-to-br from-purple-500/10 to-pink-500/10 rounded-full blur-xl" />
      <div className="relative flex items-center justify-center">
        <div className="w-16 h-16 rounded-xl bg-purple-500/20 border border-purple-500/30 flex items-center justify-center">
          <Sparkles className="w-8 h-8 text-purple-400" />
        </div>
        <div className="absolute -top-2 -right-2 w-6 h-6 rounded-full bg-pink-500/20 border border-pink-500/30 flex items-center justify-center animate-pulse">
          <Target className="w-3 h-3 text-pink-400" />
        </div>
      </div>
    </div>
  );
}

// ===== EMPTY STATE COMPONENTS =====

interface EmptyCandidatesProps {
  onUploadResume?: () => void;
  onCreateCandidate?: () => void;
  variant?: 'primary' | 'search' | 'filter';
  query?: string;
}

export function EmptyCandidates({
  onUploadResume,
  onCreateCandidate,
  variant = 'primary',
  query
}: EmptyCandidatesProps) {
  if (variant === 'search' && query) {
    return (
      <EmptyState
        variant="search"
        illustration={<SearchIllustration className="w-full h-full" />}
        title="Ничего не найдено"
        description={`По запросу "${query}" кандидаты не найдены`}
        tips={[
          'Проверьте правильность написания',
          'Попробуйте использовать меньше слов',
          'Поиск работает по имени, телефону и email'
        ]}
        size="md"
      />
    );
  }

  if (variant === 'filter') {
    return (
      <EmptyState
        variant="filter"
        icon={Filter}
        title="Нет подходящих кандидатов"
        description="Под выбранные фильтры не попадает ни один кандидат"
        tips={[
          'Попробуйте ослабить критерии поиска',
          'Уберите часть фильтров',
          'Измените диапазон зарплаты или дат'
        ]}
        size="md"
      />
    );
  }

  return (
    <EmptyState
      illustration={<CandidatesIllustration className="w-full h-full" />}
      title="Пока нет кандидатов"
      description="Загрузите первое резюме или создайте кандидата вручную, чтобы начать формировать базу талантов"
      actions={[
        ...(onUploadResume ? [{
          label: 'Загрузить резюме',
          onClick: onUploadResume,
          variant: 'secondary' as const,
          icon: Upload
        }] : []),
        ...(onCreateCandidate ? [{
          label: 'Создать кандидата',
          onClick: onCreateCandidate,
          variant: 'primary' as const,
          icon: Plus
        }] : [])
      ]}
      size="lg"
    />
  );
}

interface EmptyVacanciesProps {
  onCreate?: () => void;
  variant?: 'primary' | 'search' | 'filter';
  query?: string;
}

export function EmptyVacancies({
  onCreate,
  variant = 'primary',
  query
}: EmptyVacanciesProps) {
  if (variant === 'search' && query) {
    return (
      <EmptyState
        variant="search"
        illustration={<SearchIllustration className="w-full h-full" />}
        title="Вакансии не найдены"
        description={`По запросу "${query}" ничего не найдено`}
        tips={[
          'Проверьте правильность написания',
          'Попробуйте поискать по части названия'
        ]}
        size="md"
      />
    );
  }

  if (variant === 'filter') {
    return (
      <EmptyState
        variant="filter"
        icon={Filter}
        title="Нет подходящих вакансий"
        description="Под выбранные фильтры не попадает ни одна вакансия"
        tips={[
          'Попробуйте другой статус',
          'Измените диапазон зарплаты'
        ]}
        size="md"
      />
    );
  }

  return (
    <EmptyState
      illustration={<VacanciesIllustration className="w-full h-full" />}
      title="Пока нет вакансий"
      description="Создайте первую вакансию, чтобы начать подбор кандидатов и формировать воронку найма"
      actions={onCreate ? [{
        label: 'Создать вакансию',
        onClick: onCreate,
        variant: 'primary' as const,
        icon: Plus
      }] : []}
      size="lg"
    />
  );
}

interface EmptySearchProps {
  query: string;
  onClear?: () => void;
  entity?: 'candidates' | 'vacancies' | 'contacts' | 'generic';
}

export function EmptySearch({ query, onClear, entity = 'generic' }: EmptySearchProps) {
  const entityLabels = {
    candidates: 'кандидаты',
    vacancies: 'вакансии',
    contacts: 'контакты',
    generic: 'результаты'
  };

  return (
    <EmptyState
      variant="search"
      illustration={<SearchIllustration className="w-full h-full" />}
      title={`Ничего не найдено`}
      description={`По запросу "${query}" ${entityLabels[entity]} не найдены`}
      tips={[
        'Проверьте правильность написания',
        'Попробуйте использовать меньше слов',
        'Используйте более общие термины'
      ]}
      actions={onClear ? [{
        label: 'Сбросить поиск',
        onClick: onClear,
        variant: 'ghost' as const,
        icon: RefreshCw
      }] : []}
      size="md"
    />
  );
}

interface EmptyKanbanProps {
  onAddFromBase?: () => void;
  onUploadResume?: () => void;
}

export function EmptyKanban({ onAddFromBase, onUploadResume }: EmptyKanbanProps) {
  return (
    <EmptyState
      illustration={<KanbanIllustration className="w-full h-full" />}
      title="Нет откликов на вакансию"
      description="Добавьте первого кандидата из базы или загрузите новое резюме, чтобы начать воронку подбора"
      actions={[
        ...(onAddFromBase ? [{
          label: 'Добавить из базы',
          onClick: onAddFromBase,
          variant: 'primary' as const,
          icon: Users
        }] : []),
        ...(onUploadResume ? [{
          label: 'Загрузить резюме',
          onClick: onUploadResume,
          variant: 'secondary' as const,
          icon: Upload
        }] : [])
      ]}
      size="lg"
    />
  );
}

interface EmptyAnalysisProps {
  onRunAnalysis?: () => void;
  isLoading?: boolean;
}

export function EmptyAnalysis({ onRunAnalysis, isLoading }: EmptyAnalysisProps) {
  return (
    <EmptyState
      illustration={<AnalysisIllustration className="w-full h-full" />}
      title="AI-анализ не проводился"
      description="Запустите анализ, чтобы получить детальную оценку кандидата с помощью искусственного интеллекта"
      actions={onRunAnalysis ? [{
        label: isLoading ? 'Анализ...' : 'Запустить анализ',
        onClick: onRunAnalysis,
        variant: 'primary' as const,
        icon: Sparkles
      }] : []}
      size="md"
    />
  );
}

interface EmptyFilesProps {
  onUpload?: () => void;
}

export function EmptyFiles({ onUpload }: EmptyFilesProps) {
  return (
    <EmptyState
      icon={FolderOpen}
      title="Нет прикреплённых файлов"
      description="Загрузите резюме, документы или другие файлы, связанные с этим контактом"
      actions={onUpload ? [{
        label: 'Загрузить файл',
        onClick: onUpload,
        variant: 'primary' as const,
        icon: Upload
      }] : []}
      size="sm"
    />
  );
}

interface EmptyChatsProps {
  onLink?: () => void;
}

export function EmptyChats({ onLink }: EmptyChatsProps) {
  return (
    <EmptyState
      icon={MessageSquare}
      title="Нет связанных чатов"
      description="Привяжите чат из Telegram для отслеживания коммуникации"
      actions={onLink ? [{
        label: 'Привязать чат',
        onClick: onLink,
        variant: 'secondary' as const,
        icon: Plus
      }] : []}
      size="sm"
    />
  );
}

interface EmptyCallsProps {
  onLink?: () => void;
}

export function EmptyCalls({ onLink }: EmptyCallsProps) {
  return (
    <EmptyState
      icon={Phone}
      title="Нет записей звонков"
      description="Привяжите записи звонков для хранения истории общения"
      actions={onLink ? [{
        label: 'Привязать звонок',
        onClick: onLink,
        variant: 'secondary' as const,
        icon: Plus
      }] : []}
      size="sm"
    />
  );
}

interface EmptyHistoryProps {}

export function EmptyHistory({}: EmptyHistoryProps) {
  return (
    <EmptyState
      icon={Clock}
      title="История пуста"
      description="Здесь будет отображаться история изменений и действий"
      size="sm"
    />
  );
}

interface EmptyEntityVacanciesProps {
  onAdd?: () => void;
}

export function EmptyEntityVacancies({ onAdd }: EmptyEntityVacanciesProps) {
  return (
    <EmptyState
      icon={Briefcase}
      title="Нет откликов на вакансии"
      description="Добавьте кандидата на вакансию для отслеживания в воронке подбора"
      actions={onAdd ? [{
        label: 'Добавить в вакансию',
        onClick: onAdd,
        variant: 'primary' as const,
        icon: Plus
      }] : []}
      size="sm"
    />
  );
}

interface EmptyErrorProps {
  message?: string;
  onRetry?: () => void;
}

export function EmptyError({ message, onRetry }: EmptyErrorProps) {
  return (
    <EmptyState
      variant="error"
      icon={AlertCircle}
      title="Произошла ошибка"
      description={message || 'Не удалось загрузить данные. Попробуйте ещё раз.'}
      actions={onRetry ? [{
        label: 'Повторить',
        onClick: onRetry,
        variant: 'primary' as const,
        icon: RefreshCw
      }] : []}
      size="md"
    />
  );
}

interface EmptyRecommendationsProps {
  entityType?: 'candidate' | 'vacancy';
}

export function EmptyRecommendations({ entityType = 'candidate' }: EmptyRecommendationsProps) {
  return (
    <EmptyState
      icon={Target}
      title={entityType === 'candidate' ? 'Нет рекомендаций' : 'Нет подходящих кандидатов'}
      description={
        entityType === 'candidate'
          ? 'Для этого кандидата пока нет подходящих вакансий'
          : 'Для этой вакансии пока нет подходящих кандидатов'
      }
      size="sm"
    />
  );
}
