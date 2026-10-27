import { Outlet, NavLink, useNavigate, useLocation } from "react-router-dom";
import { isRequestVisibleTo, isPersonallyActive } from "@/utils/vacancy";
import { pluralRu } from "@/utils/plural";
import {
  LayoutDashboard,
  Users,
  Settings,
  Search,
  LogOut,
  Menu,
  X,
  Shield,
  UserCog,
  Briefcase,
  FolderKanban,
  GitBranch,
  Bell,
  Check,
  BarChart3,
  Plus,
  User,
  UserPlus,
  ChevronDown,
  Calendar,
  ClipboardList,
  UserCheck,
  Volume2,
  VolumeX,
  Building2,
  type LucideIcon,
} from "lucide-react";
import { useState, useMemo, useEffect, useLayoutEffect, useCallback, useRef } from "react";
import { useAuthStore } from "@/stores/authStore";
import { useVacancyStore } from "@/stores/vacancyStore";
import { useNotificationStore } from "@/stores/notificationStore";
import * as notificationsApi from "@/services/api/notifications";
import type { Notification as AppNotification } from "@/services/api/notifications";
import { isAnketaSoundMuted, setAnketaSoundMuted } from "@/utils/notificationSound";
import BackgroundEffects from "./BackgroundEffects";
import ThemeToggle from "./ThemeToggle";
import { VacancyForm } from "@/components/vacancies";
import { SidebarRequestPreviewModal } from "@/components/hr/SidebarRequestPreviewModal";
import HrSettingsModal from "@/components/hr/HrSettingsModal";
import ParserModal from "@/components/parser/ParserModal";
import TelegramConnectBanner from "@/components/TelegramConnectBanner";
import UpdateBanner from "@/components/app/UpdateBanner";
import ObserverBanner from "@/components/app/ObserverBanner";
import { NotifPeek } from "@/components/NotifPeek";
import { NotifSettings } from "@/components/NotifSettings";
import { getVacancy, getAssignableUsers } from "@/services/api/vacancies";
import type { Vacancy } from "@/types";
import { AnimatePresence, motion } from "framer-motion";
import clsx from "clsx";
import toast from "react-hot-toast";

// Note: iconMap and labelMap removed — using section-based navigation now

// Map paths to data-tour attributes
const pathToTourAttribute: Record<string, string> = {
  "/all-candidates": "candidates-link",
  "/analytics": "analytics-link",
  "/dashboard": "dashboard-link",
};

const BLOCK_ICONS: Record<string, LucideIcon> = {
  hr: Briefcase,
  admin: Shield,
};

const BLOCK_ACTIVE_BG: Record<string, string> = {
  projects: "bg-[var(--hf-status-blue-badge)] text-[var(--hf-status-blue)] border-[color:var(--hf-status-blue-badge)]",
  practice: "bg-[var(--hf-status-purple-badge)] text-[var(--hf-status-purple)] border-[color:var(--hf-status-purple-badge)]",
  hr: "bg-[var(--hf-status-green-badge)] text-[var(--hf-status-green)] border-[color:var(--hf-status-green-badge)]",
  admin: "bg-[var(--hf-status-yellow-badge)] text-[var(--hf-status-yellow)] border-[color:var(--hf-status-yellow-badge)]",
};

const BLOCK_ACCENT: Record<string, string> = {
  projects: "bg-[var(--hf-status-blue-badge)] text-[var(--hf-status-blue)]",
  practice: "bg-[var(--hf-status-purple-badge)] text-[var(--hf-status-purple)]",
  hr: "bg-[var(--hf-status-green-badge)] text-[var(--hf-status-green)]",
  admin: "bg-[var(--hf-status-yellow-badge)] text-[var(--hf-status-yellow)]",
};

const HF_HR_SIDEBAR_WIDTH_STORAGE_KEY = "hf.hrSidebarWidth";
const HF_HR_SIDEBAR_WIDTH_LEGACY_STORAGE_KEY = "left-menu-width";
const HF_HR_SIDEBAR_WIDTH_MIN = 266;
const HF_HR_SIDEBAR_WIDTH_DEFAULT = 266;
const HF_HR_SIDEBAR_WIDTH_MAX = 416;
const APP_THEME_STORAGE_KEY = "theme";
const APP_DEFAULT_THEME = "dark";

function readStoredAppTheme() {
  if (typeof window === "undefined") return APP_DEFAULT_THEME;
  const stored = window.localStorage.getItem(APP_THEME_STORAGE_KEY);
  return stored === "light" || stored === "dark" ? stored : APP_DEFAULT_THEME;
}

function clampHrSidebarWidth(width: number) {
  return Math.min(
    HF_HR_SIDEBAR_WIDTH_MAX,
    Math.max(HF_HR_SIDEBAR_WIDTH_MIN, width),
  );
}

function readStoredHrSidebarWidth() {
  if (typeof window === "undefined") return HF_HR_SIDEBAR_WIDTH_DEFAULT;
  const stored =
    window.localStorage.getItem(HF_HR_SIDEBAR_WIDTH_STORAGE_KEY) ??
    window.localStorage.getItem(HF_HR_SIDEBAR_WIDTH_LEGACY_STORAGE_KEY);
  const parsed = stored ? Number.parseFloat(stored) : Number.NaN;
  return Number.isFinite(parsed)
    ? clampHrSidebarWidth(parsed)
    : HF_HR_SIDEBAR_WIDTH_DEFAULT;
}

function persistHrSidebarWidth(width: number) {
  if (typeof window === "undefined") return;
  const normalizedWidth = String(Math.round(clampHrSidebarWidth(width)));
  window.localStorage.setItem(
    HF_HR_SIDEBAR_WIDTH_STORAGE_KEY,
    normalizedWidth,
  );
  window.localStorage.setItem(
    HF_HR_SIDEBAR_WIDTH_LEGACY_STORAGE_KEY,
    normalizedWidth,
  );
}

function HfSpriteIcon({
  id,
  className,
}: {
  id: string;
  className?: string;
}) {
  return (
    <svg className={className} viewBox="0 0 20 20" aria-hidden="true">
      <use href={`/huntflow-sprite.svg#${id}`} />
    </svg>
  );
}

type SidebarVacancyMode = "view" | "edit";


// FAB — floating action button for HR block
function FABButton({
  onCreateVacancy,
  onAddCandidate,
}: {
  onCreateVacancy: () => void;
  onAddCandidate: () => void;
}) {
  const [open, setOpen] = useState(false);

  // Над нижним меню, а не поверх него: кнопка закрывала пункт «Заявки»,
  // и на телефоне до него было не дотянуться (26.10.2026). Показывается только
  // там, где есть нижнее меню (lg:hidden в Layout).
  return (
    <div className="fixed right-4 bottom-[calc(84px+env(safe-area-inset-bottom,0px))] z-50">
      {open && (
        <div className="absolute bottom-16 right-0 flex flex-col gap-2 items-end mb-2">
          <button
            onClick={() => {
              onCreateVacancy();
              setOpen(false);
            }}
            className="flex items-center gap-2 px-4 py-2.5 bg-[var(--hf-green-600)] hover:bg-[var(--hf-green-500)] text-[var(--hf-white)] text-sm font-medium rounded-xl transition-colors whitespace-nowrap"
          >
            <Briefcase className="w-4 h-4" />
            Добавить вакансию
          </button>
          <button
            onClick={() => {
              onAddCandidate();
              setOpen(false);
            }}
            className="flex items-center gap-2 px-4 py-2.5 bg-[var(--hf-cyan-700)] hover:bg-[var(--hf-cyan-600)] text-[var(--hf-white)] text-sm font-medium rounded-xl transition-colors whitespace-nowrap"
          >
            <UserPlus className="w-4 h-4" />
            Добавить кандидата
          </button>
        </div>
      )}

      <button
        onClick={() => setOpen(!open)}
        title="Создать"
        className={clsx(
          "w-14 h-14 rounded-full flex items-center justify-center transition-all shadow-[var(--hf-shadow-lg)]",
          open
            ? "bg-[var(--hf-red-600)] hover:bg-[var(--hf-red-500)] shadow-[0_10px_15px_-3px_var(--hf-status-red-badge)]"
            : "bg-[var(--hf-cyan-600)] hover:bg-[var(--hf-status-blue)] shadow-[0_10px_15px_-3px_var(--hf-status-blue-badge)] animate-pulse-subtle",
        )}
      >
        <Plus
          className={clsx(
            "w-6 h-6 text-[var(--hf-white)] transition-transform",
            open && "rotate-45",
          )}
          strokeWidth={2.5}
        />
      </button>
    </div>
  );
}

function getBlockForPath(path: string): string | null {
  // Отпуска и руководитель отдела — кадровые экраны, живут в блоке HR
  // (в Энцеладусе висели в «Проектах», которых в продукте нет).
  if (path.startsWith("/dept-manager") || path.startsWith("/timeoff")) {
    return "hr";
  }
  if (
    [
      "/factorial",
      "/dashboard",
      "/all-candidates",
      "/statuses",
      "/candidate-archive",
      "/deleted-candidates",
      "/audit-log",
      "/ai-usage",
      "/workspaces",
      "/my-funnels",
      "/form-builder",
      "/document-templates",
      "/email-templates",
      "/employees",
      "/vacancies",
      "/analytics",
      "/hr-reports",
      "/pen",
      "/extension",
      "/exports",
      "/import",
    ].some((p) => path.startsWith(p))
  ) {
    return "hr";
  }
  if (
    ["/users", "/departments", "/settings", "/admin", "/trash"].some((p) =>
      path.startsWith(p),
    )
  ) {
    return "admin";
  }
  return null;
}

export default function Layout() {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const location = useLocation();
  const {
    user,
    logout,
    isImpersonating,
    exitImpersonation,
    fetchPermissions,
    customRoleName,
    hasFeature,
  } = useAuthStore();

  const defaultBlock = useMemo(() => {
    if (user?.org_role === "admin" || user?.org_role === "hr") return "hr";
    return "projects";
  }, [user?.org_role]);
  const [activeBlock, setActiveBlock] = useState<string>(defaultBlock);

  // Sync default block when user role becomes available
  useEffect(() => {
    if (!location.pathname || location.pathname === "/") {
      if (user?.org_role === "admin" || user?.org_role === "hr") {
        setActiveBlock("hr");
      }
    }
  }, [user?.org_role]);
  const navigate = useNavigate();

  // Sidebar: expandable "Мои воронки" with vacancy list
  const { vacancies, fetchVacancies } = useVacancyStore();
  const [expandedFunnels, setExpandedFunnels] = useState(false);
  const [expandedRequests, setExpandedRequests] = useState(true);
  const [sidebarVacancy, setSidebarVacancy] = useState<Vacancy | null>(null);
  const [sidebarVacancyMode, setSidebarVacancyMode] =
    useState<SidebarVacancyMode>("view");
  const routeBlock = getBlockForPath(location.pathname);
  // На /factorial чёрное меню показывает модули брифа (Сотрудники/Документы/Кабинет);
  // вне Факториала всё остаётся прежним.
  const isFactorial = location.pathname.startsWith("/factorial");
  const activeNavigationBlock = routeBlock || activeBlock;
  const isHrSidebar = routeBlock === "hr";
  const [hrSidebarWidth, setHrSidebarWidth] = useState(readStoredHrSidebarWidth);
  const hrSidebarWidthRef = useRef(hrSidebarWidth);
  const [isHrSidebarResizing, setIsHrSidebarResizing] = useState(false);

  // FAB-triggered modals — открываются in-place без навигации
  const [showFabVacancyForm, setShowFabVacancyForm] = useState(false);
  const [showFabParserModal, setShowFabParserModal] = useState(false);
  const [showHrFabActions, setShowHrFabActions] = useState(false);
  const [showHrSettingsModal, setShowHrSettingsModal] = useState(false);
  const [showHrFunnelsPicker, setShowHrFunnelsPicker] = useState(false);
  const [showHrUserMenu, setShowHrUserMenu] = useState(false);
  const hrFabActionsRef = useRef<HTMLDivElement | null>(null);
  const hrFunnelsPickerRef = useRef<HTMLDivElement | null>(null);
  // Фильтр «чьи вакансии показывать» в попапе «Мои вакансии» (2026-07-09):
  // null = свои (текущий юзер), иначе — id выбранного рекрутёра из числа тех,
  // кто лично принял хотя бы одну вакансию (accepted_by). На «Мои вакансии»
  // выбор живёт и в URL (?recruiter=) — оттуда же и восстанавливаем: F5 должен
  // оставлять «Вакансии: Мария», а не сбрасывать на «Мои вакансии» (решение
  // юзера 2026-09-10). recruiter = я — это «Я» (null).
  const urlPickerOwnerId = (() => {
    if (location.pathname !== "/my-funnels") return undefined;
    const raw = Number(new URLSearchParams(location.search).get("recruiter"));
    if (!Number.isFinite(raw) || raw <= 0) return undefined;
    return raw === user?.id ? null : raw;
  })();
  const [pickerOwnerId, setPickerOwnerId] = useState<number | null>(urlPickerOwnerId ?? null);
  useEffect(() => {
    if (urlPickerOwnerId !== undefined) setPickerOwnerId(urlPickerOwnerId);
  }, [urlPickerOwnerId]);
  const [pickerSearch, setPickerSearch] = useState("");
  const [pickerUsersById, setPickerUsersById] = useState<Record<number, string>>({});
  useEffect(() => {
    getAssignableUsers()
      .then((list) => {
        const map: Record<number, string> = {};
        list.forEach((u) => { map[u.id] = u.name; });
        setPickerUsersById(map);
      })
      .catch(() => {});
  }, []);
  // Очищаем поиск при закрытии — иначе при следующем открытии попапа
  // остаётся старый текст фильтра, будто список пуст без видимой причины.
  useEffect(() => {
    if (!showHrFunnelsPicker) setPickerSearch("");
  }, [showHrFunnelsPicker]);

  // На маленьком экране (короткий вьюпорт, много рекрутёров в списке) попап,
  // который всегда открывался вниз от кнопки, мог вылезать за нижний край
  // экрана — списка не докрутить, ничего не видно. Меряем реальное свободное
  // место при каждом открытии/ресайзе: если снизу тесно, а сверху свободнее —
  // открываем вверх; в любом случае ограничиваем высоту тем, что реально
  // есть, и скроллим список опций (см. .hf-hr-funnels-options-scroll).
  const funnelsHeaderRef = useRef<HTMLDivElement | null>(null);
  const [pickerOpensUpward, setPickerOpensUpward] = useState(false);
  const [pickerMaxHeight, setPickerMaxHeight] = useState<number | null>(null);
  useEffect(() => {
    if (!showHrFunnelsPicker) return;
    const GAP = 8;
    const EDGE_MARGIN = 16;
    const compute = () => {
      const header = funnelsHeaderRef.current;
      if (!header) return;
      const rect = header.getBoundingClientRect();
      const spaceBelow = window.innerHeight - rect.bottom - GAP - EDGE_MARGIN;
      const spaceAbove = rect.top - GAP - EDGE_MARGIN;
      const upward = spaceBelow < 220 && spaceAbove > spaceBelow;
      setPickerOpensUpward(upward);
      setPickerMaxHeight(Math.max(160, Math.floor(upward ? spaceAbove : spaceBelow)));
    };
    compute();
    window.addEventListener("resize", compute);
    return () => window.removeEventListener("resize", compute);
  }, [showHrFunnelsPicker]);

  useEffect(() => {
    if (routeBlock === "hr") {
      fetchVacancies();
    }
  }, [routeBlock, fetchVacancies]);

  useLayoutEffect(() => {
    const root = document.documentElement;
    if (isHrSidebar) {
      root.setAttribute("data-theme", "light");
      root.dataset.hrForcedLightTheme = "true";
      return () => {
        if (root.dataset.hrForcedLightTheme === "true") {
          root.setAttribute("data-theme", readStoredAppTheme());
          delete root.dataset.hrForcedLightTheme;
        }
      };
    }

    if (root.dataset.hrForcedLightTheme === "true") {
      root.setAttribute("data-theme", readStoredAppTheme());
      delete root.dataset.hrForcedLightTheme;
    }
  }, [isHrSidebar]);

  useEffect(() => {
    if (!showHrUserMenu) {
      setShowNotifications(false);
    }
  }, [showHrUserMenu]);

  useEffect(() => {
    if (!showHrFabActions) return;
    const handlePointerDown = (event: MouseEvent) => {
      if (
        hrFabActionsRef.current &&
        !hrFabActionsRef.current.contains(event.target as Node)
      ) {
        setShowHrFabActions(false);
      }
    };
    document.addEventListener("mousedown", handlePointerDown);
    return () => document.removeEventListener("mousedown", handlePointerDown);
  }, [showHrFabActions]);

  useEffect(() => {
    if (!showHrFunnelsPicker) return;
    const handlePointerDown = (event: MouseEvent) => {
      if (
        hrFunnelsPickerRef.current &&
        !hrFunnelsPickerRef.current.contains(event.target as Node)
      ) {
        setShowHrFunnelsPicker(false);
      }
    };
    document.addEventListener("mousedown", handlePointerDown);
    return () => document.removeEventListener("mousedown", handlePointerDown);
  }, [showHrFunnelsPicker]);

  useEffect(() => {
    hrSidebarWidthRef.current = hrSidebarWidth;
  }, [hrSidebarWidth]);

  useEffect(() => {
    if (!isHrSidebarResizing) return;
    const handleMouseMove = (event: MouseEvent) => {
      const nextWidth = clampHrSidebarWidth(event.clientX);
      setHrSidebarWidth(nextWidth);
      persistHrSidebarWidth(nextWidth);
    };
    const handleMouseUp = () => {
      persistHrSidebarWidth(hrSidebarWidthRef.current);
      setIsHrSidebarResizing(false);
    };
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
    return () => {
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
  }, [isHrSidebarResizing]);

  useEffect(() => {
    if (!isHrSidebar) return;
    persistHrSidebarWidth(hrSidebarWidth);
  }, [hrSidebarWidth, isHrSidebar]);

  const openVacancyModal = useCallback(
    async (id: number) => {
      const cachedVacancy = vacancies.find((v) => v.id === id);
      if (cachedVacancy) {
        setSidebarVacancy(cachedVacancy);
        setSidebarVacancyMode("view");
      }
      try {
        const v = await getVacancy(id);
        setSidebarVacancy(v);
        setSidebarVacancyMode("view");
      } catch {
        if (!cachedVacancy) {
          toast.error("Не удалось открыть заявку");
        }
      }
    },
    [vacancies],
  );

  // Count of vacancies for the "Заявки" badge.
  // Админ (owner/admin/hr) — нераспределённые заявки 'На рассмотрении'
  //   (+ legacy draft), но НЕ свои собственные (когда админ сам создаёт заявку,
  //   ему не нужен пинг про неё — иначе любое создание сразу "флешит жёлтым").
  // Member — назначенные ему/всем, ещё НЕ принятые ЛИЧНО (2026-07-08:
  //   accepted_by, не «нет клона» — клонов в новой модели не существует).
  const assignedDraftCount = useMemo(() => {
    if (!user) return 0;
    const isAdmin =
      user.role === "superadmin" ||
      user.org_role === "owner" ||
      user.org_role === "admin";
    if (isAdmin) {
      // Все незанятые заявки (pending_review/draft), пока их не взяли в работу —
      // ВКЛЮЧАЯ созданные самим админом (Мария: «создаю на рекрутёра, но не вижу»).
      return vacancies.filter(
        (v) => v.status === "pending_review" || v.status === "draft",
      ).length;
    }
    return vacancies.filter((v) => {
      if (
        v.status !== "pending_review" &&
        v.status !== "draft" &&
        v.status !== "open" &&
        v.status !== "paused"
      ) {
        return false;
      }
      if (v.created_by === user.id) return false;
      const assigned =
        v.assigned_to_all || (v.assigned_to && v.assigned_to.includes(user.id));
      if (!assigned) return false;
      return !isPersonallyActive(v, user.id);
    }).length;
  }, [vacancies, user]);

  // Notifications state
  const unreadCount = useNotificationStore((s) => s.unreadCount);
  const setUnreadCount = useNotificationStore((s) => s.setUnreadCount);
  const [showNotifications, setShowNotifications] = useState(false);
  const [soundMuted, setSoundMuted] = useState<boolean>(isAnketaSoundMuted());
  const [notificationsList, setNotificationsList] = useState<AppNotification[]>(
    [],
  );
  const [notificationsLoading, setNotificationsLoading] = useState(false);
  const notifRef = useRef<HTMLDivElement>(null);

  const fetchUnreadCount = useCallback(async () => {
    try {
      const result = await notificationsApi.getUnreadCount();
      setUnreadCount(result.count);
    } catch {
      // silently ignore
    }
  }, []);

  const fetchNotifications = useCallback(async () => {
    setNotificationsLoading(true);
    try {
      const list = await notificationsApi.getNotifications();
      setNotificationsList(list);
    } catch {
      // silently ignore
    } finally {
      setNotificationsLoading(false);
    }
  }, []);

  const handleToggleNotifications = () => {
    const next = !showNotifications;
    setShowNotifications(next);
    if (next) fetchNotifications();
  };

  const handleMarkRead = async (id: number) => {
    try {
      await notificationsApi.markNotificationRead(id);
      setNotificationsList((prev) =>
        prev.map((n) => (n.id === id ? { ...n, is_read: true } : n)),
      );
      setUnreadCount((prev) => Math.max(0, prev - 1));
    } catch {
      // silently ignore
    }
  };

  const handleMarkAllRead = async () => {
    try {
      await notificationsApi.markAllNotificationsRead();
      setNotificationsList((prev) =>
        prev.map((n) => ({ ...n, is_read: true })),
      );
      setUnreadCount(0);
    } catch {
      // silently ignore
    }
  };

  // Close notifications on outside click. ВАЖНО: блока уведомлений два (меню юзера
  // + футер сайдбара) и они делят один notifRef → ref указывает лишь на один, и
  // клик по «Уведомления» в другом считался «снаружи» и сразу закрывал панель
  // (выглядело как «некликабельно»). Проверяем по data-атрибуту ЛЮБОЙ блок.
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      const t = e.target as HTMLElement | null;
      if (!t?.closest?.("[data-notif-root]")) {
        setShowNotifications(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  // Poll unread count every 30s
  useEffect(() => {
    if (!user) return;
    fetchUnreadCount();
    const interval = setInterval(fetchUnreadCount, 30000);
    return () => clearInterval(interval);
  }, [user?.id, fetchUnreadCount]);

  // Fetch permissions on mount
  useEffect(() => {
    if (user) {
      fetchPermissions();
    }
  }, [user?.id]);

  const handleExitImpersonation = async () => {
    try {
      await exitImpersonation();
    } catch (error) {
      console.error("Failed to exit impersonation:", error);
    }
  };

  // Auto-switch active block based on current URL
  useEffect(() => {
    const nextBlock = getBlockForPath(location.pathname);
    if (nextBlock) setActiveBlock(nextBlock);
  }, [location.pathname]);

  // Navigation sections — 3 blocks: Projects, HR, Analytics + Admin
  type NavSection = {
    id: string;
    label: string;
    items: { path: string; icon: LucideIcon; label: string }[];
  };

  const navSections = useMemo((): NavSection[] => {
    const sections: NavSection[] = [];

    // Роли:
    // - platform admin (superadmin/owner) — видит всё;
    // - HR (org_role=admin/hr) и наблюдатель — блок HR;
    // - обычный сотрудник — в меню ничего, его место — кабинет кадров
    //   (/factorial, см. utils/landing.ts).
    // Блоков «Проекты» и «Практика» в продукте нет (вырезаны при выделении
    // из Энцеладуса, 27.10.2026).
    const isPlatformAdmin =
      user?.role === "superadmin" || user?.org_role === "owner";

    // HR block — superadmin, owner, admin (HR Admin), hr (рекрутер),
    // а также НАБЛЮДАТЕЛЬ (is_readonly) — ментор с read-only доступом к HR.
    // Запись у наблюдателя режется на бэке (403) и баннером.
    // Обычный сотрудник (member без наблюдателя) HR не видит.
    const isObserver = user?.is_readonly === true;
    const isHrRole =
      isPlatformAdmin || user?.org_role === "admin" || user?.org_role === "hr" || isObserver;
    if (isHrRole) {
      const hrItems: { path: string; icon: LucideIcon; label: string }[] = [];
      hrItems.push({
        path: "/all-candidates",
        icon: Users,
        label: "Все кандидаты",
      });
      hrItems.push({ path: "/statuses", icon: UserCheck, label: "Штат" });
      hrItems.push({ path: "/analytics", icon: BarChart3, label: "Аналитика" });
      hrItems.push({
        path: "/my-funnels",
        icon: Briefcase,
        label: "Мои вакансии",
      });
      hrItems.push({ path: "/vacancies", icon: GitBranch, label: "Заявки" });
      sections.push({
        id: "hr",
        label: "HR",
        items: hrItems,
      });
    }

    // ADMIN block — только superadmin/owner, скрыт у HR-only
    if (isPlatformAdmin) {
      const adminItems: { path: string; icon: LucideIcon; label: string }[] = [
        { path: "/departments", icon: Building2, label: "Департаменты" },
        { path: "/settings", icon: Settings, label: "Настройки" },
      ];
      if (user?.role === "superadmin") {
        adminItems.unshift({
          path: "/users",
          icon: UserCog,
          label: "Пользователи",
        });
        adminItems.push({
          path: "/admin/simulator",
          icon: Shield,
          label: "Симулятор ролей",
        });
      }
      sections.push({
        id: "admin",
        label: "Управление",
        items: adminItems,
      });
    }

    return sections;
  }, [user?.role, user?.org_role, hasFeature]);

  // Flat list for mobile bottom nav
  const navItems = useMemo(() => {
    return navSections.flatMap((s) => s.items);
  }, [navSections]);

  const mobileNavItems = useMemo(() => {
    return (
      navSections.find((section) => section.id === activeNavigationBlock)?.items ??
      navItems
    );
  }, [activeNavigationBlock, navItems, navSections]);

  const hrMobileNavItems = useMemo(
    () => [
      { path: "/all-candidates", icon: Users, label: "Все кандидаты" },
      { path: "/statuses", icon: UserCheck, label: "Штат" },
      { path: "/analytics", icon: BarChart3, label: "Аналитика" },
      { path: "/vacancies", icon: GitBranch, label: "Заявки" },
      { path: "/my-funnels", icon: Briefcase, label: "Мои вакансии" },
      { path: "/my-funnels?status=closed", icon: FolderKanban, label: "Закрытые вакансии" },
    ],
    [],
  );

  const activeMobileNavItems = isHrSidebar ? hrMobileNavItems : mobileNavItems;

  const handleBlockSwitch = useCallback(
    (section: NavSection) => {
      setActiveBlock(section.id);
      const targetPath = section.items[0]?.path;
      if (targetPath && location.pathname !== targetPath) {
        navigate(targetPath);
      }
    },
    [location.pathname, navigate],
  );

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  const handleHrSettingsNavigate = (path: string) => {
    setShowHrSettingsModal(false);
    navigate(path);
  };

  // Полный админ сайдбара: owner/admin/superadmin. hr (HR Рекрутер) СЮДА НЕ
  // входит — он ограниченный рекрутёр (видит только свои/назначенные заявки,
  // «Отказаться», без удаления и без /users). Откат hr=админ, 2026-07-07.
  // Наблюдатель (is_readonly): HR смотрит, но ничего не создаёт — кнопки
  // добавления в сайдбаре ему не показываем (01.10.2026).
  const isObserverUser = user?.is_readonly === true;
  const isHrSidebarAdmin =
    user?.role === "superadmin" ||
    user?.org_role === "owner" ||
    user?.org_role === "admin";
  // Factorial «Сотрудники»/«Документы» — админ (owner/admin) + hr-рекрутёр.
  // Обычный сотрудник (member) видит лишь «Отпуска» и «Личный кабинет».
  const canManageFactorialPeople = isHrSidebarAdmin || user?.org_role === "hr";
  const sidebarSearchParams = new URLSearchParams(location.search);
  const sidebarSelectedVacancyId = sidebarSearchParams.get("v");
  const isClosedFunnelsView =
    location.pathname === "/my-funnels" &&
    sidebarSearchParams.get("status") === "closed";
  const isMyFunnelsRootView =
    location.pathname === "/my-funnels" &&
    !sidebarSelectedVacancyId &&
    !isClosedFunnelsView;
  // Все исходные заявки, у которых уже есть клон («взяли в работу»).
  // Оригинал после взятия переходит в status=open и без этого фильтра
  // дублировал клон в «Мои вакансии» (видно как два одинаковых «Тест»).
  const allClonedSourceIds = new Set<number>();
  vacancies.forEach((v) => {
    const src = (v.extra_data as Record<string, unknown> | undefined)
      ?.cloned_from_request_id;
    if (typeof src === "number") allClonedSourceIds.add(src);
  });
  // Кого показывать в «Мои вакансии» — себя (по умолчанию) или того, кого
  // выбрали в попапе «Выбрать владельца вакансий» (2026-07-09, фильтр по
  // принявшим). null в pickerOwnerId = «я».
  const funnelsPickerOwnerId = pickerOwnerId ?? user?.id ?? null;
  const sidebarOpenVacancies = vacancies
    .filter((v) => v.status === "open")
    .filter((v) => !allClonedSourceIds.has(v.id))
    // «Мои вакансии» = где выбранный владелец реально участник (создатель ИЛИ
    // назначенный, минус «закрыл у себя») — ДАЖЕ для admin/superadmin. Раньше
    // админ видел тут вообще ВСЕ открытые вакансии орга, из-за чего любое
    // «взятие в работу» рекрутёром выглядело так, будто заявку взял и сам
    // админ тоже. Просмотр «всего» без участия остаётся доступен на полной
    // странице «Мои вакансии» — там у admin/owner/superadmin свой полный список.
    // 2026-07-08: назначенный, но ещё лично НЕ принявший (isVacancyParticipant
    // без accepted_by) не должен видеть её тут как «свою» — только после
    // личного «Взять в работу» (isPersonallyActive). До этого она в «Заявки».
    .filter((v) => isPersonallyActive(v, funnelsPickerOwnerId));
  // Список рекрутёров для попапа — все, кто лично принял хотя бы одну
  // вакансию (accepted_by), кроме текущего юзера (он уже пришпилен как «Я»
  // отдельным пунктом). Считаем и сколько вакансий у каждого — видно сразу
  // в списке, без перехода на полную страницу «Мои вакансии».
  const funnelsPickerRecruiters = useMemo(() => {
    const counts = new Map<number, number>();
    // Запоминаем id последней встреченной вакансии — нужен, когда у
    // рекрутёра ровно ОДНА (см. onlyVacancyId ниже: прямой переход в её
    // воронку без промежуточного списка).
    const lastVacancyId = new Map<number, number>();
    vacancies.forEach((v) => {
      if (v.status !== "open") return;
      // Оригинал заявки, у которой уже есть личный клон рекрутёра, — не
      // отдельная воронка, а дубликат (см. allClonedSourceIds/sidebarOpenVacancies
      // выше). Без этого фильтра счётчик в попапе расходился с реальным
      // списком «Мои вакансии» — легаси-клоны считались дважды.
      if (allClonedSourceIds.has(v.id)) return;
      // СТРОГО accepted_by, БЕЗ фолбэка на created_by (в отличие от
      // getAcceptorIds) — список ниже (sidebarOpenVacancies) фильтрует через
      // isPersonallyActive, у которой фолбэка тоже нет. На старых вакансиях
      // (созданы до обязательного личного «Взять в работу», accepted_by
      // пустой) getAcceptorIds засчитывала их создателю — счётчик в попапе
      // («N вакансий») расходился с реальным списком под кнопкой (например,
      // «5» в счётчике при 1 вакансии в списке).
      const acceptedBy = ((v.extra_data as Record<string, unknown> | undefined)?.accepted_by as number[] | undefined) || [];
      acceptedBy.forEach((uid) => {
        if (user && uid === user.id) return;
        counts.set(uid, (counts.get(uid) || 0) + 1);
        lastVacancyId.set(uid, v.id);
      });
    });
    return Array.from(counts.entries())
      .map(([id, count]) => ({
        id,
        count,
        // Имени нет в списке назначаемых (например, у суперадмина) — берём его
        // из вакансии, которую он создал, как делают воронки
        // (resolveGroupUserName). Раньше в меню стояло «#1 · 4 вакансий».
        name:
          pickerUsersById[id] ||
          vacancies.find((v) => v.created_by === id && v.created_by_name)?.created_by_name ||
          `#${id}`,
        onlyVacancyId: count === 1 ? lastVacancyId.get(id) ?? null : null,
      }))
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [vacancies, user, pickerUsersById, allClonedSourceIds]);
  const filteredFunnelsPickerRecruiters = pickerSearch.trim()
    ? funnelsPickerRecruiters.filter((r) =>
        r.name.toLowerCase().includes(pickerSearch.trim().toLowerCase()),
      )
    : funnelsPickerRecruiters;
  // Заявки, которые ТЕКУЩИЙ юзер уже взял в работу (есть свой клон).
  // После «Взять в работу» исходная заявка должна пропасть из списка —
  // она уже взята. Раньше она оставалась висеть.
  const myTakenRequestIds = new Set<number>();
  if (user) {
    vacancies.forEach((v) => {
      if (v.created_by !== user.id) return;
      const src = (v.extra_data as Record<string, unknown> | undefined)
        ?.cloned_from_request_id;
      if (typeof src === "number") myTakenRequestIds.add(src);
    });
  }
  const allSidebarRequests = vacancies
    // «Заявки» = заявочные статусы (pending_review/draft) ПЛЮС open/paused, где
    // ТЕКУЩИЙ юзер назначен, но ещё лично не принял (кто-то другой уже взял —
    // воронка общая, но принятие личное, 2026-07-08). isRequestVisibleTo ниже
    // отфильтрует «свои» (уже лично принятые) через isPersonallyActive.
    .filter(
      (v) =>
        v.status === "pending_review" ||
        v.status === "draft" ||
        v.status === "open" ||
        v.status === "paused",
    )
    .filter((v) => {
      // Клон (вакансия, взятая рекрутёром в работу) — это НЕ заявка,
      // а рабочая копия в «Мои вакансии».
      const clonedFrom = (v.extra_data as Record<string, unknown> | undefined)
        ?.cloned_from_request_id;
      if (typeof clonedFrom === "number") return false;
      // Заявку, которую текущий юзер уже взял в работу, прячем.
      if (myTakenRequestIds.has(v.id)) return false;
      // Единое правило видимости заявки (utils/vacancy.ts): admin/owner/
      // superadmin видят ВСЕ, рекрутёр — свои созданные И назначенные на него.
      return isRequestVisibleTo(v, user?.id, isHrSidebarAdmin);
    });
  // Бейдж рядом с «Заявки» = ВСЕГО заявок (совпадает со списком), не только
  // нераспределённых. Список визуально ограничен 8, счётчик — полный.
  const sidebarRequestCount = allSidebarRequests.length;
  const sidebarRequestVacancies = allSidebarRequests.slice(0, 8);
  const getSidebarRequestAuthor = (vacancy: Vacancy) =>
    vacancy.created_by_name ||
    vacancy.hiring_manager_name ||
    "Автор не указан";

  return (
    <div
      className={clsx(
        isHrSidebar
          ? "hf-hr-layout-shell hf-hr-layout-shell--hr"
          : "app-layout-shell",
      )}
    >
      <BackgroundEffects />
      <AnimatePresence>
        {showHrSettingsModal && (
          <HrSettingsModal
            canUseAdmin={isHrSidebarAdmin}
            isSuperadmin={user?.role === "superadmin"}
            onClose={() => setShowHrSettingsModal(false)}
            onNavigate={handleHrSettingsNavigate}
          />
        )}
      </AnimatePresence>
      {/* Desktop Sidebar */}
      <aside
        style={isHrSidebar ? { width: hrSidebarWidth } : undefined}
        className={clsx(
          "hidden lg:flex h-screen min-h-0 flex-col",
          isHrSidebar
            ? "hf-hr-sidebar"
            : "w-64 app-sidebar-default glass border-r border-[color:var(--hf-workspace-divider)]",
        )}
        role="navigation"
        aria-label="Main navigation"
      >
        {isHrSidebar ? (
          <>
            <div
              className="hf-hr-sidebar-card"
            >
              <div className="hf-hr-block-tabs">
                {navSections.map((section) => {
                  const Icon = BLOCK_ICONS[section.id] || LayoutDashboard;
                  const isActive = activeNavigationBlock === section.id;
                  return (
                    <button
                      key={section.id}
                      type="button"
                      onClick={() => handleBlockSwitch(section)}
                      className={clsx(
                        "hf-hr-block-tab",
                        isActive && "hf-hr-block-tab-active",
                      )}
                      title={section.label}
                    >
                      <Icon className="hf-hr-block-icon" />
                      <span className="max-w-full truncate">
                        {section.label}
                      </span>
                    </button>
                  );
                })}
              </div>

              {isFactorial && (
                <nav className="hf-hr-nav" aria-label="Factorial navigation">
                  <div className="hf-hr-nav-list">
                    {canManageFactorialPeople && (
                      <>
                        <NavLink
                          to="/factorial/employees"
                          className={({ isActive }) =>
                            clsx("hf-hr-nav-item", isActive && "hf-hr-nav-item-active")
                          }
                        >
                          <HfSpriteIcon id="home-20" className="hf-hr-nav-icon" />
                          Сотрудники
                        </NavLink>
                        <NavLink
                          to="/factorial/files"
                          className={({ isActive }) =>
                            clsx("hf-hr-nav-item", isActive && "hf-hr-nav-item-active")
                          }
                        >
                          <HfSpriteIcon id="business-folder" className="hf-hr-nav-icon" />
                          Документы
                        </NavLink>
                      </>
                    )}
                    <NavLink
                      to="/factorial/time-off"
                      className={({ isActive }) =>
                        clsx("hf-hr-nav-item", isActive && "hf-hr-nav-item-active")
                      }
                    >
                      <Calendar className="hf-hr-nav-icon" strokeWidth={1.8} />
                      Отпуска
                    </NavLink>
                    <NavLink
                      to="/factorial/profile"
                      className={() =>
                        clsx(
                          "hf-hr-nav-item",
                          /\/factorial\/(profile|my-documents)/.test(
                            location.pathname,
                          ) && "hf-hr-nav-item-active",
                        )
                      }
                    >
                      <HfSpriteIcon id="edit-2-20" className="hf-hr-nav-icon" />
                      Личный кабинет
                    </NavLink>
                    <NavLink
                      to="/factorial/my-team"
                      className={({ isActive }) =>
                        clsx("hf-hr-nav-item", isActive && "hf-hr-nav-item-active")
                      }
                    >
                      <Users className="hf-hr-nav-icon" strokeWidth={1.8} />
                      Моя команда
                    </NavLink>
                  </div>
                </nav>
              )}
              {!isFactorial && (
              <nav
                className={clsx(
                  "hf-hr-nav",
                  showHrFunnelsPicker && "hf-hr-nav-popover-open",
                )}
                aria-label="Primary navigation"
              >
                <div className="hf-hr-nav-list">
                  <NavLink
                    to="/all-candidates"
                    // Метка «это переход из меню»: страница по ней сбрасывает
                    // свой поиск и возвращается на вкладку «Все». Повторный клик
                    // по пункту должен срабатывать, а не упираться в забытое
                    // слово в строке поиска (Эльвира, 02.10.2026).
                    state={{ resetSearch: true }}
                    data-tour={pathToTourAttribute["/all-candidates"]}
                    className={({ isActive }) =>
                      clsx(
                        "hf-hr-nav-item",
                        isActive && "hf-hr-nav-item-active",
                      )
                    }
                  >
                    <HfSpriteIcon id="home-20" className="hf-hr-nav-icon" />
                    Все кандидаты
                  </NavLink>
                  <NavLink
                    to="/statuses"
                    className={({ isActive }) =>
                      clsx(
                        "hf-hr-nav-item",
                        isActive && "hf-hr-nav-item-active",
                      )
                    }
                  >
                    <HfSpriteIcon id="calendar-20" className="hf-hr-nav-icon" />
                    Штат
                  </NavLink>
                  <NavLink
                    to="/analytics"
                    data-tour={pathToTourAttribute["/analytics"]}
                    className={({ isActive }) =>
                      clsx(
                        "hf-hr-nav-item",
                        isActive && "hf-hr-nav-item-active",
                      )
                    }
                  >
                    <HfSpriteIcon
                      id="graph-20"
                      className="hf-hr-nav-icon"
                    />
                    Аналитика
                  </NavLink>
                  {/* Standalone-вход к шаблонам анкет: раньше добраться до них
                      можно было только из карточки кандидата (дровер «Анкета»). */}
                  <NavLink
                    to="/form-builder"
                    className={({ isActive }) =>
                      clsx(
                        "hf-hr-nav-item",
                        isActive && "hf-hr-nav-item-active",
                      )
                    }
                  >
                    <ClipboardList className="hf-hr-nav-icon" strokeWidth={1.8} />
                    Анкеты
                  </NavLink>
                </div>

                <div className="hf-hr-sidebar-divider hf-hr-sidebar-divider-requests" />

                <div>
                  <button
                    type="button"
                    onClick={() => setExpandedRequests(!expandedRequests)}
                    className="hf-hr-nav-item hf-hr-nav-item-white w-full"
                    aria-expanded={expandedRequests}
                  >
                    <HfSpriteIcon
                      id="edit-2-20"
                      className="hf-hr-nav-icon"
                    />
                    <span className="min-w-0 flex-1">Заявки</span>
                    {/* Счётчик рядом с «Заявки» = ВСЕГО заявок (как в списке),
                        а не только нераспределённых. */}
                    {isHrSidebarAdmin && sidebarRequestCount > 0 && (
                      <span className="mr-2 inline-flex h-[18px] min-w-[18px] items-center justify-center rounded-full bg-[var(--hf-status-red)] px-1.5 text-[11px] font-semibold leading-none text-white">
                        {sidebarRequestCount}
                      </span>
                    )}
                    <span className="hf-hr-secondary-text">
                      {expandedRequests ? "Свернуть" : "Развернуть"}
                    </span>
                  </button>
                  {expandedRequests && (
                    <div className="hf-hr-request-list">
                      {sidebarRequestVacancies.map((v) => (
                        <button
                          key={v.id}
                          type="button"
                          onClick={() => openVacancyModal(v.id)}
                          className="group hf-hr-request-item"
                        >
                          <span
                            className={clsx(
                              "hf-hr-request-dot",
                              v.status === "paused"
                                ? "bg-[var(--hf-sidebar-status-paused)]"
                                : "bg-[var(--hf-sidebar-status-active)]",
                            )}
                          />
                          <span className="min-w-0">
                            <span className="hf-hr-request-title">
                              {v.title}
                            </span>
                            <span className="hf-hr-request-meta">
                              {getSidebarRequestAuthor(v)}
                            </span>
                          </span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>

                <div className="hf-hr-sidebar-divider hf-hr-sidebar-divider-funnels" />

                <div ref={hrFunnelsPickerRef}>
                  {/* position:relative-якорь для попапа должен оборачивать ТОЛЬКО
                      кнопку-триггер, а не весь блок вместе со списком вакансий
                      ниже — иначе top: calc(100% + gap) в .hf-hr-funnels-picker
                      считается от высоты ВСЕГО блока (заголовок + сколько бы ни
                      было вакансий в hf-hr-subnav), и попап съезжает вниз тем
                      сильнее, чем больше у юзера принятых вакансий — вплоть до
                      наложения на сам список вместо появления сразу под кнопкой. */}
                  <div className="hf-hr-funnels-picker-wrap" ref={funnelsHeaderRef}>
                    <div className="hf-hr-funnels-header">
                      <button
                        type="button"
                        className={clsx(
                          "hf-hr-nav-item hf-hr-funnels-trigger min-w-0",
                          isMyFunnelsRootView
                            ? "hf-hr-nav-item-active"
                            : "hf-hr-nav-item-white",
                        )}
                        onClick={() => setShowHrFunnelsPicker((value) => !value)}
                        aria-label="Выбрать владельца вакансий"
                        aria-expanded={showHrFunnelsPicker}
                        aria-haspopup="listbox"
                      >
                        <HfSpriteIcon
                          id="business-folder"
                          className="hf-hr-nav-icon"
                        />
                        <span className="truncate">
                          {pickerOwnerId === null
                            ? "Мои вакансии"
                            : `Вакансии: ${funnelsPickerRecruiters.find((r) => r.id === pickerOwnerId)?.name || pickerUsersById[pickerOwnerId] || "..."}`}
                        </span>
                        <span className="hf-hr-funnels-trigger-caret">
                          <ChevronDown
                            className={clsx(
                              "hf-hr-chevron-icon",
                              showHrFunnelsPicker && "rotate-180",
                            )}
                          />
                        </span>
                      </button>
                    </div>
                    <AnimatePresence>
                      {showHrFunnelsPicker && (
                        <motion.div
                          initial={{ opacity: 0, y: pickerOpensUpward ? 4 : -4, scale: 0.985 }}
                          animate={{ opacity: 1, y: 0, scale: 1 }}
                          exit={{ opacity: 0, y: pickerOpensUpward ? 4 : -4, scale: 0.985 }}
                          transition={{ duration: 0.12, ease: "easeOut" }}
                          className={clsx(
                            "hf-hr-funnels-picker",
                            pickerOpensUpward && "hf-hr-funnels-picker-up",
                          )}
                          style={pickerMaxHeight ? { maxHeight: pickerMaxHeight } : undefined}
                          role="listbox"
                        >
                          <label className="hf-hr-funnels-search">
                            <Search className="hf-hr-funnels-search-icon" />
                            <input
                              className="hf-hr-funnels-search-input"
                              placeholder="Поиск..."
                              value={pickerSearch}
                              onChange={(e) => setPickerSearch(e.target.value)}
                            />
                          </label>
                          {/* Скролл только тут — поиск остаётся на виду, пока
                              длинный список рекрутёров прокручивается внутри
                              ограниченной по высоте (см. pickerMaxHeight) области.
                              Без этого на невысоком экране низ списка был
                              недоступен — не хватало места, и не было скролла. */}
                          <div className="hf-hr-funnels-options-scroll">
                            <button
                              type="button"
                              className="hf-hr-funnels-option"
                              onClick={() => {
                                setPickerOwnerId(null);
                                setShowHrFunnelsPicker(false);
                                navigate("/my-funnels");
                              }}
                              role="option"
                              aria-selected={pickerOwnerId === null}
                            >
                              {pickerOwnerId === null && <Check className="hf-hr-funnels-check" />}
                              <span className="hf-hr-funnels-avatar">
                                {user?.name?.[0]?.toUpperCase() || "Я"}
                              </span>
                              <span className="hf-hr-funnels-option-text">
                                <span className="hf-hr-funnels-option-title">
                                  Я, {user?.name || user?.email || "Профиль"}
                                </span>
                                <span className="hf-hr-funnels-option-subtitle">
                                  {user?.email || "—"}
                                  {user?.is_readonly && (
                                    <span
                                      style={{
                                        marginLeft: 6, padding: "1px 6px", borderRadius: 6,
                                        fontSize: 10, fontWeight: 600,
                                        background: "#fde68a", color: "#92400e",
                                      }}
                                    >
                                      только чтение
                                    </span>
                                  )}
                                </span>
                              </span>
                            </button>
                            {/* Рекрутёры, которые лично приняли хотя бы одну вакансию
                                (accepted_by) — выбор фильтрует список ниже под них,
                                можно пройтись по их воронкам прямо из сайдбара. */}
                            {filteredFunnelsPickerRecruiters.map((r) => (
                              <button
                                key={r.id}
                                type="button"
                                className="hf-hr-funnels-option"
                                onClick={() => {
                                  setPickerOwnerId(r.id);
                                  setShowHrFunnelsPicker(false);
                                  // 2026-07-09: ровно одна вакансия — сразу открываем
                                  // её воронку (без промежуточного списка, однозначно
                                  // понятно, что показывать), с любой страницы.
                                  // Несколько вакансий — НЕ уводим с текущей страницы
                                  // (главная/заявки/что угодно остаётся как есть);
                                  // если уже на «Мои вакансии» — просто фильтруем её
                                  // под этого рекрутёра (см. ?recruiter= в
                                  // RecruiterFunnelsPage), иначе трогаем только
                                  // мини-список под кнопкой в сайдбаре.
                                  if (r.onlyVacancyId) {
                                    // recruiter=<id> скоупит кандидатов воронки на
                                    // этого рекрутёра (см. RecruiterFunnelsPage).
                                    navigate(`/my-funnels?v=${r.onlyVacancyId}&recruiter=${r.id}`);
                                  } else if (location.pathname === "/my-funnels") {
                                    navigate(`/my-funnels?recruiter=${r.id}`);
                                  }
                                }}
                                role="option"
                                aria-selected={pickerOwnerId === r.id}
                              >
                                {pickerOwnerId === r.id && <Check className="hf-hr-funnels-check" />}
                                <span className="hf-hr-funnels-avatar">
                                  {r.name[0]?.toUpperCase() || "?"}
                                </span>
                                <span className="hf-hr-funnels-option-text">
                                  <span className="hf-hr-funnels-option-title">
                                    {r.name}
                                  </span>
                                  <span className="hf-hr-funnels-option-subtitle">
                                    {r.count} {pluralRu(r.count, "вакансия", "вакансии", "вакансий")}
                                  </span>
                                </span>
                              </button>
                            ))}
                          </div>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </div>
                  {/* Список скрываем, пока открыт попап выбора владельца —
                      иначе при длинном списке (много принятых вакансий)
                      вакансии внизу выглядывают из-под попапа, который
                      рассчитан на компактную высоту (поиск + один пункт). */}
                  {!showHrFunnelsPicker && sidebarOpenVacancies.length > 0 && (
                    <div className="hf-hr-subnav">
                      {sidebarOpenVacancies.map((v) => (
                        <NavLink
                          key={v.id}
                          to={(() => {
                            // Воронка из сайдбара всегда со скоупом: выбранный
                            // владелец, а у «Я» — свой id (своя воронка отсюда =
                            // только свои кандидаты, решение юзера 2026-09-10).
                            const rec = pickerOwnerId ?? user?.id ?? null;
                            return rec != null
                              ? `/my-funnels?v=${v.id}&recruiter=${rec}`
                              : `/my-funnels?v=${v.id}`;
                          })()}
                          className={() =>
                            clsx(
                              "hf-hr-subnav-link",
                              sidebarSelectedVacancyId === String(v.id) &&
                                "hf-hr-subnav-link-active",
                            )
                          }
                        >
                          <span className="hf-hr-request-title">
                            {v.title}
                          </span>
                          <span className="hf-hr-request-meta">
                            {typeof (
                              v.extra_data as
                                | Record<string, unknown>
                                | undefined
                            )?.department === "string"
                              ? ((v.extra_data as Record<string, unknown>)
                                  .department as string)
                              : "IT"}
                          </span>
                        </NavLink>
                      ))}
                    </div>
                  )}
                </div>

                <div className="hf-hr-sidebar-divider hf-hr-sidebar-divider-closed" />

                <NavLink
                  to="/my-funnels?status=closed"
                  className={clsx(
                    "hf-hr-nav-item",
                    isClosedFunnelsView
                      ? "hf-hr-nav-item-active"
                      : "hf-hr-nav-item-white",
                  )}
                >
                  <HfSpriteIcon
                    id="archive-2-20"
                    className="hf-hr-nav-icon"
                  />
                  <span className="min-w-0 flex-1">Закрытые вакансии</span>
                </NavLink>
              </nav>
              )}

              {!isFactorial && (
              <div
                ref={hrFabActionsRef}
                className="hf-hr-fab-wrap"
              >
                {!isObserverUser && (
                <AnimatePresence>
                  {showHrFabActions && (
                    <motion.div
                      initial={{ opacity: 0, y: 6, scale: 0.98 }}
                      animate={{ opacity: 1, y: 0, scale: 1 }}
                      exit={{ opacity: 0, y: 6, scale: 0.98 }}
                      transition={{ duration: 0.12, ease: "easeOut" }}
                      className="hf-hr-fab-menu"
                    >
                      {[
                        // «Создать заявку» — все админы (owner/admin/hr) и
                        // суперадмин. Открывает модалку-форму прямо на месте.
                        ...(isHrSidebarAdmin
                          ? [{
                              label: "Создать заявку",
                              action: () => setShowFabVacancyForm(true),
                            }]
                          : []),
                        {
                          label: "Добавить кандидата",
                          action: () => navigate("/all-candidates?add=resume"),
                        },
                        {
                          label: "Перейти к заявкам",
                          action: () => navigate("/vacancies"),
                        },
                      ].map((item) => (
                        <button
                          key={item.label}
                          type="button"
                          onClick={() => {
                            item.action();
                            setShowHrFabActions(false);
                          }}
                          className="hf-hr-fab-menu-item"
                        >
                          {item.label}
                        </button>
                      ))}
                    </motion.div>
                  )}
                </AnimatePresence>
                )}
                {!isObserverUser && (
                <button
                  type="button"
                  onClick={() => setShowHrFabActions((open) => !open)}
                  className="hf-hr-fab"
                  aria-label="Открыть меню добавления"
                >
                  <Plus className="hf-hr-fab-icon" />
                </button>
                )}
                {/* Кнопка уведомлений + peek входящих рядом с «+» */}
                <NotifPeek />
              </div>
              )}

              <div className="hf-hr-sidebar-bottom">
                <div className="hf-hr-user-row hf-hr-bottom-row">
                  <button
                    type="button"
                    onClick={() => setShowHrUserMenu((open) => !open)}
                    className="hf-hr-user-toggle"
                    aria-expanded={showHrUserMenu}
                    aria-label={
                      showHrUserMenu
                        ? "Свернуть меню пользователя"
                        : "Развернуть меню пользователя"
                    }
                  >
                    <span className="hf-hr-user-avatar">
                      {user?.name?.[0]?.toUpperCase() || "U"}
                    </span>
                    <span className="min-w-0 flex-1 text-left">
                      <span className="hf-hr-user-name">
                        {user?.name}
                      </span>
                      <span className="hf-hr-user-email">
                        {user?.email}
                      </span>
                    </span>
                    <ChevronDown
                      className={clsx(
                        "hf-hr-user-chevron",
                        showHrUserMenu && "hf-hr-user-chevron-open",
                      )}
                      strokeWidth={1.8}
                    />
                  </button>
                  <button
                    type="button"
                    onClick={() => setShowHrSettingsModal(true)}
                    aria-label="Открыть настройки HR"
                    title="Настройки"
                    className="hf-hr-settings-btn"
                  >
                    <Settings className="hf-hr-settings-icon" strokeWidth={1.8} />
                  </button>
                </div>

                <AnimatePresence initial={false}>
                  {showHrUserMenu && (
                    <motion.div
                      key="hr-user-menu"
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: "auto", opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.16, ease: [0.22, 1, 0.36, 1] }}
                      className="hf-hr-user-menu"
                      // overflow:hidden (CSS) нужен для анимации высоты, но он же
                      // обрезал absolute-поповер уведомлений (bottom-full → вверх
                      // за пределы меню) → панель открывалась, но была невидима.
                      // Меню к моменту открытия уведомлений уже развёрнуто, поэтому
                      // на это время отдаём overflow:visible.
                      style={{ overflow: showNotifications ? "visible" : undefined }}
                    >
                      <div className="relative hf-hr-bottom-row" ref={notifRef} data-notif-root>
                        <button
                          type="button"
                          onClick={handleToggleNotifications}
                          className="hf-hr-nav-item w-full text-[color:var(--hf-white-alpha-72)]"
                        >
                          <Bell className="h-[var(--hf-avatar-3xs)] w-[var(--hf-avatar-3xs)]" strokeWidth={1.8} />
                          <span className="min-w-0 flex-1 truncate text-left">
                            Уведомления
                          </span>
                          {unreadCount > 0 && (
                            <span className="flex min-w-[18px] items-center justify-center rounded-full bg-[var(--hf-red-500)] px-[5px] text-[length:var(--hf-fs-5xs)] font-bold leading-[16px] text-[var(--hf-white)]">
                              {unreadCount > 99 ? "99+" : unreadCount}
                            </span>
                          )}
                        </button>

                        {showNotifications && (
                          <div className="hf-hr-notifications-popover absolute bottom-full left-0 z-[120] mb-2 w-80 max-h-96 overflow-hidden rounded-xl shadow-[var(--hf-shadow-2xl)]">
                            <div className="hf-hr-notifications-header flex items-center justify-between px-4 py-3">
                              <span className="hf-hr-notifications-title text-sm font-medium">
                                Уведомления
                              </span>
                              <div className="flex items-center gap-3">
                                <NotifSettings
                                  onChanged={() => {
                                    fetchNotifications();
                                    fetchUnreadCount();
                                  }}
                                />
                                <button
                                  type="button"
                                  onClick={() => {
                                    const next = !soundMuted;
                                    setAnketaSoundMuted(next);
                                    setSoundMuted(next);
                                  }}
                                  title={soundMuted ? "Включить звук новых анкет" : "Выключить звук новых анкет"}
                                  aria-label={soundMuted ? "Включить звук" : "Выключить звук"}
                                  className="flex items-center text-[var(--hf-dark-300)] transition-colors hover:text-[var(--hf-dark-100)]"
                                >
                                  {soundMuted ? <VolumeX className="h-4 w-4" /> : <Volume2 className="h-4 w-4" />}
                                </button>
                                {unreadCount > 0 && (
                                  <button
                                    type="button"
                                    onClick={handleMarkAllRead}
                                    className="flex items-center gap-1 text-xs text-[var(--hf-status-blue)] transition-colors hover:text-[var(--hf-cyan-400)]"
                                  >
                                    <Check className="h-3 w-3" />
                                    Прочитать все
                                  </button>
                                )}
                              </div>
                            </div>
                            <div className="max-h-80 overflow-y-auto">
                              {notificationsLoading ? (
                                <div className="flex items-center justify-center py-8">
                                  <div className="hf-loading-spinner h-5 w-5 border-2" />
                                </div>
                              ) : notificationsList.length === 0 ? (
                                <div className="hf-hr-notifications-empty py-8 text-center text-xs">
                                  Нет уведомлений
                                </div>
                              ) : (
                                notificationsList.map((notif) => (
                                  <button
                                    key={notif.id}
                                    type="button"
                                    onClick={() => {
                                      if (!notif.is_read) handleMarkRead(notif.id);
                                      if (notif.link) {
                                        navigate(notif.link);
                                        setShowNotifications(false);
                                      }
                                    }}
                                    className={clsx(
                                      "hf-hr-notifications-item w-full px-4 py-3 text-left transition-colors",
                                      !notif.is_read && "hf-hr-notifications-item-unread",
                                    )}
                                  >
                                    <div className="flex items-start gap-2">
                                      {!notif.is_read && (
                                        <span className="mt-1.5 h-2 w-2 flex-shrink-0 rounded-full bg-[var(--hf-status-blue)]" />
                                      )}
                                      <div
                                        className={clsx(
                                          "min-w-0 flex-1",
                                          notif.is_read && "ml-4",
                                        )}
                                      >
                                        <p className="hf-hr-notifications-item-title truncate text-xs font-medium">
                                          {notif.title}
                                        </p>
                                        {notif.message && (
                                          <p className="hf-hr-notifications-item-message mt-0.5 truncate text-[length:var(--hf-fs-4xs)]">
                                            {notif.message}
                                          </p>
                                        )}
                                        <p className="hf-hr-notifications-item-time mt-1 text-[length:var(--hf-fs-5xs)]">
                                          {new Date(notif.created_at).toLocaleString(
                                            "ru-RU",
                                            {
                                              day: "numeric",
                                              month: "short",
                                              hour: "2-digit",
                                              minute: "2-digit",
                                            },
                                          )}
                                        </p>
                                      </div>
                                    </div>
                                  </button>
                                ))
                              )}
                            </div>
                          </div>
                        )}
                      </div>

                      {!isHrSidebar && <ThemeToggle />}

                      <NavLink
                        to="/my-profile"
                        className={({ isActive }) =>
                          clsx(
                            "hf-hr-nav-item w-full",
                            isActive
                              ? "hf-hr-nav-item-active"
                              : "text-[color:var(--hf-white-alpha-72)]",
                          )
                        }
                      >
                        <User className="h-[var(--hf-avatar-3xs)] w-[var(--hf-avatar-3xs)]" strokeWidth={1.8} />
                        <span className="min-w-0 flex-1 truncate text-left">
                          Мой профиль
                        </span>
                      </NavLink>

                      <button
                        type="button"
                        onClick={handleLogout}
                        className="hf-hr-nav-item w-full text-[color:var(--hf-white-alpha-72)] hover:bg-[var(--hf-status-red-bg)] hover:text-[var(--hf-red-300)]"
                        aria-label="Выйти из аккаунта"
                      >
                        <LogOut className="h-[var(--hf-avatar-3xs)] w-[var(--hf-avatar-3xs)]" strokeWidth={1.8} />
                        <span className="min-w-0 flex-1 truncate text-left">
                          Выход
                        </span>
                      </button>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            </div>
            <button
              type="button"
              aria-label="Изменить ширину HR-сайдбара"
              onMouseDown={(event) => {
                event.preventDefault();
                setIsHrSidebarResizing(true);
              }}
              className={clsx(
                "hf-hr-resizer",
                isHrSidebarResizing && "hf-hr-resizer-active",
              )}
            >
              <span className="hf-hr-resizer-line" />
              <span className="hf-hr-resizer-handle" />
            </button>
          </>
        ) : (
          <>
            {/* Block switcher — top row of icons */}
            <div className="p-3 border-b border-[color:var(--hf-workspace-divider)]">
              <div className="flex items-center gap-1">
                {navSections.map((section) => {
                  const Icon = BLOCK_ICONS[section.id] || LayoutDashboard;
                  const isActive = activeNavigationBlock === section.id;
                  return (
                    <button
                      key={section.id}
                      onClick={() => handleBlockSwitch(section)}
                      className={clsx(
                        "flex-1 flex flex-col items-center gap-1 py-2 px-1 rounded-xl transition-all duration-200",
                        isActive
                          ? clsx("border", BLOCK_ACTIVE_BG[section.id])
                          : "text-[var(--hf-dark-400)] hover:text-[var(--hf-dark-100)] hover:bg-[var(--hf-alpha-100)] border border-transparent",
                      )}
                      title={section.label}
                    >
                      <Icon className="w-4 h-4" />
                      <span className="text-[length:var(--hf-fs-6xs)] font-semibold uppercase tracking-wider">
                        {section.label}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Active block navigation */}
            <nav
              className="flex-1 min-h-0 px-3 py-3 overflow-y-auto"
              aria-label="Primary navigation"
            >
              {navSections
                .filter((s) => s.id === activeNavigationBlock)
                .map((section) => (
                  <div key={section.id}>
                    <div className="space-y-0.5">
                      {section.items.map((item) => {
                        // "Мои воронки" — expandable with vacancy sub-list
                        if (item.path === "/my-funnels") {
                          // «Мои вакансии» = где я реально участник — ДАЖЕ для
                          // admin/superadmin (иначе взятие заявки любым рекрутёром
                          // выглядело так, будто её взял и сам админ). Просмотр
                          // «всего» без участия — на полной странице /my-funnels.
                          const myVacancies = vacancies
                            .filter(
                              (v) =>
                                v.status === "open" || v.status === "paused",
                            )
                            // Личное принятие (2026-07-08): назначенный, но
                            // ещё не принявший лично — не «моя воронка».
                            .filter(
                              (v) => user && isPersonallyActive(v, user.id),
                            )
                            .slice(0, 10);
                          return (
                            <div key={item.path}>
                              <div className="flex items-center">
                                <NavLink
                                  to={item.path}
                                  className={({ isActive }) =>
                                    clsx(
                                      "flex-1 flex items-center gap-3 py-2.5 px-3 rounded-lg transition-all duration-200 text-sm",
                                      isActive
                                        ? clsx(BLOCK_ACCENT[activeNavigationBlock])
                                        : "text-[var(--hf-dark-300)] hover:text-[var(--hf-dark-100)] hover:bg-[var(--hf-alpha-100)]",
                                    )
                                  }
                                >
                                  <item.icon className="w-4 h-4 flex-shrink-0" />
                                  <span className="font-medium truncate">
                                    {item.label}
                                  </span>
                                </NavLink>
                                {myVacancies.length > 0 && (
                                  <button
                                    onClick={() =>
                                      setExpandedFunnels(!expandedFunnels)
                                    }
                                    className="p-1.5 rounded-lg text-[var(--hf-dark-400)] hover:text-[var(--hf-dark-100)] hover:bg-[var(--hf-alpha-100)] transition-all"
                                  >
                                    <ChevronDown
                                      className={clsx(
                                        "w-3.5 h-3.5 transition-transform",
                                        expandedFunnels && "rotate-180",
                                      )}
                                    />
                                  </button>
                                )}
                              </div>
                              {expandedFunnels && myVacancies.length > 0 && (
                                <div className="ml-4 pl-3 border-l border-[color:var(--hf-white-alpha-05)] mt-0.5 space-y-0.5">
                                  {myVacancies.map((v) => (
                                    <NavLink
                                      key={v.id}
                                      to={`/my-funnels?v=${v.id}`}
                                      className={({ isActive }) =>
                                        clsx(
                                          "flex items-center gap-2 py-1.5 px-2 rounded-md text-xs transition-all",
                                          isActive
                                 ? "text-[var(--hf-status-blue)] bg-[var(--hf-status-blue-bg)]"
                                            : "text-[var(--hf-dark-400)] hover:text-[var(--hf-dark-100)] hover:bg-[var(--hf-alpha-100)]",
                                        )
                                      }
                                    >
                                      <span
                                        className={clsx(
                                          "w-1.5 h-1.5 rounded-full flex-shrink-0",
                                          v.status === "open"
                                            ? "bg-[var(--hf-status-green)]"
                                            : "bg-[var(--hf-status-yellow)]",
                                        )}
                                      />
                                      <span className="truncate">
                                        {v.title}
                                      </span>
                                    </NavLink>
                                  ))}
                                </div>
                              )}
                            </div>
                          );
                        }

                        // "Заявки" — expandable with vacancy request sub-list
                        if (item.path === "/vacancies") {
                          // Единое правило видимости (utils/vacancy.ts), то же,
                          // что и в основном списке «Заявки»: admin/owner/
                          // superadmin видят ВСЕ заявки орга, рекрутёр — свои
                          // созданные И назначенные на него. Раньше админ здесь
                          // видел только НЕназначенные — расхождение с основным
                          // списком «Заявки», где админ видит всё.
                          const isAdminUser = isHrSidebarAdmin;
                          const myClonesFor = new Set<number>();
                          if (user) {
                            vacancies.forEach((v) => {
                              if (v.created_by !== user.id) return;
                              const src = (
                                v.extra_data as
                                  | Record<string, unknown>
                                  | undefined
                              )?.cloned_from_request_id;
                              if (typeof src === "number") myClonesFor.add(src);
                            });
                          }
                          const requestVacancies = vacancies
                            .filter((v) => {
                              const statusOk =
                                v.status === "pending_review" ||
                                v.status === "draft" ||
                                v.status === "open" ||
                                v.status === "paused";
                              if (!statusOk) return false;
                              if (myClonesFor.has(v.id)) return false;
                              return isRequestVisibleTo(v, user?.id, isAdminUser);
                            })
                            .slice(0, 15);
                          return (
                            <div key={item.path}>
                              <div className="flex items-center">
                                <NavLink
                                  to={item.path}
                                  className={({ isActive }) =>
                                    clsx(
                                      "flex-1 flex items-center gap-3 py-2.5 px-3 rounded-lg transition-all duration-200 text-sm",
                                      isActive
                                        ? clsx(BLOCK_ACCENT[activeNavigationBlock])
                                        : "text-[var(--hf-dark-300)] hover:text-[var(--hf-dark-100)] hover:bg-[var(--hf-alpha-100)]",
                                    )
                                  }
                                >
                                  <item.icon className="w-4 h-4 flex-shrink-0" />
                                  <span className="font-medium truncate">
                                    {item.label}
                                  </span>
                                  {assignedDraftCount > 0 && (
                                    <span className="ml-auto flex items-center justify-center min-w-[20px] h-5 px-1.5 text-[length:var(--hf-fs-5xs)] font-bold bg-[var(--hf-status-orange)] text-[var(--hf-white)] rounded-full">
                                      {assignedDraftCount > 99
                                        ? "99+"
                                        : assignedDraftCount}
                                    </span>
                                  )}
                                </NavLink>
                                {requestVacancies.length > 0 && (
                                  <button
                                    onClick={() =>
                                      setExpandedRequests(!expandedRequests)
                                    }
                                    className="p-1.5 rounded-lg text-[var(--hf-dark-400)] hover:text-[var(--hf-dark-100)] hover:bg-[var(--hf-alpha-100)] transition-all"
                                  >
                                    <ChevronDown
                                      className={clsx(
                                        "w-3.5 h-3.5 transition-transform",
                                        expandedRequests && "rotate-180",
                                      )}
                                    />
                                  </button>
                                )}
                              </div>
                              {expandedRequests &&
                                requestVacancies.length > 0 && (
                                  <div className="ml-4 pl-3 border-l border-[color:var(--hf-white-alpha-05)] mt-0.5 space-y-0.5">
                                    {requestVacancies.map((v) => (
                                      <button
                                        key={v.id}
                                        onClick={() => openVacancyModal(v.id)}
                                        className="w-full flex items-center gap-2 py-1.5 px-2 rounded-md text-xs transition-all text-[var(--hf-dark-400)] hover:text-[var(--hf-dark-100)] hover:bg-[var(--hf-alpha-100)]"
                                      >
                                        <span
                                          className={clsx(
                                            "w-1.5 h-1.5 rounded-full flex-shrink-0",
                                            v.status === "pending_review"
                                              ? "bg-[var(--hf-status-purple)]"
                                              : v.status === "draft"
                                                ? "bg-[var(--hf-status-orange)]"
                                                : v.status === "open"
                                                  ? "bg-[var(--hf-status-green)]"
                                                  : "bg-[var(--hf-status-yellow)]",
                                          )}
                                        />
                                        <span className="truncate text-left">
                                          {v.title}
                                        </span>
                                        <span className="text-[var(--hf-dark-500)] truncate ml-auto text-[length:var(--hf-fs-5xs)]">
                                          {getSidebarRequestAuthor(v)}
                                        </span>
                                      </button>
                                    ))}
                                  </div>
                                )}
                            </div>
                          );
                        }

                        return (
                          <NavLink
                            key={item.path}
                            to={item.path}
                            end={item.path.includes("?")}
                            // Метка «это переход из меню» — страница по ней
                            // сбрасывает свой поиск и возвращается на «Все»
                            // (просьба Эльвиры 02.10.2026: повторный клик по
                            // пункту должен срабатывать, а не упираться в
                            // забытое слово в строке поиска).
                            state={{ resetSearch: true }}
                            data-tour={pathToTourAttribute[item.path]}
                            className={({ isActive }) =>
                              clsx(
                                "flex items-center gap-3 py-2.5 px-3 rounded-lg transition-all duration-200 text-sm",
                                isActive
                                  ? clsx(BLOCK_ACCENT[activeNavigationBlock])
                                  : "text-[var(--hf-dark-300)] hover:text-[var(--hf-dark-100)] hover:bg-[var(--hf-alpha-100)]",
                              )
                            }
                          >
                            <item.icon className="w-4 h-4 flex-shrink-0" />
                            <span className="font-medium truncate">
                              {item.label}
                            </span>
                          </NavLink>
                        );
                      })}
                    </div>
                  </div>
                ))}
            </nav>

            <div
              className="app-sidebar-footer flex-shrink-0 border-t border-[color:var(--hf-workspace-divider)]"
              // overflow-y:auto (CSS) обрезал absolute-поповер уведомлений (тот же
              // баг, что в hf-hr-user-menu) → на время показа отдаём overflow:visible
              style={{ overflow: showNotifications ? "visible" : undefined }}
            >
              {/* Notification bell */}
              <div className="relative app-sidebar-footer-section" ref={notifRef} data-notif-root>
                <button
                  onClick={handleToggleNotifications}
                  className="app-sidebar-footer-action w-full text-[var(--hf-dark-300)] hover:text-[var(--hf-status-blue)] hover:bg-[var(--hf-status-blue-bg)]"
                >
                  <Bell className="w-5 h-5" />
                  <span className="font-medium text-sm">Уведомления</span>
                  {unreadCount > 0 && (
                    <span className="absolute top-1.5 left-7 w-4.5 h-4.5 flex items-center justify-center text-[length:var(--hf-fs-6xs)] font-bold bg-[var(--hf-red-500)] text-[var(--hf-white)] rounded-full min-w-[18px] px-1">
                      {unreadCount > 99 ? "99+" : unreadCount}
                    </span>
                  )}
                </button>

                {/* Notifications dropdown */}
                {showNotifications && (
                  <div className="absolute bottom-full left-0 mb-2 w-80 max-h-96 bg-[var(--hf-dark-panel-alpha-95)] backdrop-blur-xl border border-[color:var(--hf-white-alpha-10)] rounded-xl shadow-[var(--hf-shadow-2xl)] overflow-hidden z-50">
                    <div className="flex items-center justify-between px-4 py-3 border-b border-[color:var(--hf-white-alpha-05)]">
                      <span className="text-sm font-medium text-[var(--hf-white)]">
                        Уведомления
                      </span>
                      {unreadCount > 0 && (
                        <button
                          onClick={handleMarkAllRead}
                          className="flex items-center gap-1 text-xs text-[var(--hf-status-blue)] hover:text-[var(--hf-cyan-400)] transition-colors"
                        >
                          <Check className="w-3 h-3" />
                          Прочитать все
                        </button>
                      )}
                    </div>
                    <div className="overflow-y-auto max-h-80">
                      {notificationsLoading ? (
                        <div className="flex items-center justify-center py-8">
                          <div className="hf-loading-spinner h-5 w-5 border-2" />
                        </div>
                      ) : notificationsList.length === 0 ? (
                        <div className="py-8 text-center text-xs text-[color:var(--hf-white-alpha-30)]">
                          Нет уведомлений
                        </div>
                      ) : (
                        notificationsList.map((notif) => (
                          <button
                            key={notif.id}
                            onClick={() => {
                              if (!notif.is_read) handleMarkRead(notif.id);
                              if (notif.link) {
                                navigate(notif.link);
                                setShowNotifications(false);
                              }
                            }}
                            className={clsx(
                              "w-full text-left px-4 py-3 border-b border-[color:var(--hf-white-alpha-03)] hover:bg-[var(--hf-white-alpha-03)] transition-colors",
                              !notif.is_read && "bg-[var(--hf-white-alpha-05)]",
                            )}
                          >
                            <div className="flex items-start gap-2">
                              {!notif.is_read && (
                                <span className="w-2 h-2 rounded-full bg-[var(--hf-status-blue)] flex-shrink-0 mt-1.5" />
                              )}
                              <div
                                className={clsx(
                                  "flex-1 min-w-0",
                                  notif.is_read && "ml-4",
                                )}
                              >
                                <p className="text-xs font-medium text-[var(--hf-white)] truncate">
                                  {notif.title}
                                </p>
                                {notif.message && (
                                  <p className="text-[length:var(--hf-fs-4xs)] text-[color:var(--hf-white-alpha-30)] truncate mt-0.5">
                                    {notif.message}
                                  </p>
                                )}
                                <p className="text-[length:var(--hf-fs-5xs)] text-[color:var(--hf-white-alpha-20)] mt-1">
                                  {new Date(notif.created_at).toLocaleString(
                                    "ru-RU",
                                    {
                                      day: "numeric",
                                      month: "short",
                                      hour: "2-digit",
                                      minute: "2-digit",
                                    },
                                  )}
                                </p>
                              </div>
                            </div>
                          </button>
                        ))
                      )}
                    </div>
                  </div>
                )}
              </div>

              <div className="app-sidebar-user-row">
                <div className="w-10 h-10 rounded-full bg-[var(--hf-accent-bg-20)] flex items-center justify-center">
                  <span className="text-[var(--hf-accent)] font-semibold">
                    {user?.name?.[0]?.toUpperCase() || "U"}
                  </span>
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate">{user?.name}</p>
                  <p className="text-xs text-[var(--hf-dark-400)] truncate">
                    {user?.email}
                  </p>
                  {customRoleName && (
                    <span className="inline-block mt-1 px-2 py-0.5 text-xs bg-[var(--hf-accent-bg-20)] text-[var(--hf-accent)] rounded-full">
                      {customRoleName}
                    </span>
                  )}
                </div>
              </div>
              {!isHrSidebar && <ThemeToggle />}
              <NavLink
                to="/my-profile"
                className={({ isActive }) =>
                  clsx(
                    "app-sidebar-footer-action w-full mb-1",
                    isActive
                      ? "text-[var(--hf-accent)] bg-[var(--hf-accent-bg-10)]"
                      : "text-[var(--hf-dark-300)] hover:text-[var(--hf-dark-100)] hover:bg-[var(--hf-alpha-100)]",
                  )
                }
              >
                <User className="w-5 h-5" />
                <span className="font-medium">Мой профиль</span>
              </NavLink>
              <button
                onClick={handleLogout}
                className="app-sidebar-footer-action w-full text-[var(--hf-dark-300)] hover:text-[var(--hf-status-red)] hover:bg-[var(--hf-status-red-bg)]"
                aria-label="Выйти из аккаунта"
              >
                <LogOut className="w-5 h-5" aria-hidden="true" />
                <span className="font-medium">Выход</span>
              </button>
            </div>
          </>
        )}
      </aside>

      {/* Mobile Header */}
      <header
        className={clsx(
          "lg:hidden border-b px-4 py-3 flex items-center justify-between",
          isHrSidebar
            ? "hf-hr-mobile-header"
            : "glass border-[color:var(--hf-white-alpha-05)]",
        )}
        role="banner"
      >
        <h1
          className={clsx(
            "text-lg font-bold",
            isHrSidebar
              ? "hf-hr-mobile-brand"
              : "bg-[linear-gradient(to_right,var(--hf-accent),var(--hf-accent-hover))] bg-clip-text text-transparent",
          )}
        >
          Enceladus
        </h1>
        <button
          onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          className={clsx(
            "p-2 rounded-lg",
            isHrSidebar
              ? "hf-hr-mobile-menu-trigger"
              : "hover:bg-[var(--hf-bg-dark-panel)]",
          )}
          aria-expanded={mobileMenuOpen}
          aria-controls="mobile-menu"
          aria-label={mobileMenuOpen ? "Закрыть меню" : "Открыть меню"}
        >
          {mobileMenuOpen ? (
            <X className="w-6 h-6" aria-hidden="true" />
          ) : (
            <Menu className="w-6 h-6" aria-hidden="true" />
          )}
        </button>
      </header>

      {/* Mobile Menu Overlay */}
      {mobileMenuOpen && (
        <div
          className={clsx(
            "lg:hidden fixed inset-0 z-50 animate-[fadeIn_0.15s_ease]",
            isHrSidebar ? "hf-hr-mobile-menu-overlay" : "bg-[var(--hf-black-alpha-80)]",
          )}
          onClick={() => setMobileMenuOpen(false)}
          role="dialog"
          aria-modal="true"
          aria-label="Мобильное меню"
        >
          <div
            className={clsx(
              "absolute right-0 top-0 h-full w-64 flex flex-col animate-[slideInRight_0.2s_ease]",
              isHrSidebar ? "hf-hr-mobile-menu" : "glass",
            )}
            onClick={(e) => e.stopPropagation()}
            id="mobile-menu"
          >
            <nav
              className="p-3 overflow-y-auto flex-1"
              aria-label="Мобильная навигация"
            >
              {isHrSidebar ? (
                <div className="hf-hr-mobile-nav-list">
                  {hrMobileNavItems.map((item) => (
                    <NavLink
                      key={item.path}
                      to={item.path}
                      onClick={() => setMobileMenuOpen(false)}
                      className={({ isActive }) =>
                        clsx(
                          "hf-hr-mobile-nav-item",
                          isActive && "hf-hr-mobile-nav-item-active",
                        )
                      }
                    >
                      <item.icon className="hf-hr-mobile-nav-icon" aria-hidden="true" />
                      <span className="font-medium truncate">
                        {item.label}
                      </span>
                    </NavLink>
                  ))}
                </div>
              ) : (
                <>
                  <div className="flex gap-1 mb-4">
                    {navSections.map((section) => {
                      const Icon = BLOCK_ICONS[section.id] || LayoutDashboard;
                      return (
                        <button
                          key={section.id}
                          onClick={() => handleBlockSwitch(section)}
                          className={clsx(
                            "flex-1 flex flex-col items-center gap-1 py-2 rounded-xl transition-all text-xs",
                            activeNavigationBlock === section.id
                              ? clsx("border", BLOCK_ACTIVE_BG[section.id])
                              : "text-[color:var(--hf-white-alpha-30)] border border-transparent",
                          )}
                        >
                          <Icon className="w-4 h-4" />
                          <span className="text-[length:var(--hf-fs-6xs)] font-semibold uppercase">
                            {section.label}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                  {navSections
                    .filter((s) => s.id === activeNavigationBlock)
                    .map((section) => (
                      <div key={section.id}>
                        {section.items.map((item) => (
                          <NavLink
                            key={item.path}
                            to={item.path}
                            onClick={() => setMobileMenuOpen(false)}
                            className={({ isActive }) =>
                              clsx(
                                "flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-200 text-sm",
                                isActive
                                  ? clsx(BLOCK_ACCENT[activeNavigationBlock])
                                  : "text-[var(--hf-dark-300)] hover:text-[var(--hf-dark-100)] hover:bg-[var(--hf-bg-dark-panel)]",
                              )
                            }
                          >
                            <item.icon
                              className="w-4 h-4 flex-shrink-0"
                              aria-hidden="true"
                            />
                            <span className="font-medium truncate">
                              {item.label}
                            </span>
                          </NavLink>
                        ))}
                      </div>
                    ))}
                  {!isHrSidebar && <ThemeToggle />}
                </>
              )}
              <button
                onClick={handleLogout}
                className={clsx(
                  "w-full flex items-center gap-3 px-4 py-3 rounded-xl transition-all duration-200",
                  isHrSidebar
                    ? "hf-hr-mobile-logout"
                    : "text-[var(--hf-dark-300)] hover:text-[var(--hf-status-red)] hover:bg-[var(--hf-status-red-bg)]",
                )}
                aria-label="Выйти из аккаунта"
              >
                <LogOut className="w-5 h-5" aria-hidden="true" />
                <span className="font-medium">Выйти</span>
              </button>
            </nav>
          </div>
        </div>
      )}

      {/* Main Content */}
      <main
        className={clsx(
          "flex-1 overflow-hidden flex flex-col",
          isHrSidebar ? "bg-[var(--hf-workspace-bg)]" : "bg-[var(--bg-body)]",
        )}
        role="main"
        aria-label="Main content"
      >
        {/* Баннер режима наблюдателя (read-only) — ТОЛЬКО в HR/админ-разделах, где
            он действительно только смотрит. В своём рабочем домене (Практика/проекты)
            наблюдатель-практик-лид полноценно работает, поэтому там баннер не висит. */}
        {user?.is_readonly && (routeBlock === "hr" || routeBlock === "admin") && (
          <ObserverBanner scoped={(user?.scope_vacancy_ids?.length ?? 0) > 0} />
        )}
        {/* Вышла новая сборка, а вкладка открыта на старой — предложить обновить. */}
        <UpdateBanner />
        {/* Telegram bot connect banner — показываем если у юзера не привязан tg */}
        <TelegramConnectBanner />
        {/* Impersonation Banner */}
        {isImpersonating() && user && (
          <div
            className="bg-[var(--hf-status-yellow-badge)] border-b border-[color:var(--hf-status-yellow-badge)] px-4 py-3 flex items-center justify-between"
            role="alert"
            aria-live="polite"
          >
            <div className="flex items-center gap-3">
              <Shield className="w-5 h-5 text-[var(--hf-status-yellow)]" aria-hidden="true" />
              <div>
                <p className="text-sm font-semibold text-[var(--hf-yellow-300)]">
                  Режим имперсонации
                </p>
                <p className="text-xs text-[var(--hf-yellow-300)]">
                  Вы действуете от имени:{" "}
                  <span className="font-medium">{user.name}</span> ({user.email}
                  )
                  {user.original_user_name && (
                    <span className="ml-2">
                      • Вернуться к:{" "}
                      <span className="font-medium">
                        {user.original_user_name}
                      </span>
                    </span>
                  )}
                </p>
              </div>
            </div>
            <button
              onClick={handleExitImpersonation}
              className="px-4 py-2 rounded-lg bg-[var(--hf-status-yellow-badge)] hover:bg-[var(--hf-status-yellow-bg)] text-[var(--hf-yellow-300)] hover:text-[var(--hf-yellow-300)] transition-colors text-sm font-medium border border-[color:var(--hf-status-yellow-badge)]"
              aria-label="Выйти из режима имперсонации"
            >
              Выйти из имперсонации
            </button>
          </div>
        )}

        <div
          className={clsx(
            "flex-1 overflow-y-auto overflow-x-hidden relative",
            isHrSidebar ? "bg-[var(--hf-workspace-bg)]" : "bg-[var(--bg-body)]",
          )}
        >
          <Outlet />

          {/* FAB — floating action button for HR block */}
          {isHrSidebar && !mobileMenuOpen && (
            <div className="lg:hidden">
              <FABButton
                onCreateVacancy={() => setShowFabVacancyForm(true)}
                onAddCandidate={() => setShowFabParserModal(true)}
              />
            </div>
          )}
        </div>
      </main>

      {/* Mobile Bottom Navigation */}
      <nav
        className={clsx(
          "lg:hidden border-t px-2 py-2 flex",
          isHrSidebar
            ? "hf-hr-mobile-bottom-nav"
            : "glass border-[color:var(--hf-white-alpha-05)]",
        )}
        aria-label="Нижняя навигация"
      >
        {activeMobileNavItems.slice(0, 4).map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            data-tour={pathToTourAttribute[item.path]}
            className={({ isActive }) =>
              clsx(
                // min-w-0: пункты делят ширину поровну; без него «Все кандидаты»
                // растягивал свой пункт, и на 320 px последний уезжал за край.
                "flex-1 min-w-0 flex flex-col items-center gap-1 px-1 sm:px-2 py-2 rounded-xl transition-all duration-200",
                isHrSidebar
                  ? isActive
                    ? "hf-hr-mobile-bottom-item-active"
                    : "hf-hr-mobile-bottom-item"
                  : isActive
                    ? "text-[var(--hf-accent)]"
                    : "text-[var(--hf-dark-400)] hover:text-[var(--hf-dark-200)]",
              )
            }
            aria-label={item.label}
          >
            <item.icon className="w-5 h-5 flex-shrink-0" aria-hidden="true" />
            <span className="text-[11px] sm:text-xs leading-tight text-center line-clamp-2 max-w-full">{item.label}</span>
          </NavLink>
        ))}
      </nav>

      {/* Sidebar Vacancy Modal */}
      <AnimatePresence>
        {sidebarVacancy && (
          sidebarVacancyMode === "view" ? (
            <SidebarRequestPreviewModal
              key={`sidebar-view-${sidebarVacancy.id}`}
              vacancy={sidebarVacancy}
              onClose={() => setSidebarVacancy(null)}
              onEdit={() => setSidebarVacancyMode("edit")}
              onTaken={() => setSidebarVacancy(null)}
            />
          ) : (
              <VacancyForm
                key={`sidebar-edit-${sidebarVacancy.id}`}
                vacancy={sidebarVacancy}
                onClose={() => setSidebarVacancy(null)}
                onSuccess={() => {
                  setSidebarVacancy(null);
                  fetchVacancies();
                }}
              />
          )
        )}
      </AnimatePresence>

      {/* FAB → Новая вакансия — открывается прямо здесь, без перехода на /vacancies */}
      <AnimatePresence>
        {showFabVacancyForm && (
          <VacancyForm
            key="fab-new-vacancy"
            onClose={() => setShowFabVacancyForm(false)}
            onSuccess={() => {
              setShowFabVacancyForm(false);
              fetchVacancies();
              toast.success("Вакансия создана");
            }}
          />
        )}
      </AnimatePresence>

      {/* FAB → Добавить кандидата — парсер резюме поверх текущей страницы */}
      <AnimatePresence>
        {showFabParserModal && (
          <ParserModal
            type="resume"
            onClose={() => setShowFabParserModal(false)}
            onParsed={() => {
              setShowFabParserModal(false);
              toast.success("Кандидат добавлен");
            }}
            // Добавили — открываем ЕГО карточку (Эльвира, 13.10.2026: «после
            // добавления опять на чужие карточки кидает»). Этот «+» виден, когда
            // окно уже 1024 px (ноутбук с масштабом, полэкрана), и его окно
            // разбора живёт здесь, а не на странице: правка 02.10 подключила
            // открытие только к окну внутри «Все кандидаты», а отсюда справа
            // оставался тот, кто был открыт до добавления. Страница ловит метку
            // openCreatedEntity так же, как resetSearch у пункта меню.
            onCreated={(entityId) => {
              setShowFabParserModal(false);
              navigate(`/all-candidates?entity=${entityId}`, {
                state: { openCreatedEntity: entityId },
              });
            }}
            onAttachedToEntity={(entityId) => {
              setShowFabParserModal(false);
              navigate(`/all-candidates?entity=${entityId}`, {
                state: { openCreatedEntity: entityId },
              });
            }}
          />
        )}
      </AnimatePresence>
    </div>
  );
}
