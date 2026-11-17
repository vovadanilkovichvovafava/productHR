import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Plus, X } from "lucide-react";
import toast from "react-hot-toast";
import { HuntflowInfoRow as InfoRow } from "@/components/hr/HuntflowControls";
import {
  addEntityParticipant,
  getEntityTeam,
  removeEntityParticipant,
  setEntityHr,
  setEntityMentor,
  undoEntityHr,
  type EntityTeam,
} from "@/services/api/entities";
import { getAssignableUsers, type AssignableUser } from "@/services/api/vacancies";
import { getErrorDetail } from "@/utils";

// Строки «HR» и «Участники» в шапке карточки (тикет Маши 13.11.2026, таблица
// «трек АТС»: «менять основного HR, откреплять второго… без потери истории»).
// HR у кандидата один — во всех его воронках; при смене прежний становится
// сорсером, если сорсера ещё нет (решение владельца 16.11.2026). Правила —
// backend services/candidate_hr.py. Отмена смены — корзина у строки
// «Сменился HR» в ленте воронки.

const chip =
  "inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-[var(--hf-bg-panel)] text-[var(--hf-main-900)] border border-[color:var(--hf-main-200)] hf-dark-disabled:bg-[var(--hf-white-alpha-06)] hf-dark-disabled:text-[var(--hf-dark-200)] hf-dark-disabled:border-[color:var(--hf-white-alpha-10)]";
const ghostBtn =
  "inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium text-[var(--hf-main-600)] border border-dashed border-[color:var(--hf-main-300)] hover:text-[var(--hf-main-900)] hover:border-[color:var(--hf-main-500)] hf-dark-disabled:text-[var(--hf-dark-300)]";

// Команда открытых карточек: при повторном открытии строки рисуются сразу,
// без ожидания запроса (он всё равно уходит и освежает данные).
const teamCache = new Map<number, EntityTeam>();

export function CandidateTeamRows({
  entityId,
  readonly,
  refreshKey,
  onChanged,
  showMentor,
  initialHr,
}: {
  entityId: number;
  readonly?: boolean;
  /** Показать «Ментор практики» и без ментора (кандидат на практике и дальше). */
  showMentor?: boolean;
  /** Меняется, когда карточку надо перечитать (смена этапа, «Забрать»…). */
  refreshKey?: unknown;
  /** Команда поменялась — карточке перечитать метки и ленту. */
  onChanged?: () => void;
  /** HR из данных карточки (метка «HR: …») — чтобы строка «HR» была видна
   *  сразу, вместе с «Сорсером», а не после отдельного запроса. */
  initialHr?: { id: number; name: string | null } | null;
}) {
  // Строки «HR» и «Ментор» раньше появлялись только после ответа
  // /entities/{id}/team — позже «Сорсера», и шапка карточки прыгала
  // (владелец, 16.11.2026). Теперь они рисуются сразу: из кэша прошлого
  // открытия или из данных карточки, а ответ сервера их уточняет.
  const placeholder = (): EntityTeam => ({
    hr: initialHr ? { id: initialHr.id, name: initialHr.name } : null,
    hr_from_board: false,
    participants: [],
    sourcers: [],
    in_funnels: false,
    mentor: undefined,
    mentor_options: [],
  });
  const [team, setTeamState] = useState<EntityTeam | null>(() => teamCache.get(entityId) ?? placeholder());
  const [loaded, setLoaded] = useState(() => teamCache.has(entityId));
  const setTeam = useCallback(
    (next: EntityTeam | null) => {
      if (next) teamCache.set(entityId, next);
      setTeamState(next);
    },
    [entityId],
  );
  const [users, setUsers] = useState<AssignableUser[]>([]);
  const [changeOpen, setChangeOpen] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const addRef = useRef<HTMLDivElement>(null);
  const [mentorOpen, setMentorOpen] = useState(false);
  const mentorRef = useRef<HTMLDivElement>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const historyRef = useRef<HTMLDivElement>(null);

  // Другая карточка — сразу её кэш или заглушка из её данных, а не прежняя.
  const shownFor = useRef(entityId);
  if (shownFor.current !== entityId) {
    shownFor.current = entityId;
    setTeamState(teamCache.get(entityId) ?? placeholder());
    setLoaded(teamCache.has(entityId));
  }

  const load = useCallback(async () => {
    try {
      setTeam(await getEntityTeam(entityId));
      setLoaded(true);
    } catch {
      setLoaded(true);
    }
  }, [entityId, setTeam]);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  const loadUsers = useCallback(async () => {
    if (users.length) return;
    try {
      setUsers(await getAssignableUsers({ includeOwners: true }));
    } catch {
      toast.error("Не удалось загрузить список рекрутёров");
    }
  }, [users.length]);

  useEffect(() => {
    if (!addOpen && !mentorOpen && !historyOpen) return;
    const onClick = (e: MouseEvent) => {
      if (addRef.current && !addRef.current.contains(e.target as Node)) setAddOpen(false);
      if (mentorRef.current && !mentorRef.current.contains(e.target as Node)) setMentorOpen(false);
      if (historyRef.current && !historyRef.current.contains(e.target as Node)) setHistoryOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [addOpen, mentorOpen, historyOpen]);

  const taken = useMemo(
    () => new Set([team?.hr?.id, ...(team?.participants || []).map((p) => p.id)].filter(Boolean) as number[]),
    [team],
  );

  // Строка «HR» есть всегда: у человека без воронок (в т.ч. уволенного — его
  // воронки закрыты) HR живёт на доске «Штат», и менять его можно отсюда же.
  if (!team) return null;

  const addParticipant = async (userId: number) => {
    setAddOpen(false);
    try {
      const next = await addEntityParticipant(entityId, userId);
      setTeam(next);
      onChanged?.();
    } catch (e) {
      toast.error(getErrorDetail(e, "Не удалось добавить участника"));
    }
  };
  const undoHr = async () => {
    setHistoryOpen(false);
    try {
      setTeam(await undoEntityHr(entityId));
      toast.success("Смена HR отменена");
      onChanged?.();
    } catch (e) {
      toast.error(getErrorDetail(e, "Не удалось отменить смену HR"));
    }
  };
  const pickMentor = async (name: string | null) => {
    setMentorOpen(false);
    try {
      setTeam(await setEntityMentor(entityId, name));
      onChanged?.();
    } catch (e) {
      toast.error(getErrorDetail(e, "Не удалось поставить ментора"));
    }
  };
  const removeParticipant = async (userId: number) => {
    try {
      setTeam(await removeEntityParticipant(entityId, userId));
      onChanged?.();
    } catch (e) {
      toast.error(getErrorDetail(e, "Не удалось снять участника"));
    }
  };

  return (
    <>
      <InfoRow label="HR">
        <div className="flex flex-wrap items-center gap-1.5">
          {team.hr ? (
            <span
              className={chip}
              title={team.hr_from_board ? "HR с доски «Штат» — кандидат не в воронке" : "HR кандидата во всех его воронках"}
            >
              {team.hr.name || "—"}
            </span>
          ) : (
            <span className="text-xs text-[var(--hf-main-500)]">{loaded ? "не назначен" : "…"}</span>
          )}
          {!readonly && (
            <button
              disabled={!loaded}
              type="button"
              className={ghostBtn}
              onClick={() => {
                void loadUsers();
                setChangeOpen(true);
              }}
            >
              Сменить
            </button>
          )}
          {/* История смен HR — здесь, а не в ленте: лента для взаимодействия с
              кандидатом (Маша, 17.11.2026). Отмена — только последней смены. */}
          {loaded && (team.hr_history?.length ?? 0) > 0 && (
            <div className="relative" ref={historyRef}>
              <button type="button" className={ghostBtn} onClick={() => setHistoryOpen((v) => !v)}>
                История
              </button>
              {historyOpen && (
                <div className="absolute left-0 top-full z-30 mt-1 w-72 rounded-xl border border-[color:var(--hf-main-200)] bg-[var(--hf-white)] p-2 shadow-lg hf-dark-disabled:bg-[var(--hf-dark-800)]">
                  <div className="grid gap-1.5">
                    {(team.hr_history || []).map((h, i) => (
                      <div key={i} className="text-xs leading-snug">
                        <span className="text-[var(--hf-main-500)]">
                          {h.at ? new Date(h.at.endsWith("Z") || h.at.includes("+") ? h.at : `${h.at}Z`).toLocaleString("ru", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : ""}
                          {h.by ? ` · ${h.by}` : ""}
                        </span>
                        <div className="text-[var(--hf-main-900)] hf-dark-disabled:text-[var(--hf-dark-200)]">
                          {h.prev ? `${h.prev} → ${h.new || "—"}` : `HR: ${h.new || "—"}`}
                        </div>
                      </div>
                    ))}
                  </div>
                  {!readonly && team.can_undo_hr && (
                    <button
                      type="button"
                      onClick={() => void undoHr()}
                      className="mt-2 w-full rounded-lg border border-[color:var(--hf-main-200)] px-2 py-1 text-xs font-medium hover:bg-[var(--hf-main-100)] hf-dark-disabled:hover:bg-[var(--hf-white-alpha-10)]"
                    >
                      Отменить последнюю смену
                    </button>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      </InfoRow>
      {loaded && team.in_funnels && (team.participants.length > 0 || !readonly) && (
        <InfoRow label="Участники">
          <div className="flex flex-wrap items-center gap-1.5">
            {team.participants.map((p) => (
              <span key={p.id} className={`group ${chip}`}>
                {p.name || "—"}
                {!readonly && (
                  <button
                    type="button"
                    title="Снять участника"
                    onClick={() => void removeParticipant(p.id)}
                    className="opacity-60 hover:opacity-100 hover:text-[var(--hf-status-red)]"
                  >
                    <X className="w-3 h-3" />
                  </button>
                )}
              </span>
            ))}
            {!readonly && (
              <div className="relative" ref={addRef}>
                <button
                  type="button"
                  className={ghostBtn}
                  title="Добавить участника — подключился к работе, но не HR"
                  onClick={() => {
                    void loadUsers();
                    setAddOpen((v) => !v);
                  }}
                >
                  <Plus className="w-3 h-3" />
                  {team.participants.length === 0 && "добавить"}
                </button>
                {addOpen && (
                  <div className="absolute left-0 top-full z-30 mt-1 max-h-64 w-56 overflow-auto rounded-xl border border-[color:var(--hf-main-200)] bg-[var(--hf-white)] p-1 shadow-lg hf-dark-disabled:bg-[var(--hf-dark-800)]">
                    {users.filter((u) => !taken.has(u.id)).length === 0 ? (
                      <div className="px-3 py-2 text-xs text-[var(--hf-main-500)]">Некого добавить</div>
                    ) : (
                      users
                        .filter((u) => !taken.has(u.id))
                        .map((u) => (
                          <button
                            key={u.id}
                            type="button"
                            onClick={() => void addParticipant(u.id)}
                            className="block w-full rounded-lg px-3 py-1.5 text-left text-sm hover:bg-[var(--hf-main-100)] hf-dark-disabled:hover:bg-[var(--hf-white-alpha-10)]"
                          >
                            {u.name}
                          </button>
                        ))
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        </InfoRow>
      )}
      {/* Ментор практики — тег у ФИО, он же «Рук. практики» на «Штате» (тикет
          Маши 13.11.2026: «указали ментора в карточке — сразу на борде»). */}
      {(showMentor || team.mentor) && (team.mentor || !readonly || !loaded) && (
        <InfoRow label="Ментор">
          <div className="flex flex-wrap items-center gap-1.5">
            {team.mentor && (
              <span className={`group ${chip}`} title="Он же в колонке «Рук. практики» на «Штате»">
                {team.mentor}
                {!readonly && (
                  <button
                    type="button"
                    title="Снять ментора"
                    onClick={() => void pickMentor(null)}
                    className="opacity-60 hover:opacity-100 hover:text-[var(--hf-status-red)]"
                  >
                    <X className="w-3 h-3" />
                  </button>
                )}
              </span>
            )}
            {!loaded && team.mentor === undefined && (
              <span className="text-xs text-[var(--hf-main-400)]">…</span>
            )}
            {!readonly && loaded && (
              <div className="relative" ref={mentorRef}>
                <button type="button" className={ghostBtn} onClick={() => setMentorOpen((v) => !v)}>
                  {team.mentor ? "Сменить" : "выбрать"}
                </button>
                {mentorOpen && (
                  <div className="absolute left-0 top-full z-30 mt-1 max-h-64 w-48 overflow-auto rounded-xl border border-[color:var(--hf-main-200)] bg-[var(--hf-white)] p-1 shadow-lg hf-dark-disabled:bg-[var(--hf-dark-800)]">
                    {(team.mentor_options || [])
                      .filter((n) => n !== team.mentor)
                      .map((n) => (
                        <button
                          key={n}
                          type="button"
                          onClick={() => void pickMentor(n)}
                          className="block w-full rounded-lg px-3 py-1.5 text-left text-sm hover:bg-[var(--hf-main-100)] hf-dark-disabled:hover:bg-[var(--hf-white-alpha-10)]"
                        >
                          {n}
                        </button>
                      ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </InfoRow>
      )}
      {changeOpen && (
        <ChangeHrModal
          team={team}
          users={users}
          onCancel={() => setChangeOpen(false)}
          onDone={(next, sourcer) => {
            setChangeOpen(false);
            setTeam(next);
            toast.success(sourcer ? `HR сменён. ${sourcer} — сорсер` : "HR сменён");
            onChanged?.();
          }}
          entityId={entityId}
        />
      )}
    </>
  );
}

function ChangeHrModal({
  entityId,
  team,
  users,
  onCancel,
  onDone,
}: {
  entityId: number;
  team: EntityTeam;
  users: AssignableUser[];
  onCancel: () => void;
  onDone: (team: EntityTeam, sourcer: string | null) => void;
}) {
  const options = users.filter((u) => u.id !== team.hr?.id);
  const [userId, setUserId] = useState<number | "">("");
  const [keep, setKeep] = useState(false);
  const [busy, setBusy] = useState(false);
  const prevName = team.hr?.name || null;
  const sourcerNote = !prevName
    ? null
    : team.sourcers.length
      ? `Сорсер остаётся: ${team.sourcers.map((s) => s.name).join(", ")}.`
      : `${prevName} станет сорсером.`;

  const submit = async () => {
    if (userId === "") return;
    setBusy(true);
    try {
      const res = await setEntityHr(entityId, userId, keep);
      onDone(res.team, res.sourcer);
    } catch (e) {
      toast.error(getErrorDetail(e, "Не удалось сменить HR"));
      setBusy(false);
    }
  };

  return createPortal(
    <div
      className="hf-confirm-modal-backdrop"
      style={{ zIndex: 60 }}
      onClick={() => !busy && onCancel()}
      onKeyDown={(e) => e.key === "Escape" && !busy && onCancel()}
    >
      <div role="dialog" aria-modal="true" className="hf-confirm-modal" onClick={(e) => e.stopPropagation()}>
        <div className="grid gap-3">
          <h3 className="hf-confirm-modal-title">Сменить HR</h3>
          <p className="hf-confirm-modal-subtitle">
            {team.in_funnels
              ? "HR кандидата во всех его воронках. Этапы, комментарии и интервью остаются как есть."
              : "Кандидат не в воронке — HR меняется на доске «Штат»."}
          </p>
          <select
            value={userId}
            onChange={(e) => setUserId(e.target.value ? Number(e.target.value) : "")}
            className="h-10 w-full rounded-lg border border-[color:var(--hf-main-200)] bg-[var(--hf-white)] px-3 text-sm hf-dark-disabled:bg-[var(--hf-dark-800)]"
            autoFocus
          >
            <option value="">Кого сделать HR…</option>
            {options.map((u) => (
              <option key={u.id} value={u.id}>
                {u.name}
              </option>
            ))}
          </select>
          {prevName && team.in_funnels && (
            <label className="flex items-start gap-2 text-sm">
              <input type="checkbox" checked={keep} onChange={(e) => setKeep(e.target.checked)} className="mt-0.5" />
              <span>Оставить {prevName} участником</span>
            </label>
          )}
          {sourcerNote && <p className="text-xs text-[var(--hf-main-600)]">{sourcerNote}</p>}
        </div>
        <div className="hf-confirm-modal-actions">
          <button type="button" onClick={onCancel} disabled={busy} className="hf-confirm-modal-cancel">
            Отмена
          </button>
          <button
            type="button"
            onClick={() => void submit()}
            disabled={busy || userId === ""}
            className="hf-confirm-modal-submit hf-confirm-modal-submit-warning whitespace-nowrap"
          >
            {busy ? "Подождите…" : "Сменить"}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
