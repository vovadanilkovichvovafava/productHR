import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Loader2, Plus, Check, X, Clock, ShieldCheck, Lock, RotateCcw,
  Mail, Briefcase, Building2, Send, CalendarDays, MessageSquare,
} from "lucide-react";
import clsx from "clsx";
import toast from "react-hot-toast";
import {
  getAvailableResources, getRequests, createRequest,
  takeInProgress, grantRequest, rejectRequest, revokeGrant,
  getMessages, sendMessage, type AccessMessage,
  type CatalogResource, type AccessRequest, type AccessStatus,
} from "@/services/api/accessHub";
import { useAuthStore } from "@/stores/authStore";
import { useWebSocket } from "@/hooks/useWebSocket";
import { getMyEmployeeProfile, type EmployeeData } from "@/services/api/employees";
import AccessAdmin from "./AccessAdmin";
import type { Me } from "./MiniApp";

/**
 * Хаб доступов — кабинет сотрудника.
 *
 * «Создать заявку» показывает ТОЛЬКО то, что доступно по роли, с учётом условия
 * разблокировки и остатка месячного лимита (заблокированное видно, но с
 * причиной — так понятнее, чем прятать).
 *
 * Ответственный за ресурс анонимен: в заявке заявитель видит «Снабжение».
 * Имя раскрывается только самому ответственному и админам — это приходит с
 * бэкенда, фронт ничего не домысливает.
 */

const STATUS_META: Record<AccessStatus, { label: string; cls: string }> = {
  new:         { label: "Новая",     cls: "hf-ah-chip-new" },
  in_progress: { label: "В работе",  cls: "hf-ah-chip-progress" },
  granted:     { label: "Выдано",    cls: "hf-ah-chip-granted" },
  rejected:    { label: "Отклонено", cls: "hf-ah-chip-rejected" },
  revoked:     { label: "Отозвано",  cls: "hf-ah-chip-revoked" },
};

const CATEGORY_LABELS: Record<string, string> = {
  proxy: "Прокси",
  payment_topup: "Пополнение платёжки",
  payment: "Оплата",
  account: "Аккаунт",
  tg_account: "Telegram-аккаунт",
  consumable: "Расходник",
  other: "Прочее",
};

const fmtDate = (iso: string | null) => {
  if (!iso) return "—";
  const d = new Date(iso);
  return isNaN(d.getTime()) ? "—" : d.toLocaleDateString("ru-RU");
};

type Tab = "cabinet" | "my" | "assigned" | "admin";

export default function AccessHub({ me }: { me?: Me | null }) {
  // В мини-аппе вход идёт по подписи Telegram, и глобальный стор авторизации
  // не заполняется — пользователь приходит пропсом из оболочки. Без этого
  // isAdmin всегда был false, и админ не видел вкладку «Настройка».
  const storeUser = useAuthStore((s) => s.user) as any;
  const user = (me ?? storeUser) as Me | null | undefined;
  const isAdmin = user?.role === "superadmin" || user?.org_role === "owner" || user?.org_role === "admin";

  const [tab, setTab] = useState<Tab>("cabinet");
  const [resources, setResources] = useState<CatalogResource[]>([]);
  const [requests, setRequests] = useState<AccessRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [picked, setPicked] = useState<CatalogResource | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [profile, setProfile] = useState<EmployeeData | null>(null);
  const [chatId, setChatId] = useState<number | null>(null);

  // Карточка сотрудника. 404 (нет записи в штате) и 403 (уволен) — штатные
  // ситуации, а не ошибка: кабинет тогда показывает данные аккаунта.
  useEffect(() => {
    getMyEmployeeProfile().then(setProfile).catch(() => setProfile(null));
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const scope = tab === "assigned" ? "assigned" : "my";
      const [res, reqs] = await Promise.all([
        getAvailableResources(),
        getRequests(scope),
      ]);
      setResources(res);
      setRequests(reqs);
    } catch {
      toast.error("Не удалось загрузить хаб доступов");
    } finally {
      setLoading(false);
    }
  }, [tab]);

  useEffect(() => { load(); }, [load]);

  // Live-обновления (ТЗ п. 5): статус меняет ответственный со своей стороны,
  // и без пуша человек сидел бы перед устаревшим экраном до перезагрузки.
  useWebSocket({
    onEvent: (msg) => {
      if (msg.type === "access_request.updated" || msg.type === "access_request.message") {
        load();
      }
    },
  });

  const act = async (id: number, fn: () => Promise<AccessRequest>) => {
    setBusyId(id);
    try {
      const fresh = await fn();
      setRequests((cur) => cur.map((r) => (r.id === fresh.id ? fresh : r)));
      // выдача/отзыв меняют остаток лимита — обновляем каталог
      getAvailableResources().then(setResources).catch(() => {});
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Не удалось выполнить действие");
    } finally {
      setBusyId(null);
    }
  };

  const openCount = useMemo(
    () => requests.filter((r) => r.status === "new" || r.status === "in_progress").length,
    [requests]
  );

  return (
    <div className="hf-ah-page">
      <div className="hf-ah-tabs">
        <button className={clsx("hf-ah-tab", tab === "cabinet" && "hf-ah-tab-active")} onClick={() => setTab("cabinet")}>
          Мой кабинет
        </button>
        <button className={clsx("hf-ah-tab", tab === "my" && "hf-ah-tab-active")} onClick={() => setTab("my")}>
          Мои заявки {openCount > 0 && <span className="hf-ah-tab-badge">{openCount}</span>}
        </button>
        <button className={clsx("hf-ah-tab", tab === "assigned" && "hf-ah-tab-active")} onClick={() => setTab("assigned")}>
          Мне на выдачу
        </button>
        {isAdmin && (
          <button className={clsx("hf-ah-tab", tab === "admin" && "hf-ah-tab-active")} onClick={() => setTab("admin")}>
            Настройка
          </button>
        )}
      </div>

      {tab === "admin" ? (
        <AccessAdmin onChanged={load} />
      ) : loading ? (
        <div className="hf-ah-loading"><Loader2 className="animate-spin" size={26} /></div>
      ) : tab === "cabinet" ? (
        <Cabinet
          profile={profile}
          fallbackName={user?.name || "—"}
          fallbackEmail={user?.email || null}
          resources={resources}
          onPick={setPicked}
          isAdmin={isAdmin}
        />
      ) : (
        <RequestList
          requests={requests}
          scope={tab}
          isAdmin={isAdmin}
          busyId={busyId}
          onProgress={(id) => act(id, () => takeInProgress(id))}
          onGrant={(id) => act(id, () => grantRequest(id))}
          onReject={(id) => {
            const c = prompt("Причина отказа:");
            if (c === null) return;
            act(id, () => rejectRequest(id, c || undefined));
          }}
          onRevoke={(id) => {
            const c = prompt("Причина отзыва:");
            if (c === null) return;
            act(id, () => revokeGrant(id, c || undefined));
          }}
          onChat={setChatId}
        />
      )}

      {chatId != null && (
        <RequestChat requestId={chatId} onClose={() => setChatId(null)} />
      )}

      {picked && (
        <RequestModal
          resource={picked}
          onClose={() => setPicked(null)}
          onCreated={() => { setPicked(null); load(); }}
        />
      )}
    </div>
  );
}

// ============================================================
// Кабинет: карточка человека + кнопки доступов
// ============================================================

const ACCESS_STATE: Record<string, { cls: string; hint: string }> = {
  granted:  { cls: "hf-ah-access-granted",  hint: "Доступ выдан" },
  pending:  { cls: "hf-ah-access-pending",  hint: "Заявка в работе" },
  rejected: { cls: "hf-ah-access-rejected", hint: "Отказано — можно запросить снова" },
  none:     { cls: "hf-ah-access-none",     hint: "Нажмите, чтобы запросить" },
};

/** Порядок категорий фиксирован: то, чем пользуются чаще, — выше. */
const CATEGORY_ORDER = [
  "proxy", "account", "tg_account", "payment_topup", "payment", "consumable", "other",
];

/** Приоритет сортировки плиток: сначала то, что требует внимания. */
const STATE_RANK: Record<string, number> = { pending: 0, granted: 1, rejected: 2, none: 3 };

/** Короткая подпись под выданным доступом: что именно на руках. */
function grantedSummary(r: CatalogResource): string {
  const values = Object.values(r.granted_params || {}).filter(Boolean);
  return values.length ? `Выдан · ${values.join(", ")}` : "Выдан";
}

function Cabinet({
  profile, fallbackName, fallbackEmail, resources, onPick, isAdmin,
}: {
  profile: EmployeeData | null;
  fallbackName: string;
  fallbackEmail: string | null;
  resources: CatalogResource[];
  onPick: (r: CatalogResource) => void;
  isAdmin: boolean;
}) {
  const [cat, setCat] = useState<string>("all");
  const [q, setQ] = useState("");

  const name = profile?.user_name || fallbackName;
  const initials = name.split(" ").filter(Boolean).slice(0, 2).map((w) => w[0]).join("").toUpperCase();

  const stats = useMemo(() => ({
    granted: resources.filter((r) => r.state === "granted").length,
    pending: resources.filter((r) => r.state === "pending").length,
    free: resources.filter((r) => r.state === "none" && !r.locked).length,
  }), [resources]);

  // Категории — фильтр-чипами, а не отдельными секциями: секции при 1-2 плитках
  // растягивали страницу пустотами, чипы дают ту же навигацию без потери плотности.
  const categories = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const r of resources) counts[r.category] = (counts[r.category] || 0) + 1;
    const known = CATEGORY_ORDER.filter((c) => counts[c]);
    const rest = Object.keys(counts).filter((c) => !CATEGORY_ORDER.includes(c));
    return [...known, ...rest].map((c) => ({
      key: c, label: CATEGORY_LABELS[c] || c, count: counts[c],
    }));
  }, [resources]);

  const searchable = resources.length > 6;

  const visible = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return resources
      .filter((r) => cat === "all" || r.category === cat)
      .filter((r) => !needle || [r.name, r.description, CATEGORY_LABELS[r.category]]
        .filter(Boolean).some((v) => String(v).toLowerCase().includes(needle)))
      // Заблокированные — всегда в конец, они всё равно не кликаются
      .sort((a, b) =>
        (a.locked ? 1 : 0) - (b.locked ? 1 : 0)
        || (STATE_RANK[a.state] ?? 9) - (STATE_RANK[b.state] ?? 9)
        || a.name.localeCompare(b.name, "ru")
      );
  }, [resources, cat, q]);

  return (
    <div className="hf-ah-cabinet">
      {/* Карточка человека со сводкой */}
      <div className="hf-ah-person">
        <div className="hf-ah-person-avatar">{initials || "?"}</div>
        <div className="hf-ah-person-main">
          <div className="hf-ah-person-name">{name}</div>
          <div className="hf-ah-person-facts">
            {profile?.position && <span><Briefcase size={12} /> {profile.position}</span>}
            {profile?.department_name && <span><Building2 size={12} /> {profile.department_name}</span>}
            {(profile?.user_email || fallbackEmail) && (
              <span><Mail size={12} /> {profile?.user_email || fallbackEmail}</span>
            )}
            {profile?.telegram_username && (
              <span><Send size={12} /> @{profile.telegram_username.replace(/^@/, "")}</span>
            )}
            {profile?.department_start_date && (
              <span><CalendarDays size={12} /> в отделе с {fmtDate(profile.department_start_date)}</span>
            )}
          </div>
        </div>
        <div className="hf-ah-person-stats">
          <div className="hf-ah-stat hf-ah-stat-granted"><b>{stats.granted}</b><span>выдано</span></div>
          <div className="hf-ah-stat hf-ah-stat-pending"><b>{stats.pending}</b><span>в работе</span></div>
          <div className="hf-ah-stat"><b>{stats.free}</b><span>доступно</span></div>
        </div>
      </div>

      {resources.length === 0 ? (
        <div className="hf-ah-empty">
          <Lock size={28} />
          <p>Пока нет доступных ресурсов</p>
          <span>
            {isAdmin
              ? "Каталог пуст. Откройте вкладку «Настройка» и добавьте ресурсы — там же есть типовой набор одной кнопкой."
              : "Администратор ещё не открыл доступы. Напишите ему — он добавит ресурсы в хабе."}
          </span>
        </div>
      ) : (
        <>
          <div className="hf-ah-filters">
            <button
              className={clsx("hf-ah-fchip", cat === "all" && "hf-ah-fchip-active")}
              onClick={() => setCat("all")}
            >
              Все <span>{resources.length}</span>
            </button>
            {categories.map((c) => (
              <button
                key={c.key}
                className={clsx("hf-ah-fchip", cat === c.key && "hf-ah-fchip-active")}
                onClick={() => setCat(c.key)}
              >
                {c.label} <span>{c.count}</span>
              </button>
            ))}
            {searchable && (
              <input
                className="hf-ah-access-search"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Найти доступ…"
              />
            )}
          </div>

          {visible.length === 0 ? (
            <div className="hf-ah-empty"><p>Ничего не найдено</p></div>
          ) : (
            <div className="hf-ah-access-grid">
              {visible.map((r) => {
                const meta = ACCESS_STATE[r.locked ? "none" : r.state] || ACCESS_STATE.none;
                const disabled = r.locked || r.state === "pending";
                const left = r.limit_per_month != null ? r.limit_per_month - r.used_this_month : null;
                return (
                  <button
                    key={r.id}
                    className={clsx("hf-ah-access", meta.cls, r.locked && "hf-ah-access-locked")}
                    disabled={disabled}
                    onClick={() => onPick(r)}
                    title={r.locked ? r.lock_reason || undefined : meta.hint}
                  >
                    <span className="hf-ah-access-icon">
                      {r.locked ? <Lock size={15} />
                        : r.state === "granted" ? <Check size={15} />
                        : r.state === "pending" ? <Clock size={15} />
                        : r.state === "rejected" ? <X size={15} />
                        : <Plus size={15} />}
                    </span>
                    <span className="hf-ah-access-body">
                      <span className="hf-ah-access-name">{r.name}</span>
                      <span className="hf-ah-access-sub">
                        {r.locked ? r.lock_reason
                          : r.state === "granted" ? grantedSummary(r)
                          : r.state === "pending" ? "Заявка в работе"
                          : r.state === "rejected" ? "Отказано — можно повторить"
                          : r.description || CATEGORY_LABELS[r.category] || "Запросить"}
                      </span>
                    </span>
                    {!r.locked && left != null && (
                      <span className="hf-ah-access-left" title="Осталось в этом месяце">
                        {left}/{r.limit_per_month}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ============================================================
// Список заявок
// ============================================================

function RequestList({
  requests, scope, isAdmin, busyId, onProgress, onGrant, onReject, onRevoke, onChat,
}: {
  requests: AccessRequest[];
  scope: Tab;
  isAdmin: boolean;
  busyId: number | null;
  onProgress: (id: number) => void;
  onGrant: (id: number) => void;
  onReject: (id: number) => void;
  onRevoke: (id: number) => void;
  onChat: (id: number) => void;
}) {
  if (requests.length === 0) {
    return (
      <div className="hf-ah-empty">
        <ShieldCheck size={28} />
        <p>{scope === "assigned" ? "На вас пока ничего не назначено" : "Заявок пока нет"}</p>
        <span>{scope === "assigned" ? "Заявки приходят по типам ресурсов, за которые вы отвечаете" : "Загляните во вкладку «Создать заявку»"}</span>
      </div>
    );
  }

  return (
    <div className="hf-ah-list">
      {requests.map((r) => {
        const meta = STATUS_META[r.status];
        const busy = busyId === r.id;
        return (
          <div key={r.id} className={clsx("hf-ah-row", busy && "hf-ah-row-busy")}>
            <div className="hf-ah-row-main">
              <div className="hf-ah-row-head">
                <span className="hf-ah-row-name">{r.resource_name}</span>
                <span className={clsx("hf-ah-chip", meta.cls)}>{meta.label}</span>
                <span className="hf-ah-row-cat">{CATEGORY_LABELS[r.resource_category] || r.resource_category}</span>
              </div>
              {Object.keys(r.params).length > 0 && (
                <div className="hf-ah-row-params">
                  {Object.entries(r.params).map(([k, v]) => (
                    <span key={k} className="hf-ah-param"><b>{k}:</b> {String(v)}</span>
                  ))}
                </div>
              )}
              {r.comment && <div className="hf-ah-row-comment">{r.comment}</div>}
              <div className="hf-ah-row-meta">
                <span><Clock size={11} /> {fmtDate(r.created_at)}</span>
                {scope === "assigned" || isAdmin
                  ? <span>Заявитель: {r.requester_name || "—"}</span>
                  : <span>Исполнитель: {r.assignee_display}</span>}
                {r.decision_comment && <span>Решение: {r.decision_comment}</span>}
              </div>
            </div>

            <div className="hf-ah-row-actions">
              {busy && <Loader2 className="animate-spin" size={16} />}
              {!busy && r.can_decide && r.status === "new" && (
                <button className="hf-ah-btn" onClick={() => onProgress(r.id)}>В работу</button>
              )}
              {!busy && r.can_decide && (
                <>
                  <button className="hf-ah-btn hf-ah-btn-ok" onClick={() => onGrant(r.id)}>
                    <Check size={13} /> Выдать
                  </button>
                  <button className="hf-ah-btn hf-ah-btn-no" onClick={() => onReject(r.id)}>
                    <X size={13} /> Отклонить
                  </button>
                </>
              )}
              {!busy && r.status === "granted" && (isAdmin || r.assignee_user_id) && (
                <button className="hf-ah-btn" onClick={() => onRevoke(r.id)}>
                  <RotateCcw size={13} /> Отозвать
                </button>
              )}
              <button className="hf-ah-btn" onClick={() => onChat(r.id)}>
                <MessageSquare size={13} /> Чат
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ============================================================
// Модалка создания заявки
// ============================================================

function RequestModal({
  resource, onClose, onCreated,
}: { resource: CatalogResource; onClose: () => void; onCreated: () => void }) {
  const [params, setParams] = useState<Record<string, string>>({});
  const [comment, setComment] = useState("");
  const [amount, setAmount] = useState("");
  const [saving, setSaving] = useState(false);

  const submit = async () => {
    setSaving(true);
    try {
      await createRequest({
        resource_id: resource.id,
        params,
        comment: comment.trim() || null,
        amount: amount ? Number(amount) : null,
      });
      toast.success("Заявка отправлена");
      onCreated();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Не удалось отправить заявку");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="hf-ah-overlay" onClick={() => !saving && onClose()}>
      <div className="hf-ah-modal" onClick={(e) => e.stopPropagation()}>
        <div className="hf-ah-modal-head">
          <h3>{resource.name}</h3>
          <button onClick={() => !saving && onClose()}><X size={16} /></button>
        </div>

        {resource.description && <p className="hf-ah-modal-desc">{resource.description}</p>}

        <div className="hf-ah-modal-body">
          {(resource.params_schema || []).map((p) => (
            <label key={p.key} className="hf-ah-field">
              <span>{p.label}{p.required && " *"}</span>
              {p.type === "select" ? (
                <select
                  value={params[p.key] || ""}
                  onChange={(e) => setParams({ ...params, [p.key]: e.target.value })}
                >
                  <option value="">— выберите —</option>
                  {(p.options || []).map((o) => <option key={o} value={o}>{o}</option>)}
                </select>
              ) : (
                <input
                  type={p.type === "number" ? "number" : "text"}
                  value={params[p.key] || ""}
                  onChange={(e) => setParams({ ...params, [p.key]: e.target.value })}
                />
              )}
            </label>
          ))}

          {resource.limit_amount_month != null && (
            <label className="hf-ah-field">
              <span>Сумма{resource.currency ? `, ${resource.currency}` : ""}</span>
              <input type="number" value={amount} onChange={(e) => setAmount(e.target.value)} />
            </label>
          )}

          <label className="hf-ah-field">
            <span>Комментарий</span>
            <textarea rows={3} value={comment} onChange={(e) => setComment(e.target.value)}
              placeholder="Зачем нужен ресурс — поможет быстрее выдать" />
          </label>
        </div>

        <div className="hf-ah-modal-foot">
          <button className="hf-ah-btn" onClick={onClose} disabled={saving}>Отмена</button>
          <button className="hf-ah-btn hf-ah-btn-primary" onClick={submit} disabled={saving}>
            {saving ? "Отправляю…" : "Отправить заявку"}
          </button>
        </div>
      </div>
    </div>
  );
}


// ============================================================
// Анонимный чат по заявке (ТЗ п. 3.5)
// ============================================================

function RequestChat({ requestId, onClose }: { requestId: number; onClose: () => void }) {
  const [items, setItems] = useState<AccessMessage[]>([]);
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  const load = useCallback(async () => {
    try {
      setItems(await getMessages(requestId));
    } catch {
      toast.error("Не удалось загрузить переписку");
    } finally {
      setLoading(false);
    }
  }, [requestId]);

  useEffect(() => { load(); }, [load]);

  // Новое сообщение прилетает пушем — подтягиваем, не заставляя обновлять
  useWebSocket({
    onEvent: (msg) => {
      if (msg.type === "access_request.message" && msg.payload?.request_id === requestId) load();
    },
  });

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [items.length]);

  const send = async () => {
    const value = text.trim();
    if (!value) return;
    setSending(true);
    try {
      await sendMessage(requestId, value);
      setText("");
      await load();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Не удалось отправить");
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="hf-ah-overlay" onClick={onClose}>
      <div className="hf-ah-modal hf-ah-chat" onClick={(e) => e.stopPropagation()}>
        <div className="hf-ah-modal-head">Чат по заявке #{requestId}</div>

        <div className="hf-ah-chat-body">
          {loading ? (
            <div className="hf-ah-loading"><Loader2 className="animate-spin" size={20} /></div>
          ) : items.length === 0 ? (
            <div className="hf-ah-chat-empty">
              Сообщений пока нет. Здесь можно уточнить детали — собеседник
              получит их в Telegram и сможет ответить прямо оттуда.
            </div>
          ) : (
            items.map((m) => (
              <div key={m.id} className={clsx("hf-ah-msg", m.mine && "hf-ah-msg-mine")}>
                <div className="hf-ah-msg-author">{m.author}</div>
                <div className="hf-ah-msg-text">{m.text}</div>
                <div className="hf-ah-msg-time">{fmtDate(m.created_at)}</div>
              </div>
            ))
          )}
          <div ref={bottomRef} />
        </div>

        <div className="hf-ah-chat-input">
          <input
            value={text}
            placeholder="Сообщение…"
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") send(); }}
          />
          <button className="hf-ah-btn hf-ah-btn-primary" onClick={send} disabled={sending || !text.trim()}>
            {sending ? <Loader2 className="animate-spin" size={14} /> : <Send size={14} />}
          </button>
        </div>

        <div className="hf-ah-modal-foot">
          <button className="hf-ah-btn" onClick={onClose}>Закрыть</button>
        </div>
      </div>
    </div>
  );
}
