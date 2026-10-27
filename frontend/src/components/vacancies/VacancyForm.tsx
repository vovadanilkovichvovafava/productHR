import { useState, useEffect, useMemo, useRef } from 'react';
import { motion } from 'framer-motion';
import clsx from 'clsx';
import {
  Loader2,
  PlayCircle,
} from 'lucide-react';
import toast from 'react-hot-toast';
import { useVacancyStore } from '@/stores/vacancyStore';
import { useAuthStore } from '@/stores/authStore';
import type { Vacancy, VacancyStatus } from '@/types';
import { getAssignableUsers, assignVacancy, takeVacancy, declineVacancy } from '@/services/api';
import type { AssignableUser } from '@/services/api';
import { getBoardDepartments } from '@/services/api/staffBoard';
import type { BoardDepartment } from '@/services/api/staffBoard';
import { getCurrencySymbol, SALARY_INPUT_CURRENCIES } from '@/utils/currency';
import {
  RichTextField, DeadlinePicker, HfSelect,
  HuntflowClose28Icon, HuntflowEyeOffIcon, HuntflowFlagIcon,
} from './vacancyFormParts';
import { apiErrorDetail, buildVacancyPayload, validateVacancyForm } from './vacancyFormPayload';
import VacancyConfirmModal, { type VacancyConfirmAction } from './VacancyConfirmModal';
import { isVacancyParticipant, hasPersonallyAccepted, isExplicitlyAssigned, getVacancyExitOptions } from '@/utils/vacancy';
import { backdropClose } from '@/utils/backdropClose';

interface VacancyFormProps {
  vacancy?: Vacancy;
  prefillData?: Partial<Vacancy>;
  onClose: () => void;
  onSuccess: () => void;
}

export default function VacancyForm({ vacancy, prefillData, onClose, onSuccess }: VacancyFormProps) {
  const { user } = useAuthStore();
  const { vacancies, fetchVacancies } = useVacancyStore();

  // Редактирование заявки (2026-07-09): бэкенд (can_edit_vacancy) уже давно
  // разрешает редактировать назначенному рекрутёру (assigned_to/assigned_to_all)
  // наравне с создателем — ограничение было чисто фронтовым и без причины строже
  // бэка. Теперь назначенный рекрутёр получает ту же полноценную форму, что и
  // создатель/админ. isReadOnlyRequest остаётся true только для теоретического
  // случая просмотра без прав редактирования вообще (например, узкая share-view
  // без edit) — на практике почти не встречается, раз форму вообще открыли.
  const isAdmin = user?.role === 'superadmin' || user?.org_role === 'owner' || user?.org_role === 'admin';
  const isMineByOwnership = !!(user && vacancy && (vacancy.created_by === user.id || vacancy.hiring_manager_id === user.id));
  const isAssignedToMe = !!(user && vacancy && (vacancy.assigned_to_all || (vacancy.assigned_to || []).includes(user.id)));
  // Админа, которого ЯВНО назначили, считаем участником наравне с рекрутёром:
  // он тоже может отказаться (2026-09-10).
  const isExplicitlyAssignedToMe = !!(user && vacancy && isExplicitlyAssigned(vacancy, user.id));
  // Наблюдатель (is_readonly) обычно сидит с правами админа, поэтому форма
  // открывалась ему полностью редактируемой: поля вводились, «Сохранить» молча
  // отбивал сервер. Для него форма — просмотр (01.10.2026).
  const isObserver = !!user?.is_readonly;
  const canEditVacancy = (isAdmin || isMineByOwnership || isAssignedToMe) && !isObserver;
  const isReadOnlyRequest = !!vacancy && !canEditVacancy;

  // Уже ли ЭТОТ юзер лично принял заявку (extra_data.accepted_by, 2026-07-08) —
  // воронка общая, но принятие личное. Не зависит от режима формы (read-only
  // vs редактируемая) — назначенный рекрутёр видит статус принятия в любом случае.
  const alreadyTaken = useMemo(() => {
    if (!isAssignedToMe || !vacancy || !user) return false;
    return hasPersonallyAccepted(vacancy, user.id);
  }, [vacancy, user, isAssignedToMe]);

  const [taking, setTaking] = useState(false);
  const [declining, setDeclining] = useState(false);
  // «Отказаться» — рекрутёр снимает себя с заявки (backend /decline), не удаляет.
  // «Выйти из вакансии» / «Закрыть вакансию» — две разные кнопки (2026-09-10),
  // см. getVacancyExitOptions. «Отказаться» — только для ещё не взятой заявки.
  const exitOptions = vacancy && user
    ? getVacancyExitOptions(vacancy, user.id, isAdmin)
    : { canLeave: false, canClose: true, others: [] as number[] };
  const showDecline = !alreadyTaken && (isAdmin ? isExplicitlyAssignedToMe : isAssignedToMe);
  const showLeave = exitOptions.canLeave && !showDecline;
  // Подтверждение «Выйти / Закрыть / Удалить» — окном сайта, не браузера.
  const [confirmAction, setConfirmAction] = useState<VacancyConfirmAction | null>(null);
  const handleLeave = async () => {
    if (!vacancy || declining) return;
    setDeclining(true);
    try {
      await declineVacancy(vacancy.id);
      toast.success('Вы вышли из вакансии — у остальных она осталась в работе');
      onSuccess();
      onClose();
    } catch {
      toast.error('Не удалось выйти из вакансии');
    } finally {
      setDeclining(false);
      setConfirmAction(null);
    }
  };
  const handleDecline = async () => {
    if (!vacancy || declining) return;
    setDeclining(true);
    try {
      await declineVacancy(vacancy.id);
      toast.success('Вы отказались от заявки');
      onSuccess();
    } catch {
      toast.error('Не удалось отказаться от заявки');
    } finally {
      setDeclining(false);
    }
  };
  const handleTake = async () => {
    if (!vacancy) return;
    setTaking(true);
    try {
      await takeVacancy(vacancy.id);
      toast.success('Заявка взята в работу — открыта в "Мои вакансии"');
      await fetchVacancies();
      onClose();
    } catch {
      toast.error('Не удалось взять заявку');
    } finally {
      setTaking(false);
    }
  };

  const { createVacancy, updateVacancy, deleteVacancy } = useVacancyStore();
  const [loading, setLoading] = useState(false);
  const [users, setUsers] = useState<AssignableUser[]>([]);

  // Use prefillData when creating new vacancy, vacancy when editing
  const initialData = vacancy || prefillData;

  const [formData, setFormData] = useState({
    title: initialData?.title || '',
    description: initialData?.description || '',
    requirements: initialData?.requirements || '',
    responsibilities: initialData?.responsibilities || '',
    salary_min: initialData?.salary_min || '',
    salary_max: initialData?.salary_max || '',
    salary_currency: initialData?.salary_currency || 'RUB',
    location: initialData?.location || '',
    employment_type: initialData?.employment_type || '',
    experience_level: initialData?.experience_level || '',
    status: vacancy?.status || 'pending_review' as VacancyStatus,
    priority: vacancy?.priority || 0,
    tags: initialData?.tags?.join(', ') || '',
    visible_to_all: vacancy?.visible_to_all ?? initialData?.visible_to_all ?? true,
    closes_at: vacancy?.closes_at || '',
  });

  const [selectedRecruiters, setSelectedRecruiters] = useState<number[]>(vacancy?.assigned_to || []);
  const [assignAll, setAssignAll] = useState(vacancy?.assigned_to_all ?? false);
  const [showRecruiterDD, setShowRecruiterDD] = useState(false);

  // Заказчик — ТОЛЬКО свободный текст (решение 2026-07-02): пользователей
  // системы (рекрутёров и остальных) в подсказках НЕТ. Значения приходят из
  // ручного ввода и из бота («Влад — RND Facebook»: имя отправителя + чат).
  // Легаси hiring_manager_name показываем как текст и при сохранении
  // конвертируем в customer_name (hiring_manager_id зануляется).
  const [customerText, setCustomerText] = useState(
    () => vacancy?.hiring_manager_name || String(vacancy?.extra_data?.customer_name || ''),
  );
  const [showCustomerDD, setShowCustomerDD] = useState(false);
  // Песочница воронки: куда человек попадёт на доске «Статусы», выйдя на
  // практику. Список берём с доски — это её справочник, а не оргструктура.
  const [sandboxId, setSandboxId] = useState<string>(
    () => (vacancy?.extra_data?.board_sandbox_id != null
      ? String(vacancy.extra_data.board_sandbox_id)
      : ''),
  );
  const [positionsCount, setPositionsCount] = useState<string>(() => {
    const n = vacancy?.extra_data?.positions_count ?? initialData?.extra_data?.positions_count;
    return typeof n === 'number' && n >= 1 ? String(n) : '1';
  });
  const [sandboxes, setSandboxes] = useState<BoardDepartment[]>([]);
  useEffect(() => {
    getBoardDepartments()
      .then((list) => setSandboxes(list.filter((d) => d.kind === 'sandbox' && !d.hidden)))
      .catch(() => setSandboxes([]));
  }, []);
  const customerRef = useRef<HTMLDivElement>(null);

  // Ранее введённые заказчики — собираем по всем вакансиям орга
  // (extra_data.customer_name), включая созданных ботом.
  const pastCustomerNames = useMemo(() => {
    const names = new Set<string>();
    vacancies.forEach((v) => {
      const n = (v.extra_data as Record<string, unknown> | undefined)?.customer_name;
      if (typeof n === 'string' && n.trim()) names.add(n.trim());
    });
    return Array.from(names);
  }, [vacancies]);

  const customerSuggestions = useMemo(() => {
    const q = customerText.trim().toLowerCase();
    return pastCustomerNames
      .filter((n) => !q || n.toLowerCase().includes(q))
      .map((n) => ({ id: n, label: n }));
  }, [customerText, pastCustomerNames]);

  const customerExactMatch = customerSuggestions.some(
    (o) => o.label.toLowerCase() === customerText.trim().toLowerCase(),
  );
  const canAddCustomerText = customerText.trim().length > 0 && !customerExactMatch;

  const selectCustomerFreeText = (name: string) => {
    setCustomerText(name);
    setShowCustomerDD(false);
  };

  useEffect(() => {
    getAssignableUsers()
      .then((list) => {
        // Себя в списке «Добавить» не показываем — текущий юзер уже назначен ("Я").
        const others = list.filter((u) => u.id !== user?.id);
        setUsers(others);
        // Если заявка была назначена «всем» — визуально отмечаем всех рекрутёров.
        if (vacancy?.assigned_to_all) setSelectedRecruiters(others.map((u) => u.id));
      })
      .catch((err) => console.error('Failed to load assignable users:', err));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!showCustomerDD) return;
    const closeCustomerDD = (event: PointerEvent) => {
      const target = event.target as Node | null;
      if (target && !customerRef.current?.contains(target)) setShowCustomerDD(false);
    };
    document.addEventListener('pointerdown', closeCustomerDD);
    return () => document.removeEventListener('pointerdown', closeCustomerDD);
  }, [showCustomerDD]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isReadOnlyRequest) return;
    const invalid = validateVacancyForm({ ...formData, positionsCount });
    if (invalid) {
      toast.error(invalid);
      return;
    }

    setLoading(true);
    try {
      const data = buildVacancyPayload(formData, { vacancy, customerText, sandboxId, positionsCount });

      if (vacancy) {
        await updateVacancy(vacancy.id, data);
        // Save recruiter assignments
        await assignVacancy(vacancy.id, selectedRecruiters, assignAll);
        toast.success('Вакансия обновлена');
      } else {
        const created = await createVacancy(data);
        // Save recruiter assignments for new vacancy
        if (selectedRecruiters.length > 0 || assignAll) {
          await assignVacancy(created.id, selectedRecruiters, assignAll);
        }
        toast.success('Вакансия создана');
      }
      onSuccess();
    } catch (error) {
      toast.error(apiErrorDetail(error, vacancy ? 'Ошибка при обновлении' : 'Ошибка при создании'));
    } finally {
      setLoading(false);
    }
  };

  // Действия над существующей вакансией: закрыть / в архив / удалить.
  const [statusAction, setStatusAction] = useState(false);
  const runStatusAction = async (status: VacancyStatus, msg: string) => {
    if (!vacancy) return;
    setStatusAction(true);
    try {
      await updateVacancy(vacancy.id, { status });
      toast.success(msg);
      onSuccess();
      onClose();
    } catch (_) {
      toast.error('Не удалось изменить статус вакансии');
    } finally {
      setStatusAction(false);
      setConfirmAction(null);
    }
  };
  // Удаление доступно ТОЛЬКО суперадмину (возврат кнопки 2026-07-02);
  // жизненный цикл у остальных ролей закрывается «Закрыть вакансию».
  const handleDeleteVacancy = async () => {
    if (!vacancy) return;
    setStatusAction(true);
    try {
      await deleteVacancy(vacancy.id);
      toast.success('Вакансия удалена');
      onSuccess();
      onClose();
    } catch (_) {
      toast.error('Не удалось удалить вакансию');
    } finally {
      setStatusAction(false);
      setConfirmAction(null);
    }
  };
  const runConfirmedAction = () => {
    if (confirmAction === 'leave') handleLeave();
    else if (confirmAction === 'close') runStatusAction('closed', 'Вакансия закрыта');
    else if (confirmAction === 'delete') handleDeleteVacancy();
  };
  const hfLabelClass = "hf-vacancy-label";
  const hfInputClass = "hf-vacancy-input";

  // markdown applyEditorFormat удалён — теперь WYSIWYG (см. RichTextField выше).

  const renderEditor = (
    value: string,
    onChange: (value: string) => void,
  ) => (
    <RichTextField value={value} onChange={onChange} disabled={isReadOnlyRequest} />
  );

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="hf-vacancy-modal-overlay font-hf-body"
      // Не onClick={onClose}: выделение текста с отпусканием мыши за краем окна
      // закрывало форму вместе с набранным (жалоба 24.09.2026, см. backdropClose).
      {...backdropClose(onClose)}
    >
      <motion.div
        initial={{ scale: 0.95, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        exit={{ scale: 0.95, opacity: 0 }}
        onClick={(e) => e.stopPropagation()}
        className="hf-vacancy-modal"
      >
        <div className="hf-vacancy-modal-header">
          <h2 className="hf-vacancy-modal-title">
            {isReadOnlyRequest ? 'Заявка' : (vacancy ? 'Редактировать заявку' : 'Новая заявка')}
          </h2>
          <div className="hf-vacancy-header-actions">
          <button
            onClick={onClose}
              className="hf-vacancy-close-btn"
          >
              <HuntflowClose28Icon className="hf-vacancy-close-icon" />
          </button>
          </div>
        </div>

        <form
          id="vacancy-form"
          onSubmit={handleSubmit}
          className="hf-vacancy-form-scroll"
        >
          <div className="hf-vacancy-modal-grid grid min-h-full">
            <div className="hf-vacancy-modal-main grid">
              <div>
                <label className={hfLabelClass}>Должность</label>
                <input
                  type="text"
                  value={formData.title}
                  onChange={(e) => setFormData({ ...formData, title: e.target.value })}
                  disabled={isReadOnlyRequest}
                  className={hfInputClass}
                />
              </div>

              <div>
                <label className={hfLabelClass}>Зарплата</label>
                <div style={{ display: 'flex', gap: 8, alignItems: 'stretch' }}>
                  {/* Сумма с авто-подстановкой символа выбранной валюты (₽/$). */}
                  <div style={{ position: 'relative', flex: 1 }}>
                    <span
                      style={{
                        position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)',
                        color: 'var(--hf-main-500)', fontSize: 14, pointerEvents: 'none',
                      }}
                    >
                      {getCurrencySymbol(formData.salary_currency)}
                    </span>
                    <input
                      type="number"
                      min={0}
                      value={formData.salary_min || formData.salary_max}
                      onChange={(e) => setFormData({ ...formData, salary_min: e.target.value, salary_max: e.target.value })}
                      disabled={isReadOnlyRequest}
                      className="hf-vacancy-input hf-vacancy-salary-input"
                      style={{ paddingLeft: 26 }}
                    />
                  </div>
                  {/* Валюта — только рубль или доллар. */}
                  <div style={{ width: 150, flexShrink: 0 }}>
                    <HfSelect
                      value={formData.salary_currency}
                      options={SALARY_INPUT_CURRENCIES}
                      onChange={(value) => setFormData({ ...formData, salary_currency: String(value) })}
                      disabled={isReadOnlyRequest}
                    />
                  </div>
                </div>
              </div>

              <div>
                <label className={hfLabelClass}>Описание вакансии</label>
                {renderEditor(
                  formData.description,
                  (value) => setFormData({ ...formData, description: value }),
                )}
              </div>

              <div>
                <label className={hfLabelClass}>Обязанности</label>
                {renderEditor(
                  formData.responsibilities,
                  (value) => setFormData({ ...formData, responsibilities: value }),
                )}
              </div>

              <div>
                <label className={hfLabelClass}>Требования</label>
                {renderEditor(
                  formData.requirements,
                  (value) => setFormData({ ...formData, requirements: value }),
                )}
              </div>
            </div>

            <aside className="hf-vacancy-modal-aside">
              {!isReadOnlyRequest && isAdmin && (
                <div className="hf-vacancy-recruiters">
                  <label className={hfLabelClass}>Назначенные рекрутеры</label>
                  {/* Показываем РЕАЛЬНО назначенных (assigned_to), а не хардкод «Я».
                      Раньше всегда висело «Я, {юзер}», даже если он не назначен. */}
                  {(() => {
                    if (assignAll) {
                      return (
                        <div className="hf-vacancy-recruiter-row">
                          <span className="hf-vacancy-avatar">∀</span>
                          <span className="truncate">Все рекрутёры</span>
                        </div>
                      );
                    }
                    const rows: { id: number; isMe: boolean; name: string }[] = [];
                    for (const id of selectedRecruiters) {
                      const isMe = id === user?.id;
                      const name = isMe
                        ? `Я, ${user?.name || user?.email || "Профиль"}`
                        : (users.find((x) => x.id === id)?.name || "");
                      if (name) rows.push({ id, isMe, name });
                    }
                    if (rows.length === 0) {
                      return (
                        <div className="hf-vacancy-recruiter-row">
                          <span className="truncate text-[var(--hf-main-500)]">Пока никто не назначен</span>
                        </div>
                      );
                    }
                    return rows.map((r) => (
                      <div key={r.id} className="hf-vacancy-recruiter-row">
                        <span className="hf-vacancy-avatar">{r.isMe ? "Я" : (r.name[0] || "?")}</span>
                        <span className="truncate">{r.name}</span>
                      </div>
                    ));
                  })()}
                  <button
                    type="button"
                    onClick={() => setShowRecruiterDD(!showRecruiterDD)}
                    className="hf-vacancy-side-link hf-vacancy-recruiter-add"
                  >
                    + Добавить
                  </button>
                  {showRecruiterDD && (
                    <div className="hf-vacancy-dropdown">
                      <button
                        type="button"
                        onClick={() => {
                          // «Всем рекрутёрам» — отдельный флаг (assigned_to_all), а НЕ
                          // производная от «отметили всех текущих людей в списке».
                          // Раньше выбор ДВУХ конкретных людей, которые случайно
                          // составляли весь список assignable-users, молча превращался
                          // в assigned_to_all=true — заявка становилась видна вообще
                          // всем рекрутёрам орга (и будущим), а не только этим двоим.
                          setAssignAll(!assignAll);
                          setSelectedRecruiters([]);
                        }}
                        className="hf-vacancy-dropdown-item"
                      >
                        <span className={clsx("hf-vacancy-dropdown-check", assignAll && "hf-vacancy-dropdown-check-active")} />
                        Всем рекрутерам
                      </button>
                      {users.map((u) => {
                        // При «Всем рекрутёрам» визуально отмечаем каждого — они все
                        // покрыты флагом assigned_to_all. Данные при этом не меняются:
                        // individual selectedRecruiters остаётся пустым, это чисто
                        // отображение (клик по конкретному человеку всё равно снимет
                        // assignAll и переключит на явный список — см. onClick ниже).
                        const isSelected = assignAll || selectedRecruiters.includes(u.id);
                        return (
                          <button
                            key={u.id}
                            type="button"
                            onClick={() => {
                              // Клик по конкретному человеку всегда означает «именно
                              // эти люди», а не «все» — снимаем assignAll, если был включён.
                              const base = assignAll ? [] : selectedRecruiters;
                              const next = base.includes(u.id)
                                ? base.filter(id => id !== u.id)
                                : [...base, u.id];
                              setAssignAll(false);
                              setSelectedRecruiters(next);
                            }}
                            className="hf-vacancy-dropdown-item"
                          >
                            <span className={clsx("hf-vacancy-dropdown-check", isSelected && "hf-vacancy-dropdown-check-active")} />
                            <span className="truncate">{u.name}</span>
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}

              <div className="hf-vacancy-side-stack">
                <div className="hf-vacancy-side-section">
                  <label className="hf-vacancy-side-title">Сколько человек нужно нанять</label>
                  {/* Сколько человек нужно — extra_data.positions_count (его же пишет бот
                      «нужно 3 таргетолога» и показывает предпросмотр заявки). Раньше
                      поле было пустышкой: всегда «1» и не сохранялось (20.10.2026). */}
                  <input
                    type="number"
                    min={1}
                    className={hfInputClass}
                    value={positionsCount}
                    onChange={(e) => setPositionsCount(e.target.value)}
                    disabled={isReadOnlyRequest}
                  />
                </div>
                <div>
                  <label className={hfLabelClass}>Дедлайн</label>
                  <DeadlinePicker
                    value={formData.closes_at}
                    onChange={(value) => setFormData({ ...formData, closes_at: value })}
                    disabled={isReadOnlyRequest}
                  />
                </div>
                <div ref={customerRef}>
                  <label className={hfLabelClass}>Заказчик</label>
                  <input
                    type="text"
                    value={customerText}
                    onChange={(e) => {
                      setCustomerText(e.target.value);
                      setShowCustomerDD(true);
                    }}
                    onFocus={() => setShowCustomerDD(true)}
                    placeholder="Например: Влад — RND Facebook"
                    disabled={isReadOnlyRequest}
                    className="hf-vacancy-input"
                  />
                  {showCustomerDD && !isReadOnlyRequest && (
                    <div className="hf-vacancy-dropdown">
                      <button
                        type="button"
                        onClick={() => selectCustomerFreeText('')}
                        className="hf-vacancy-dropdown-item"
                      >
                        <span className="truncate text-[var(--hf-main-600)]">Не указан</span>
                      </button>
                      {customerSuggestions.map((o) => (
                        <button
                          type="button"
                          key={o.id}
                          onClick={() => selectCustomerFreeText(o.label)}
                          className="hf-vacancy-dropdown-item"
                        >
                          <span className="truncate">{o.label}</span>
                        </button>
                      ))}
                      {canAddCustomerText && (
                        <button
                          type="button"
                          onClick={() => selectCustomerFreeText(customerText.trim())}
                          className="hf-vacancy-dropdown-item"
                        >
                          <span className="truncate text-[var(--hf-cyan-700)]">
                            + Добавить «{customerText.trim()}»
                          </span>
                        </button>
                      )}
                    </div>
                  )}
                </div>
                <div>
                  <label className={hfLabelClass}>Видимость</label>
                  <HfSelect
                    value={formData.visible_to_all ? "all" : "private"}
                    options={[
                      { value: "all", label: "Видна коллегам" },
                      { value: "private", label: "Скрыта от коллег", icon: <HuntflowEyeOffIcon className="hf-vacancy-select-icon-svg" /> },
                    ]}
                    onChange={(value) => setFormData({ ...formData, visible_to_all: value === "all" })}
                  />
                </div>
                <div>
                  {/* Куда человек попадает, выйдя на практику. Песочниц
                      несколько (SANDBOX, SANDBOX MOBILE, SANDBOX R&D), угадать
                      нельзя — поэтому её выбирают у воронки (Мария,
                      30.09.2026). Не выбрана — человек появится на доске
                      «Статусы» без отдела, и песочницу укажут руками. */}
                  <label className={hfLabelClass}>Песочница на практике</label>
                  <HfSelect
                    value={sandboxId}
                    options={[
                      {
                        value: "",
                        // Пусто — сработает песочница организации «по умолчанию»;
                        // её и показываем, чтобы было видно, куда попадёт человек.
                        label: sandboxes.find((d) => d.is_default)
                          ? `По умолчанию: ${sandboxes.find((d) => d.is_default)!.name}`
                          : "Спросить потом",
                      },
                      ...sandboxes.map((d) => ({ value: String(d.id), label: d.name })),
                    ]}
                    onChange={(value) => setSandboxId(String(value))}
                    disabled={isReadOnlyRequest}
                  />
                </div>
                <div>
                  <label className={hfLabelClass}>Приоритет</label>
                  <HfSelect
                    value={formData.priority}
                    options={[
                      { value: 0, label: "Обычный" },
                      { value: 1, label: "Высокий", icon: <HuntflowFlagIcon className="hf-vacancy-select-icon-svg hf-vacancy-select-icon-danger" /> },
                    ]}
                    onChange={(value) => setFormData({ ...formData, priority: parseInt(value) })}
                    disabled={isReadOnlyRequest}
                  />
                </div>
                {vacancy && !isReadOnlyRequest && (
                  <div className="mt-[var(--hf-space-l)] pt-[var(--hf-space-l)] border-t border-[var(--hf-ui-border)] flex flex-col gap-[8px]">
                    <span className={hfLabelClass}>Действия с вакансией</span>
                    {/* Личное принятие (2026-07-08): назначенный рекрутёр, ещё не
                        нажимавший «Взять в работу», видит это тут — раньше кнопка
                        была только в read-only виде заявки, но теперь форма для
                        назначенных полноценно редактируемая, и без этой кнопки
                        принять заявку было бы негде. */}
                    {isAssignedToMe && !alreadyTaken && (
                      <button
                        type="button"
                        onClick={handleTake}
                        disabled={taking}
                        className="w-full h-[36px] rounded-[8px] border border-[var(--hf-ui-border)] text-[13px] font-medium text-[var(--hf-main-800)] transition-colors hover:bg-[var(--hf-ui-hover)] disabled:opacity-50 flex items-center justify-center gap-1.5"
                      >
                        {taking ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <PlayCircle className="w-3.5 h-3.5" />}
                        {taking ? 'Беру...' : 'Взять в работу'}
                      </button>
                    )}
                    {vacancy.status === 'closed' ? (
                      <button
                        type="button"
                        onClick={() => runStatusAction('open', 'Вакансия открыта заново')}
                        disabled={statusAction}
                        className="w-full h-[36px] rounded-[8px] border border-[var(--hf-ui-border)] text-[13px] font-medium text-[var(--hf-main-800)] transition-colors hover:bg-[var(--hf-ui-hover)] disabled:opacity-50"
                      >
                        Открыть вакансию
                      </button>
                    ) : exitOptions.canClose && (
                      <button
                        type="button"
                        onClick={() => setConfirmAction('close')}
                        disabled={statusAction}
                        className="w-full h-[36px] rounded-[8px] border border-[var(--hf-ui-border)] text-[13px] font-medium text-[var(--hf-main-800)] transition-colors hover:bg-[var(--hf-ui-hover)] disabled:opacity-50"
                      >
                        Закрыть вакансию
                      </button>
                    )}
                    {showLeave && vacancy.status !== 'closed' && (
                      <button
                        type="button"
                        onClick={() => setConfirmAction('leave')}
                        disabled={declining}
                        className="w-full h-[36px] rounded-[8px] border border-[var(--hf-ui-border)] text-[13px] font-medium text-[var(--hf-main-800)] transition-colors hover:bg-[var(--hf-ui-hover)] disabled:opacity-50"
                      >
                        {declining ? 'Выходим…' : 'Выйти из вакансии'}
                      </button>
                    )}
                    {showDecline && (
                      <button
                        type="button"
                        onClick={handleDecline}
                        disabled={declining}
                        className="w-full h-[36px] rounded-[8px] border border-[var(--hf-status-red-badge)] text-[13px] font-medium text-[var(--hf-status-red)] transition-colors hover:bg-[var(--hf-status-red-badge)] disabled:opacity-50"
                      >
                        {declining ? 'Отказ...' : 'Отказаться'}
                      </button>
                    )}
                    {/* «Удалить вакансию» доступна рекрутёрам-УЧАСТНИКАМ воронки
                        (по запросу юзера 2026-08-04, разворот прежнего admin-only от
                        3eab9bda) и админам орга. Удаление мягкое (deleted_at →
                        «Удалённые», восстановимо) и настоящее: в общей воронке сносит
                        вакансию у ВСЕХ участников — поэтому постороннему рекрутёру её
                        не показываем. Раньше кнопка висела у всех, но чужую воронку
                        было и не открыть; с 2026-09-07 просмотр открыт всему
                        HR-сегменту, и без этого гейта кнопка «Удалить» появилась бы
                        на каждой чужой воронке (бэк отвечает 403, см.
                        can_delete_vacancy). «Отказаться» (уйти у себя) остаётся
                        отдельной кнопкой рядом для тех, кому нужен именно выход. */}
                    {(isAdmin || isVacancyParticipant(vacancy, user?.id)) && (
                      <button
                        type="button"
                        onClick={() => setConfirmAction('delete')}
                        disabled={statusAction}
                        className="w-full h-[36px] rounded-[8px] border border-[var(--hf-status-red-badge)] text-[13px] font-medium text-[var(--hf-status-red)] transition-colors hover:bg-[var(--hf-status-red-badge)] disabled:opacity-50"
                      >
                        Удалить вакансию
                      </button>
                    )}
                  </div>
                )}
              </div>
            </aside>
          </div>
        </form>

        <div className="hf-vacancy-footer">
          {isReadOnlyRequest ? (
            <>
              <button
                type="button"
                onClick={onClose}
                className="hf-vacancy-secondary-btn"
              >
                Закрыть
              </button>
              {!alreadyTaken && !isObserver && (
              <button
                onClick={handleTake}
                disabled={taking}
                  className="hf-vacancy-primary-btn"
              >
                  {taking ? <Loader2 className="hf-vacancy-button-icon animate-spin" /> : <PlayCircle className="hf-vacancy-button-icon" />}
                {taking ? 'Беру...' : 'Взять в работу'}
              </button>
              )}
              {!isObserver && (
              <button
                type="button"
                onClick={handleDecline}
                disabled={declining}
                className="hf-vacancy-secondary-btn"
                style={{ color: 'var(--hf-status-red)', borderColor: 'var(--hf-status-red)' }}
              >
                {declining ? 'Отказ...' : 'Отказаться'}
              </button>
              )}
            </>
          ) : (
            <>
              <button
                type="submit"
                form="vacancy-form"
                disabled={loading}
                className="hf-vacancy-primary-btn"
              >
                {loading ? 'Сохранение...' : 'Сохранить'}
              </button>
              <button
                type="button"
                onClick={onClose}
                className="hf-vacancy-secondary-btn"
              >
                Отмена
              </button>
            </>
          )}
        </div>
        {vacancy && confirmAction && (
          <VacancyConfirmModal
            action={confirmAction}
            vacancy={vacancy}
            userId={user?.id}
            busy={declining || statusAction}
            onCancel={() => setConfirmAction(null)}
            onConfirm={runConfirmedAction}
          />
        )}
      </motion.div>
    </motion.div>
  );
}
