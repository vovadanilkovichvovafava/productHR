import {
  PanelLeftClose,
  PanelLeftOpen,
  Home,
  Mail,
  Calendar as CalendarIcon,
  Megaphone,
  User,
  Palmtree as TreePalm,
  Target,
  FolderOpen,
  Users,
  Folder,
  BookOpen,
  Ticket,
  LineChart as ChartLine,
  BarChart3 as ChartBar,
  CreditCard,
  Workflow,
  Settings as SettingsIcon,
} from 'lucide-react';
import { ROUTES } from '@/factorial/lib/routes';
import { useSidebarStore } from '@/factorial/stores/useSidebarStore';
import SidebarSearch from './SidebarSearch';
import SidebarItem from './SidebarItem';
import SidebarSection from './SidebarSection';
import SidebarUserFooter from './SidebarUserFooter';

const TOP_ITEMS = [
  { icon: Home, label: 'Главная', href: ROUTES.dashboard },
  { icon: Mail, label: 'Входящие', href: ROUTES.inbox },
  { icon: CalendarIcon, label: 'Календарь', href: ROUTES.calendar },
  { icon: Megaphone, label: 'Что нового', href: ROUTES.discover },
];

const SECTIONS = [
  {
    key: 'personal',
    label: 'Личное',
    items: [
      { icon: User, label: 'Профиль', href: ROUTES.profile },
      { icon: TreePalm, label: 'Отпуска', href: ROUTES.timeOff },
      { icon: Target, label: 'Задачи', href: ROUTES.tasks },
      { icon: FolderOpen, label: 'Мои документы', href: ROUTES.myDocuments },
    ],
  },
  {
    key: 'company',
    label: 'Компания',
    items: [
      { icon: Users, label: 'Сотрудники', href: ROUTES.employees },
      { icon: Folder, label: 'Документы', href: ROUTES.files },
      { icon: BookOpen, label: 'Политики', href: ROUTES.pages },
      { icon: Ticket, label: 'Тикеты', href: ROUTES.ticketing },
    ],
  },
  {
    key: 'talents',
    label: 'Таланты',
    items: [{ icon: ChartLine, label: 'Аналитика', href: ROUTES.talentAnalytics }],
  },
  {
    key: 'other',
    label: 'Другое',
    items: [
      { icon: ChartBar, label: 'Аналитика', href: ROUTES.analytics },
      { icon: CreditCard, label: 'Биллинг', href: '#', external: true },
      { icon: Workflow, label: 'Рабочие процессы', href: ROUTES.workflows },
      { icon: SettingsIcon, label: 'Настройки', href: ROUTES.settings },
    ],
  },
];

export default function Sidebar() {
  const { collapsed, toggleCollapsed } = useSidebarStore();

  return (
    <aside className="h-full flex flex-col bg-sidebar-bg border-r border-border">
      <div className="p-3 border-b border-border">
        <div className="flex items-center gap-2 mb-3">
          <div className="w-8 h-8 rounded-fx-lg bg-logo-gradient flex items-center justify-center text-white font-bold text-fx-sm shrink-0">
            M
          </div>
          {!collapsed && (
            <span className="flex-1 text-fx-sm font-semibold text-text-primary truncate">
              MSTech L.L.C-FZ
            </span>
          )}
          <button
            onClick={toggleCollapsed}
            className="p-1 rounded hover:bg-sidebar-hover transition-colors"
            aria-label={collapsed ? 'Развернуть сайдбар' : 'Свернуть сайдбар'}
          >
            {collapsed ? <PanelLeftOpen className="w-4 h-4" /> : <PanelLeftClose className="w-4 h-4" />}
          </button>
        </div>
        {!collapsed && <SidebarSearch />}
      </div>

      <nav className="flex-1 overflow-y-auto scrollbar-thin py-2 px-2 space-y-3">
        <div className="space-y-1">
          {TOP_ITEMS.map((item) => (
            <SidebarItem key={item.href} {...item} />
          ))}
        </div>
        {SECTIONS.map((section) => (
          <SidebarSection key={section.key} section={section} />
        ))}
      </nav>

      <div className="p-3 border-t border-border">
        <SidebarUserFooter />
      </div>
    </aside>
  );
}
