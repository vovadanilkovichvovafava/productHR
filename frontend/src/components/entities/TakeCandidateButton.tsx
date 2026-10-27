import { useState, useEffect, useMemo, useRef } from "react";
import { Grab, Loader2, ChevronDown, Check } from "lucide-react";
import clsx from "clsx";
import toast from "react-hot-toast";
import { getErrorDetail } from "@/utils";
import {
  getAllVacancies,
  getAssignableUsers,
  takeApplication,
  type AssignableUser,
} from "@/services/api/vacancies";
import { getEntityActivity, type VacancyActivityBlock } from "@/services/api/entities";
import { STAGE_LABEL_BY_STAGE } from "@/constants/hrStages";
import type { Vacancy } from "@/types";
import { isVacancyParticipant } from "@/utils/vacancy";
import { useAuthStore } from "@/stores/authStore";
import { usePriorRejectionGate } from "@/components/candidates/priorRejection";

/**
 * «Забрать» кандидата: сперва КОМУ (рекрутёр или админ, не наблюдатель), затем
 * В КАКУЮ воронку — только те, где выбранный работает (его воронки + общие).
 * Нет кандидата в воронке — добавится на «Новый»; есть у другого рекрутёра —
 * ПЕРЕЙДЁТ к выбранному с этапом и историей, прежний получит уведомление.
 * С 26.10.2026 окно заранее говорит, что из этого произойдёт (раньше одна
 * кнопка молча делала то одно, то другое). Имена в текстах — только в
 * именительном падеже: склонять их мы не умеем.
 *
 * Кнопку показываем ТОЛЬКО если кандидат уже в ≥1 воронке (забота вызывающего).
 */
export default function TakeCandidateButton({
  entityId,
  onDone,
}: {
  entityId: number;
  // Выбранная воронка + рекрутёр — вызывающему нужно, чтобы после «Забрать»
  // показать кандидата под НОВЫМ владельцем (иначе он выпадает из фильтра).
  onDone?: (result: { vacancyId: number; recruiterId: number }) => void;
}) {
  const { user } = useAuthStore();

  const [open, setOpen] = useState(false);
  const [vacancies, setVacancies] = useState<Vacancy[]>([]);
  const [recruiters, setRecruiters] = useState<AssignableUser[]>([]);
  const [recruiterId, setRecruiterId] = useState<number | "">("");
  const [vacancyId, setVacancyId] = useState<number | "">("");
  const [openMenu, setOpenMenu] = useState<null | "rec" | "vac">(null);
  const [saving, setSaving] = useState(false);
  // Где кандидат сейчас и кто его ведёт — чтобы сказать, что произойдёт.
  const [blocks, setBlocks] = useState<VacancyActivityBlock[]>([]);
  // Окно шириной 320 px: у правого края экрана открываем его влево, иначе
  // оно уезжало за край (узкое окно, планшет).
  const [alignRight, setAlignRight] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    // getAllVacancies уже скоуплен бэком под доступ текущего юзера — для не-админа
    // это его воронки, для админа — все. Дальше режем по выбранному рекрутёру.
    getAllVacancies({ status: "open" })
      .then((vs) => {
        if (!cancelled) setVacancies(vs);
      })
      .catch(() => toast.error("Не удалось загрузить воронки"));
    getAssignableUsers({ includeOwners: true })
      .then((us) => {
        if (!cancelled) setRecruiters(us);
      })
      .catch(() => { /* некритично */ });
    getEntityActivity(entityId)
      .then((bs) => {
        if (!cancelled) setBlocks(bs);
      })
      .catch(() => { /* без этого окно просто не предупредит */ });
    // По умолчанию — «я».
    setRecruiterId(user?.id ?? "");
    setVacancyId("");
    setOpenMenu(null);
    return () => {
      cancelled = true;
    };
  }, [open, user?.id, entityId]);

  // «Кому отдать»: assignable-users отдаёт только admin/hr из HR-отдела —
  // владельца/себя-вне-HR-отдела там нет, и «передать себе» было невозможно.
  // Гарантируем себя в списке (первым, с «(я)»); бэкенд «Забрать» пускает
  // owner/admin/hr, так что передача себе валидна.
  const recruiterOptions = useMemo<AssignableUser[]>(() => {
    if (!user?.id) return recruiters;
    if (recruiters.some((r) => r.id === user.id)) return recruiters;
    return [{ id: user.id, name: user.name || user.email }, ...recruiters];
  }, [recruiters, user?.id, user?.name, user?.email]);

  // Воронки ВЫБРАННОГО рекрутёра (где он участник: создатель/назначенный/общая).
  const funnelOptions = useMemo(() => {
    if (recruiterId === "") return [];
    return vacancies.filter((v) => isVacancyParticipant(v, Number(recruiterId)));
  }, [vacancies, recruiterId]);

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
        setOpenMenu(null);
      }
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  const pickRecruiter = (id: number) => {
    setRecruiterId(id);
    setVacancyId(""); // у другого рекрутёра — другие воронки
    setOpenMenu(null);
  };
  const pickVacancy = (id: number) => {
    setVacancyId(id);
    setOpenMenu(null);
  };

  const priorGate = usePriorRejectionGate();

  const isSelf = recruiterId !== "" && recruiterId === user?.id;
  const recipientName = recruiterOptions.find((r) => r.id === recruiterId)?.name || "";
  // Что произойдёт при нажатии: добавится / перейдёт / ничего.
  const current = vacancyId === "" ? undefined : blocks.find((b) => b.vacancy_id === vacancyId);
  const outcome: "added" | "transferred" | "unchanged" | null =
    vacancyId === "" || recruiterId === ""
      ? null
      : !current
        ? "added"
        : current.owner_id === recruiterId
          ? "unchanged"
          : "transferred";
  const stageName = current
    ? (STAGE_LABEL_BY_STAGE as Record<string, string>)[current.current_stage] || current.current_stage
    : "";

  const submit = async () => {
    if (!vacancyId || !recruiterId) {
      toast.error("Выберите, кому и в какую воронку");
      return;
    }
    // Был отказ — спросить, только когда кандидат заново попадает в воронку
    // (при смене рекрутёра он уже здесь, вопрос лишний).
    if (outcome === "added" && !(await priorGate.gate(entityId))) return;
    setSaving(true);
    try {
      const res = await takeApplication(Number(vacancyId), {
        entity_id: entityId,
        recruiter_id: Number(recruiterId),
      });
      const vt = vacancies.find((v) => v.id === vacancyId)?.title || "";
      const who = isSelf ? "вы" : recipientName;
      if (res.take_outcome === "transferred") {
        toast.success(isSelf ? "Готово. Кандидата теперь ведёте вы" : `Готово. Кандидата теперь ведёт: ${who}`);
      } else if (res.take_outcome === "unchanged") {
        toast(isSelf ? "Кандидат уже у вас, ничего не изменилось" : `Кандидат уже у этого рекрутёра: ${who}`);
      } else {
        toast.success(`Кандидат добавлен в воронку «${vt}»`);
      }
      setOpen(false);
      onDone?.({ vacancyId: Number(vacancyId), recruiterId: Number(recruiterId) });
    } catch (e) {
      toast.error(getErrorDetail(e, "Не удалось забрать"));
    } finally {
      setSaving(false);
    }
  };

  const recruiterName = recruiterOptions.find((r) => r.id === recruiterId)?.name;
  const vacancyTitle = funnelOptions.find((v) => v.id === vacancyId)?.title;

  const triggerCls =
    "flex w-full items-center justify-between gap-2 rounded-hf-s border border-[color:var(--hf-main-200)] hf-dark-disabled:border-[color:var(--hf-white-alpha-10)] bg-[var(--hf-white)] hf-dark-disabled:bg-[var(--hf-bg-dark)] px-3 py-2 text-left text-sm text-[var(--hf-main-900)] hf-dark-disabled:text-[var(--hf-white)] transition-colors hover:border-[color:var(--hf-main-400)] disabled:cursor-not-allowed disabled:opacity-50";
  const menuCls =
    "absolute top-full left-0 right-0 z-[70] mt-1 max-h-56 overflow-y-auto rounded-hf-s border border-[color:var(--hf-main-200)] hf-dark-disabled:border-[color:var(--hf-white-alpha-10)] bg-[var(--hf-white)] hf-dark-disabled:bg-[var(--hf-bg-dark)] py-1 shadow-[0_8px_24px_rgba(0,0,0,.14)]";
  const itemCls =
    "flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm text-[var(--hf-main-900)] hf-dark-disabled:text-[var(--hf-white)] transition-colors hover:bg-[var(--hf-ui-hover)] hf-dark-disabled:hover:bg-[var(--hf-white-alpha-06)]";
  const labelCls = "block text-[11px] text-[var(--hf-main-500)] mb-1";

  return (
    <div className="relative" ref={ref}>
      {priorGate.element}
      <button
        onClick={() => {
          const r = ref.current?.getBoundingClientRect();
          setAlignRight(!!r && r.left + 336 > window.innerWidth);
          setOpen((o) => !o);
        }}
        disabled={saving}
        className="hf-profile-action-btn disabled:opacity-50"
        title="Забрать кандидата: выбрать рекрутёра и воронку"
      >
        {saving ? (
          <Loader2 className="hf-profile-action-icon animate-spin" />
        ) : (
          <Grab className="hf-profile-action-icon" />
        )}
        Забрать
      </button>
      {open && (
        <div
          className={clsx(
            "hf-profile-vacancy-menu absolute top-full mt-1 w-80 max-w-[calc(100vw-24px)] z-50 p-3",
            alignRight ? "right-0" : "left-0",
          )}
          style={{ overflow: "visible" }}
        >
          <div className="mb-2 text-[13px] font-semibold text-[var(--hf-main-900)] hf-dark-disabled:text-[var(--hf-white)]">
            Забрать кандидата
          </div>

          {/* 1) Кому отдать */}
          <label className={labelCls}>Кому</label>
          <div className="relative mb-3">
            <button
              type="button"
              className={triggerCls}
              onClick={() => setOpenMenu((m) => (m === "rec" ? null : "rec"))}
            >
              <span className={clsx("truncate", !recruiterName && "text-[var(--hf-main-500)]")}>
                {recruiterName
                  ? `${recruiterName}${recruiterId === user?.id ? " (я)" : ""}`
                  : "Выберите…"}
              </span>
              <ChevronDown className="h-4 w-4 shrink-0 text-[var(--hf-main-500)]" />
            </button>
            {openMenu === "rec" && (
              <div className={menuCls}>
                {recruiterOptions.length === 0 ? (
                  <div className="px-3 py-2 text-sm text-[var(--hf-main-500)]">Нет рекрутёров</div>
                ) : (
                  recruiterOptions.map((r) => (
                    <button
                      key={r.id}
                      type="button"
                      className={clsx(itemCls, r.id === recruiterId && "bg-[var(--hf-bg-panel)] hf-dark-disabled:bg-[var(--hf-white-alpha-06)]")}
                      onClick={() => pickRecruiter(r.id)}
                    >
                      <span className="truncate">
                        {r.name}
                        {r.id === user?.id ? " (я)" : ""}
                      </span>
                      {r.id === recruiterId && (
                        <Check className="h-4 w-4 shrink-0 text-[var(--hf-status-green)]" />
                      )}
                    </button>
                  ))
                )}
              </div>
            )}
          </div>

          {/* 2) В какую воронку — только воронки выбранного рекрутёра */}
          <label className={labelCls}>В какую воронку</label>
          <div className="relative mb-3">
            <button
              type="button"
              disabled={recruiterId === ""}
              className={triggerCls}
              onClick={() => setOpenMenu((m) => (m === "vac" ? null : "vac"))}
            >
              <span className={clsx("truncate", !vacancyTitle && "text-[var(--hf-main-500)]")}>
                {vacancyTitle ||
                  (recruiterId === "" ? "Сначала выберите рекрутёра" : "Выберите…")}
              </span>
              <ChevronDown className="h-4 w-4 shrink-0 text-[var(--hf-main-500)]" />
            </button>
            {openMenu === "vac" && (
              <div className={menuCls}>
                {funnelOptions.length === 0 ? (
                  <div className="px-3 py-2 text-sm text-[var(--hf-main-500)]">
                    Нет воронок у этого рекрутёра
                  </div>
                ) : (
                  funnelOptions.map((v) => (
                    <button
                      key={v.id}
                      type="button"
                      className={clsx(itemCls, v.id === vacancyId && "bg-[var(--hf-bg-panel)] hf-dark-disabled:bg-[var(--hf-white-alpha-06)]")}
                      onClick={() => pickVacancy(v.id)}
                    >
                      <span className="truncate">{v.title}</span>
                      {v.id === vacancyId && (
                        <Check className="h-4 w-4 shrink-0 text-[var(--hf-status-green)]" />
                      )}
                    </button>
                  ))
                )}
              </div>
            )}
          </div>

          {outcome && (
            <div
              className={clsx(
                "mb-3 rounded-hf-s px-3 py-2 text-[12.5px] leading-snug",
                outcome === "transferred"
                  ? "bg-[var(--hf-status-yellow-bg)] text-[var(--hf-main-900)]"
                  : "bg-[var(--hf-bg-panel)] text-[var(--hf-main-700)] hf-dark-disabled:bg-[var(--hf-white-alpha-06)] hf-dark-disabled:text-[var(--hf-white-alpha-70)]",
              )}
              data-testid="take-outcome"
            >
              {outcome === "added" && (
                <>Кандидат появится в этой воронке на этапе «Новый». В других воронках всё останется как было.</>
              )}
              {outcome === "transferred" && (
                <>
                  Сейчас в этой воронке кандидата ведёт {current?.owner_name || "другой рекрутёр"}
                  {stageName ? `, этап «${stageName}»` : ""}.{" "}
                  {isSelf ? "Вести его будете вы" : `Вести его будет ${recipientName}`}, этап и история сохранятся.{" "}
                  {current?.owner_name || "Прежний рекрутёр"} получит уведомление.
                </>
              )}
              {outcome === "unchanged" && (
                <>{isSelf ? "Вы уже ведёте этого кандидата в этой воронке." : `${recipientName} уже ведёт этого кандидата в этой воронке.`}</>
              )}
            </div>
          )}

          <button
            onClick={submit}
            disabled={saving || !vacancyId || !recruiterId || outcome === "unchanged"}
            className="w-full rounded-hf-s py-2 text-sm font-semibold text-white disabled:opacity-50"
            style={{ background: "var(--hf-status-green)" }}
          >
            {saving ? "Секунду…" : isSelf ? "Забрать себе" : "Передать"}
          </button>
        </div>
      )}
    </div>
  );
}
