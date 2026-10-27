import { useCallback, useEffect, useMemo, useState } from "react";
import { Loader2, Plus, Pencil, Sparkles, Save, EyeOff, Eye } from "lucide-react";
import clsx from "clsx";
import toast from "react-hot-toast";
import {
  getCatalog, createResource, updateResource,
  getCustomRoles, getOrgMembers, getRoleResources, setRoleResources,
  type CatalogResource, type CustomRoleBrief, type OrgMemberBrief,
} from "@/services/api/accessHub";

/**
 * Настройка хаба: каталог ресурсов и конструктор ролей.
 *
 * Экран админский — раньше каталог можно было наполнить только запросами к
 * API, то есть функция фактически была недоступна.
 *
 * Роли НЕ заводятся заново: берутся те же CustomRole, что уже есть в
 * Энцеладусе. Две несогласованные модели прав были бы хуже отсутствия любой.
 */

const CATEGORIES: { value: string; label: string }[] = [
  { value: "proxy", label: "Прокси" },
  { value: "payment_topup", label: "Пополнение платёжки" },
  { value: "payment", label: "Оплата" },
  { value: "account", label: "Аккаунт" },
  { value: "tg_account", label: "Telegram-аккаунт" },
  { value: "consumable", label: "Расходник" },
  { value: "other", label: "Другое" },
];

const UNLOCK: { value: string; label: string; hint: string }[] = [
  { value: "always", label: "Всегда", hint: "Доступен сразу" },
  {
    value: "prometheus_accepted",
    label: "После зачисления в штат",
    hint: "Пока человек не принят — ресурс заблокирован с указанием причины",
  },
];

/** Базовый справочник типов из ТЗ, п. 3.3: «прокси, пополнение платёжки,
 *  оплата, аккаунт, расходник, TG-аккаунт и другие». Заводится сам при
 *  первом открытии, чтобы у сотрудника сразу были кнопки, а не пустой экран. */
const STARTER: Array<Parameters<typeof createResource>[0]> = [
  { key: "proxy", name: "Прокси", category: "proxy", description: "Резидентный прокси под задачу", unlock_condition: "always", limit_per_month: 5, available_to_all: true },
  { key: "tg_account", name: "Telegram-аккаунт", category: "tg_account", description: "Рабочий аккаунт для связи", unlock_condition: "always", limit_per_month: 3, available_to_all: true },
  { key: "service_account", name: "Аккаунт сервиса", category: "account", description: "Доступ к рабочему сервису", unlock_condition: "always", available_to_all: true },
  { key: "card_topup", name: "Пополнение платёжки", category: "payment_topup", description: "Пополнение рабочей карты", unlock_condition: "prometheus_accepted", limit_amount_month: 50000, currency: "RUB" },
  { key: "subscription", name: "Оплата подписки", category: "payment", description: "Оплата сервиса по счёту", unlock_condition: "prometheus_accepted", limit_amount_month: 30000, currency: "RUB" },
  { key: "consumable", name: "Расходник", category: "consumable", description: "Расходные материалы", unlock_condition: "always", limit_per_month: 10, available_to_all: true },
];

const RU2LAT: Record<string, string> = {
  а: "a", б: "b", в: "v", г: "g", д: "d", е: "e", ё: "e", ж: "zh", з: "z", и: "i",
  й: "y", к: "k", л: "l", м: "m", н: "n", о: "o", п: "p", р: "r", с: "s", т: "t",
  у: "u", ф: "f", х: "h", ц: "c", ч: "ch", ш: "sh", щ: "sch", ъ: "", ы: "y", ь: "",
  э: "e", ю: "yu", я: "ya",
};

/** key уникален в организации и участвует в URL-подобных местах — только латиница. */
function slugify(name: string): string {
  const s = name.toLowerCase().split("").map((c) => RU2LAT[c] ?? c).join("");
  return s.replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 40) || "resource";
}

export default function AccessAdmin({ onChanged }: { onChanged?: () => void }) {
  const [section, setSection] = useState<"catalog" | "roles">("catalog");
  const [resources, setResources] = useState<CatalogResource[]>([]);
  const [roles, setRoles] = useState<CustomRoleBrief[]>([]);
  const [members, setMembers] = useState<OrgMemberBrief[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<CatalogResource | "new" | null>(null);
  const [seeding, setSeeding] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      // Роли и участники — справочники для формы; их отсутствие не должно
      // мешать работе с каталогом, поэтому падение гасим отдельно.
      const [res, rs, ms] = await Promise.all([
        getCatalog(true),
        getCustomRoles().catch(() => [] as CustomRoleBrief[]),
        getOrgMembers().catch(() => [] as OrgMemberBrief[]),
      ]);
      setResources(res);
      setRoles(rs);
      setMembers(ms);
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Не удалось загрузить настройки");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const seed = useCallback(async (silent = false) => {
    setSeeding(true);
    try {
      let created = 0;
      for (const r of STARTER) {
        try { await createResource(r); created += 1; } catch { /* уже есть — пропускаем */ }
      }
      if (!silent) {
        toast.success(created ? `Добавлено ресурсов: ${created}` : "Всё уже заведено");
      }
      await load();
      onChanged?.();
    } finally {
      setSeeding(false);
    }
  }, [load, onChanged]);


  if (loading) {
    return <div className="hf-ah-loading"><Loader2 className="animate-spin" size={26} /></div>;
  }

  return (
    <div className="hf-ah-adm">
      <div className="hf-ah-filters">
        <button
          className={clsx("hf-ah-fchip", section === "catalog" && "hf-ah-fchip-active")}
          onClick={() => setSection("catalog")}
        >
          Каталог · {resources.length}
        </button>
        <button
          className={clsx("hf-ah-fchip", section === "roles" && "hf-ah-fchip-active")}
          onClick={() => setSection("roles")}
        >
          Роли · {roles.length}
        </button>
      </div>

      {section === "catalog" ? (
        <>
          <div className="hf-ah-adm-actions">
            <button className="hf-ah-btn hf-ah-btn-primary" onClick={() => setEditing("new")}>
              <Plus size={15} /> Добавить ресурс
            </button>
            {/* Кнопка нужна и с непустым каталогом: типовой набор мог быть
                удалён по одному или сюда добавили свой ресурс раньше. */}
            <button className="hf-ah-btn" onClick={() => seed()} disabled={seeding} title="Завести типы из ТЗ, уже существующие пропускаются">
              {seeding ? <Loader2 className="animate-spin" size={15} /> : <Sparkles size={15} />}
              Типовой набор
            </button>
          </div>

          {resources.length === 0 ? (
            <div className="hf-ah-empty">
              <p>Каталог пуст</p>
              <span>Добавьте ресурс вручную или создайте типовой набор одной кнопкой</span>
            </div>
          ) : (
            <div className="hf-ah-adm-list">
              {resources.map((r) => (
                <ResourceRow
                  key={r.id}
                  res={r}
                  onEdit={() => setEditing(r)}
                  onToggle={async () => {
                    try {
                      const fresh = await updateResource(r.id, { is_active: !r.is_active });
                      setResources((cur) => cur.map((x) => (x.id === fresh.id ? fresh : x)));
                      onChanged?.();
                    } catch (e: any) {
                      toast.error(e?.response?.data?.detail || "Не удалось изменить");
                    }
                  }}
                />
              ))}
            </div>
          )}
        </>
      ) : (
        <RoleBuilder roles={roles} resources={resources} members={members} />
      )}

      {editing && (
        <ResourceForm
          res={editing === "new" ? null : editing}
          members={members}
          resources={resources}
          onClose={() => setEditing(null)}
          onSaved={async () => { setEditing(null); await load(); onChanged?.(); }}
        />
      )}
    </div>
  );
}

// ============================================================
// Строка каталога
// ============================================================

function ResourceRow({
  res, onEdit, onToggle,
}: { res: CatalogResource; onEdit: () => void; onToggle: () => void }) {
  const cat = CATEGORIES.find((c) => c.value === res.category)?.label || res.category;
  const limits: string[] = [];
  if (res.limit_per_month) limits.push(`${res.limit_per_month} шт./мес`);
  if (res.limit_amount_month) limits.push(`${res.limit_amount_month} ${res.currency || ""}/мес`);

  return (
    <div className={clsx("hf-ah-adm-row", !res.is_active && "hf-ah-adm-row-off")}>
      <div className="hf-ah-adm-row-main">
        <div className="hf-ah-adm-row-name">{res.name}</div>
        <div className="hf-ah-adm-row-meta">
          <span>{cat}</span>
          <span>· {res.responsible_name || "ответственный не назначен"}</span>
          {limits.length > 0 && <span>· {limits.join(", ")}</span>}
          {res.available_to_all && <span>· всем</span>}
          {res.unlock_condition !== "always" && <span>· после зачисления</span>}
        </div>
      </div>
      <button className="hf-ah-adm-icon" onClick={onToggle} title={res.is_active ? "Скрыть" : "Включить"}>
        {res.is_active ? <Eye size={16} /> : <EyeOff size={16} />}
      </button>
      <button className="hf-ah-adm-icon" onClick={onEdit} title="Изменить">
        <Pencil size={16} />
      </button>
    </div>
  );
}

// ============================================================
// Форма ресурса
// ============================================================

function ResourceForm({
  res, members, resources, onClose, onSaved,
}: {
  res: CatalogResource | null;
  members: OrgMemberBrief[];
  resources: CatalogResource[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = useState(res?.name || "");
  const [category, setCategory] = useState(res?.category || "proxy");
  const [description, setDescription] = useState(res?.description || "");
  const [responsible, setResponsible] = useState<string>(
    res?.responsible_user_id ? String(res.responsible_user_id) : ""
  );
  const [unlock, setUnlock] = useState(res?.unlock_condition || "always");
  const [perMonth, setPerMonth] = useState(res?.limit_per_month ? String(res.limit_per_month) : "");
  const [amountMonth, setAmountMonth] = useState(
    res?.limit_amount_month ? String(res.limit_amount_month) : ""
  );
  const [currency, setCurrency] = useState(res?.currency || "RUB");
  const [forAll, setForAll] = useState<boolean>(res ? !!res.available_to_all : true);
  const [saving, setSaving] = useState(false);
  const [allPeople, setAllPeople] = useState(false);

  // Выдают доступы снабженцы и админы, а не весь штат. Полный список
  // сотрудников в этом поле — источник ошибок: ответственным легко назначить
  // случайного человека, и заявки уедут не туда.
  //
  // Уже назначенных ответственных оставляем всегда: иначе, открыв ресурс на
  // редактирование, админ не увидел бы текущего владельца в списке.
  const issuers = useMemo(() => {
    const already = new Set(
      resources.map((r) => r.responsible_user_id).filter(Boolean) as number[]
    );
    if (res?.responsible_user_id) already.add(res.responsible_user_id);
    return members.filter(
      (m) => m.role === "owner" || m.role === "admin" || already.has(m.user_id)
    );
  }, [members, resources, res]);

  const shown = allPeople ? members : issuers;

  const save = async () => {
    if (!name.trim()) { toast.error("Укажите название"); return; }
    setSaving(true);
    try {
      const payload = {
        name: name.trim(),
        category,
        description: description.trim() || null,
        responsible_user_id: responsible ? Number(responsible) : null,
        unlock_condition: unlock,
        limit_per_month: perMonth ? Number(perMonth) : null,
        limit_amount_month: amountMonth ? Number(amountMonth) : null,
        currency: amountMonth ? currency : null,
        available_to_all: forAll,
      };
      if (res) await updateResource(res.id, payload);
      else await createResource({ ...payload, key: slugify(name) });
      toast.success(res ? "Сохранено" : "Ресурс добавлен");
      onSaved();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Не удалось сохранить");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="hf-ah-overlay" onClick={onClose}>
      <div className="hf-ah-modal" onClick={(e) => e.stopPropagation()}>
        <div className="hf-ah-modal-head">{res ? "Изменить ресурс" : "Новый ресурс"}</div>
        <div className="hf-ah-modal-body">
          <label className="hf-ah-field">
            <span>Название</span>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Прокси RU" />
          </label>

          <label className="hf-ah-field">
            <span>Категория</span>
            <select value={category} onChange={(e) => setCategory(e.target.value)}>
              {CATEGORIES.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
            </select>
          </label>

          <label className="hf-ah-field">
            <span>Описание</span>
            <input
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Коротко, зачем этот доступ"
            />
          </label>

          <label className="hf-ah-field">
            <span>Кто выдаёт</span>
            <select value={responsible} onChange={(e) => setResponsible(e.target.value)}>
              <option value="">— не назначен (заявки пойдут админам) —</option>
              {shown.map((m) => (
                <option key={m.user_id} value={m.user_id}>
                  {m.user_name || m.user_email || `#${m.user_id}`}
                  {m.role === "owner" || m.role === "admin" ? " · админ" : ""}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="hf-ah-adm-link"
            onClick={() => setAllPeople((v) => !v)}
          >
            {allPeople
              ? "Показывать только снабженцев и админов"
              : `Показать весь штат (${members.length})`}
          </button>

          <label className="hf-ah-field">
            <span>Когда доступен</span>
            <select value={unlock} onChange={(e) => setUnlock(e.target.value)}>
              {UNLOCK.map((u) => <option key={u.value} value={u.value}>{u.label}</option>)}
            </select>
          </label>

          <label className={clsx("hf-ah-adm-check", forAll && "hf-ah-adm-check-on")}>
            <input type="checkbox" checked={forAll} onChange={() => setForAll((v) => !v)} />
            <span className="hf-ah-adm-check-name">Доступен всем сотрудникам</span>
          </label>
          <div className="hf-ah-adm-hint">
            Без этой галочки ресурс увидят только те, кому он открыт ролью. У большинства
            сотрудников роли нет — для них ресурс останется невидимым.
          </div>

          <div className="hf-ah-adm-two">
            <label className="hf-ah-field">
              <span>Лимит, шт./мес</span>
              <input
                inputMode="numeric" value={perMonth}
                onChange={(e) => setPerMonth(e.target.value.replace(/\D/g, ""))}
                placeholder="без лимита"
              />
            </label>
            <label className="hf-ah-field">
              <span>Лимит, сумма/мес</span>
              <input
                inputMode="numeric" value={amountMonth}
                onChange={(e) => setAmountMonth(e.target.value.replace(/\D/g, ""))}
                placeholder="без лимита"
              />
            </label>
          </div>

          {amountMonth && (
            <label className="hf-ah-field">
              <span>Валюта</span>
              <select value={currency} onChange={(e) => setCurrency(e.target.value)}>
                {["RUB", "USD", "EUR", "USDT"].map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </label>
          )}
        </div>
        <div className="hf-ah-modal-foot">
          <button className="hf-ah-btn" onClick={onClose}>Отмена</button>
          <button className="hf-ah-btn hf-ah-btn-primary" onClick={save} disabled={saving}>
            {saving ? <Loader2 className="animate-spin" size={15} /> : <Save size={15} />}
            Сохранить
          </button>
        </div>
      </div>
    </div>
  );
}

// ============================================================
// Конструктор ролей
// ============================================================

function RoleBuilder({
  roles, resources, members,
}: { roles: CustomRoleBrief[]; resources: CatalogResource[]; members: OrgMemberBrief[] }) {
  const [roleId, setRoleId] = useState<number | null>(roles[0]?.id ?? null);
  const [checked, setChecked] = useState<Set<number>>(new Set());
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!roleId) return;
    setLoading(true);
    getRoleResources(roleId)
      .then((ids) => setChecked(new Set(ids)))
      .catch(() => toast.error("Не удалось загрузить права роли"))
      .finally(() => setLoading(false));
  }, [roleId]);

  // Сколько человек реально сидит на роли — без этого непонятно, на кого влияет
  const headcount = useMemo(() => {
    const map = new Map<number, number>();
    members.forEach((m) => {
      if (m.custom_role_id) map.set(m.custom_role_id, (map.get(m.custom_role_id) || 0) + 1);
    });
    return map;
  }, [members]);

  if (roles.length === 0) {
    return (
      <div className="hf-ah-empty">
        <p>В организации ещё нет ролей</p>
        <span>Роли создаются в веб-версии, в разделе управления доступом. Здесь они появятся сразу после создания.</span>
      </div>
    );
  }

  const save = async () => {
    if (!roleId) return;
    setSaving(true);
    try {
      await setRoleResources(roleId, Array.from(checked));
      toast.success("Права роли сохранены");
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Не удалось сохранить");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="hf-ah-adm-roles">
      <div className="hf-ah-filters">
        {roles.map((r) => (
          <button
            key={r.id}
            className={clsx("hf-ah-fchip", roleId === r.id && "hf-ah-fchip-active")}
            onClick={() => setRoleId(r.id)}
          >
            {r.name}
            {headcount.get(r.id) ? ` · ${headcount.get(r.id)}` : ""}
          </button>
        ))}
      </div>

      {resources.length === 0 ? (
        <div className="hf-ah-empty">
          <p>Сначала заполните каталог</p>
          <span>Отмечать нечего — во вкладке «Каталог» нет ни одного ресурса</span>
        </div>
      ) : loading ? (
        <div className="hf-ah-loading"><Loader2 className="animate-spin" size={22} /></div>
      ) : (
        <>
          <div className="hf-ah-adm-hint">
            Отмеченные ресурсы роль сможет запрашивать сама. Админам каталог виден целиком независимо от галочек.
          </div>
          <div className="hf-ah-adm-list">
            {resources.map((r) => {
              const on = checked.has(r.id);
              return (
                <label key={r.id} className={clsx("hf-ah-adm-check", on && "hf-ah-adm-check-on")}>
                  <input
                    type="checkbox"
                    checked={on}
                    onChange={() => {
                      setChecked((cur) => {
                        const next = new Set(cur);
                        if (next.has(r.id)) next.delete(r.id); else next.add(r.id);
                        return next;
                      });
                    }}
                  />
                  <span className="hf-ah-adm-check-name">{r.name}</span>
                  <span className="hf-ah-adm-check-cat">
                    {CATEGORIES.find((c) => c.value === r.category)?.label || r.category}
                  </span>
                </label>
              );
            })}
          </div>
          <button className="hf-ah-btn hf-ah-btn-primary hf-ah-adm-save" onClick={save} disabled={saving}>
            {saving ? <Loader2 className="animate-spin" size={15} /> : <Save size={15} />}
            Сохранить права роли
          </button>
        </>
      )}
    </div>
  );
}
