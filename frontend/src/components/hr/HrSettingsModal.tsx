import { useState } from "react";
import { motion } from "framer-motion";
import clsx from "clsx";
import toast from "react-hot-toast";
import {
  Archive, Code2, Trash2, FileText, Filter, GitBranch, History, Layers, Link2, Mail, Palette, Puzzle, Search, Sparkles, User, Users, Wand2, X,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

// Окно «Настройки HR» из HR-сайдбара (вынесено из Layout, 20.10.2026).

type HrSettingsItem = {
  title: string;
  description: string;
  icon: LucideIcon;
  color: string;
  path?: string;
  adminOnly?: boolean;
  superadminOnly?: boolean;
  missing?: boolean;
};

const HR_SETTINGS_ORG_ITEMS: HrSettingsItem[] = [
  {
    title: "Факториал",
    description: "Сотрудники, документы и личный кабинет",
    icon: Users,
    color: "text-[var(--hf-status-indigo)]",
    path: "/factorial",
  },
  {
    title: "Импорт CSV",
    description: "Загрузка кандидатов из CSV-файла (ClickUp и др.)",
    icon: FileText,
    color: "text-[var(--hf-status-cyan)]",
    path: "/import",
    adminOnly: true,
  },
  {
    // Корзина (20.10.2026): кто и когда удалял кандидатов, вернуть в течение 7 дней.
    // С 23.10.2026 — всем рекрутёрам (владелец), удалённого можно открыть.
    title: "Удалённые кандидаты",
    description: "Кто и когда удалял; открыть и вернуть кандидата в течение 7 дней",
    icon: Trash2,
    color: "text-[var(--hf-red-500)]",
    path: "/deleted-candidates",
  },
  {
    // Журнал действий (21.10.2026): кто что делал — каждое изменение в HR.
    title: "Журнал действий",
    description: "Кто, когда и что менял: этапы, комментарии, карточки, воронки",
    icon: History,
    color: "text-[var(--hf-status-cyan)]",
    path: "/audit-log",
    adminOnly: true,
  },
  {
    // Расход ИИ (21.10.2026): сколько и на что уходит Claude.
    title: "Расход ИИ",
    description: "Сколько уходит на Claude и на что: разбор резюме, созвоны, бот…",
    icon: Sparkles,
    color: "text-[var(--hf-status-pink)]",
    path: "/ai-usage",
    adminOnly: true,
  },
  {
    title: "Рекрутеры и заказчики",
    description: "Добавление пользователей и настройка прав",
    icon: Users,
    color: "text-[var(--hf-red-500)]",
    path: "/users",
    adminOnly: true,
  },
  {
    title: "Воронка",
    description: "Этапы подбора, воронки, отказы и контроль сроков",
    icon: Filter,
    color: "text-[var(--hf-status-pink)]",
    path: "/all-candidates",
  },
  {
    title: "Бизнес-процесс",
    description: "Заявки, вакансии, справочники, метки и источники резюме",
    icon: GitBranch,
    color: "text-[var(--hf-status-green)]",
    path: "/vacancies",
  },
  {
    title: "Шаблоны, оценка и анкеты",
    description: "Письма, анкеты, обратная связь и оценка рекрутмента",
    icon: Layers,
    color: "text-[var(--hf-status-cyan)]",
    path: "/email-templates",
  },
  {
    title: "Темы оформления",
    description: "Цвета, темы и персонализация интерфейса",
    icon: Palette,
    color: "text-[var(--hf-status-lime)]",
    missing: true,
  },
  {
    title: "Сбор откликов",
    description: "Карьерный сайт и публикация вакансий",
    icon: Link2,
    color: "text-[var(--hf-status-orange)]",
    path: "/form-builder",
  },
  {
    title: "API и вебхуки",
    description: "Интеграция с вашими внутренними ресурсами",
    icon: Code2,
    color: "text-[var(--hf-status-blue)]",
    missing: true,
  },
  {
    title: "Архив кандидатов",
    description: "Теневая база: скрытые дубликаты и архив (только суперадмин)",
    icon: Archive,
    color: "text-[var(--hf-status-orange)]",
    path: "/candidate-archive",
    superadminOnly: true,
  },
];

const HR_SETTINGS_MY_ITEMS: HrSettingsItem[] = [
  {
    title: "Профиль",
    description: "Обо мне, часовой пояс, аккаунт, язык интерфейса",
    icon: User,
    color: "text-[var(--hf-status-yellow)]",
    path: "/my-profile",
  },
  {
    title: "Почта и календарь",
    description: "Google, Exchange, Outlook365 и другие",
    icon: Mail,
    color: "text-[var(--hf-status-cyan)]",
    missing: true,
  },
  {
    title: "Волшебная кнопка",
    description: "Сохранение резюме с 20+ сайтов одним кликом",
    icon: Wand2,
    color: "text-[var(--hf-red-400)]",
    path: "/extension",
  },
  {
    title: "Джоб-сайты",
    description: "HH, Avito, Хабр Карьера, AmazingHiring и другие",
    icon: FileText,
    color: "text-[var(--hf-status-pink)]",
    missing: true,
  },
  {
    title: "Интеграции",
    description: "Zoom, MS Teams, Google Meet и другие",
    icon: Puzzle,
    color: "text-[var(--hf-status-indigo)]",
    missing: true,
  },
];

function HrSettingsCard({
  item,
  onSelect,
}: {
  item: HrSettingsItem;
  onSelect: (item: HrSettingsItem) => void;
}) {
  const Icon = item.icon;

  return (
    <button
      type="button"
      onClick={() => onSelect(item)}
      className="hf-hr-settings-card"
    >
      <Icon
        className={clsx(
          "hf-hr-settings-card-icon",
          item.color,
        )}
      />
      <span className="hf-hr-settings-card-content">
        <span className="hf-hr-settings-card-title">
          {item.title}
        </span>
        <span className="hf-hr-settings-card-desc">
          {item.description}
        </span>
      </span>
    </button>
  );
}

export default function HrSettingsModal({
  canUseAdmin,
  isSuperadmin,
  onClose,
  onNavigate,
}: {
  canUseAdmin: boolean;
  isSuperadmin: boolean;
  onClose: () => void;
  onNavigate: (path: string) => void;
}) {
  const [query, setQuery] = useState("");
  const normalizedQuery = query.trim().toLowerCase();
  const filterItems = (items: HrSettingsItem[]) => {
    // Суперадм-только пункты (напр. «Архив кандидатов») скрываем от остальных
    const visible = items.filter((item) => !item.superadminOnly || isSuperadmin);
    return normalizedQuery
      ? visible.filter((item) =>
          `${item.title} ${item.description}`
            .toLowerCase()
            .includes(normalizedQuery),
        )
      : visible;
  };
  const orgItems = filterItems(HR_SETTINGS_ORG_ITEMS);
  const myItems = filterItems(HR_SETTINGS_MY_ITEMS);

  const handleSelect = (item: HrSettingsItem) => {
    if (item.missing) {
      toast("Этого раздела пока нет в HR-bot, оставляем как отсутствующую фичу Huntflow");
      return;
    }
    if (item.adminOnly && !canUseAdmin) {
      toast("Раздел доступен только администратору");
      return;
    }
    if (item.superadminOnly && !isSuperadmin) {
      toast("Раздел доступен только суперадмину");
      return;
    }
    if (item.path) {
      onNavigate(item.path);
    }
  };

  return (
    <div
      className="hf-hr-settings-overlay"
      onMouseDown={onClose}
    >
      <motion.div
        initial={{ opacity: 0, y: -10, scale: 0.985 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: -8, scale: 0.985 }}
        transition={{ duration: 0.14, ease: "easeOut" }}
        onMouseDown={(event) => event.stopPropagation()}
        className="hf-hr-settings-modal"
      >
        <div className="hf-hr-settings-header">
          <button
            type="button"
            onClick={onClose}
            aria-label="Закрыть настройки"
            className="hf-hr-settings-close"
          >
            <X className="hf-hr-settings-close-icon" />
          </button>
          <h2 className="hf-hr-settings-title">
            HR-bot
          </h2>
          <p className="hf-hr-settings-subtitle">
            Настройки рабочего пространства и рекрутингового контура
          </p>
        </div>

        <div className="hf-hr-settings-body">
          <label className="hf-hr-settings-search">
            <Search
              className="hf-hr-settings-search-icon"
            />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              autoFocus
              placeholder="Поиск"
              className="hf-hr-settings-search-input"
            />
          </label>

          <div className="hf-hr-settings-grid hf-hr-settings-grid-first">
            {orgItems.map((item) => (
              <HrSettingsCard
                key={item.title}
                item={item}
                onSelect={handleSelect}
              />
            ))}
          </div>

          <div className="hf-hr-settings-section">
            <h3 className="hf-hr-settings-section-title">
              Мой профиль
            </h3>
            <div className="hf-hr-settings-grid hf-hr-settings-grid-first">
              {myItems.map((item) => (
                <HrSettingsCard
                  key={item.title}
                  item={item}
                  onSelect={handleSelect}
                />
              ))}
            </div>
          </div>
        </div>
      </motion.div>
    </div>
  );
}
