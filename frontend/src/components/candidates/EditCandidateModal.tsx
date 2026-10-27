import { useState, useMemo } from "react";
import type { ReactNode } from "react";

import { motion } from "framer-motion";
import { createPortal } from "react-dom";
import { Search } from "lucide-react";
import clsx from "clsx";
import toast from "react-hot-toast";

import { HfLoadingSpinner } from "@/components/ui/HfLoadingSpinner";

import { SALARY_INPUT_CURRENCIES } from "@/utils/currency";
import { calculateAge } from "@/utils/date";
import type { KanbanCard } from "@/services/api/candidates";
import { updateEntity, getEntityFiles, downloadEntityFile, deleteEntity } from "@/services/api/entities";
import DatePickerFactorial from "@/factorial/components/DatePickerFactorial";

import { backdropClose } from '@/utils/backdropClose';

import {
  HuntflowClose28Icon,
  HuntflowRemoveIcon,
  HuntflowClip18Icon,
  HuntflowXClose16Icon,
  HuntflowChevronDown24Icon,
} from "@/components/candidates/HuntflowIcons";
import {
  getInitials,
  formatResumeSaved,
  splitSalaryCurrency,
  joinSalaryCurrency,
  formatPhoneForEdit,
} from "@/components/candidates/candidateFormat";
import {
  normalizePhone,
  validateName,
  validatePhone,
  validateEmail,
  validateTelegram,
  validateFreeText,
  CANDIDATE_SOURCE_OPTIONS,
} from "@/components/candidates/candidateValidation";

// Окно «Редактировать кандидата» — общее для «Все кандидаты» и воронки
// (вынесено из AllCandidatesPage, 20.10.2026).

type EditResumeDemoData = {
  saved_at?: string;
  vacancy_title?: string;
  sections?: Array<{ title: string; lines?: string[] }>;
};

function buildEditResumeText(
  card: KanbanCard,
  resumeDemo?: EditResumeDemoData,
): string {
  if (!resumeDemo) return "";

  return [
    `Отклик на вакансию: «${resumeDemo.vacancy_title || card.vacancy_name || card.position || "Вакансия"}»`,
    resumeDemo.saved_at ? formatResumeSaved(resumeDemo.saved_at) : "",
    card.name,
    card.position,
    card.company,
    formatPhoneForEdit(card.phone),
    card.email,
    card.telegram_username ? `telegram: @${card.telegram_username.replace(/^@/, "")}` : "",
    card.city ? `Проживает: ${card.city}` : "",
    card.salary ? `Зарплатные ожидания: ${card.salary}` : "",
    ...(resumeDemo.sections || []).map(
      (section) => `${section.title}\n${(section.lines || []).join("\n")}`,
    ),
  ]
    .filter(Boolean)
    .join("\n\n");
}

export function EditCandidateModal({
  card,
  onClose,
  onSaved,
  onDeleted,
}: {
  card: KanbanCard;
  onClose: () => void;
  onSaved: (updated: Partial<KanbanCard>) => void;
  onDeleted: () => void;
}) {
  const initialNameParts = card.name.trim().split(/\s+/);
  const [lastName, setLastName] = useState(initialNameParts[0] || "");
  const [firstName, setFirstName] = useState(initialNameParts[1] || "");
  const [middleName, setMiddleName] = useState(
    initialNameParts.slice(2).join(" "),
  );
  const [phone, setPhone] = useState(formatPhoneForEdit(card.phone));
  const [email, setEmail] = useState(card.email || "");
  const [telegram, setTelegram] = useState(card.telegram_username || "");
  const [position, setPosition] = useState(card.position || "");
  const [company, setCompany] = useState(card.company || "");
  const [salary, setSalary] = useState(() => splitSalaryCurrency(card.salary || "").amount);
  const [salaryCurrency, setSalaryCurrency] = useState(() => splitSalaryCurrency(card.salary || "").currency);
  const [city, setCity] = useState((card.extra_data?.city as string) || "");
  const [skills, setSkills] = useState(
    Array.isArray(card.extra_data?.skills)
      ? (card.extra_data?.skills as string[]).join(", ")
      : "",
  );
  const [source, setSource] = useState(
    card.source || (card.extra_data?.source as string) || "",
  );
  const [sourceMenuOpen, setSourceMenuOpen] = useState(false);
  const [sourceSearch, setSourceSearch] = useState("");
  const [birthDate, setBirthDate] = useState(
    (card.extra_data?.birth_date as string | undefined) || "",
  );
  const resumeDemo = card.extra_data?.resume_demo as
    | EditResumeDemoData
    | undefined;
  // Сначала — текст, вписанный в «Текст резюме» (его показывает вкладка
  // «Резюме» с подписью «правится в „Редактировать“»). Раньше окно брало
  // только демо-резюме, и поле открывалось пустым (проверка прода 21.10.2026).
  const [resumeText, setResumeText] = useState(() => {
    const saved = card.extra_data?.resume_text;
    return typeof saved === "string" && saved.trim()
      ? saved
      : buildEditResumeText(card, resumeDemo);
  });
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [touched, setTouched] = useState<Record<string, boolean>>({});
  const fullName = [lastName, firstName, middleName]
    .map((part) => part.trim())
    .filter(Boolean)
    .join(" ");

  const errors = {
    name: validateName(fullName),
    phone: validatePhone(phone),
    email: validateEmail(email),
    telegram: validateTelegram(telegram),
    position: validateFreeText(position, 200),
    company: validateFreeText(company, 200),
  };
  const hasErrors = Object.values(errors).some((e) => e !== null);

  const markTouched = (field: string) =>
    setTouched((t) => ({ ...t, [field]: true }));

  const filteredSources = useMemo(() => {
    const needle = sourceSearch.trim().toLowerCase();
    if (!needle) return CANDIDATE_SOURCE_OPTIONS;
    return CANDIDATE_SOURCE_OPTIONS.filter((option) =>
      option.toLowerCase().includes(needle),
    );
  }, [sourceSearch]);

  const handleSave = async () => {
    setTouched({
      name: true,
      phone: true,
      email: true,
      telegram: true,
      position: true,
      company: true,
    });
    if (hasErrors) {
      toast.error("Исправьте ошибки в форме");
      return;
    }
    setSaving(true);
    try {
      const normalizedPhone = phone.trim() ? normalizePhone(phone) : undefined;
      const cleanTelegram = telegram.trim().replace(/^@/, "");
      const trimmedBirthDate = birthDate.trim();
      const extraData = {
        salary: joinSalaryCurrency(salary, salaryCurrency) || undefined,
        birth_date: trimmedBirthDate || undefined,
        // Возраст пересчитываем из точной даты рождения при каждом сохранении —
        // иначе (extra_data.age как отдельное несвязанное число) смена даты
        // рождения не двигала отображаемый возраст. Если дата не указана —
        // не трогаем age вообще (undefined выпадает при сериализации, PUT
        // мержит extra_data — старое значение от парсера hh.ru сохранится).
        age: trimmedBirthDate ? calculateAge(trimmedBirthDate) ?? undefined : undefined,
        resume_text: resumeText.trim() || undefined,
        source: source.trim() || undefined,
        city: city.trim() || undefined,
        skills: skills.split(",").map((s) => s.trim()).filter(Boolean),
      };
      const saved = await updateEntity(card.id, {
        name: fullName,
        phone: normalizedPhone,
        email: email.trim() || undefined,
        telegram_usernames: cleanTelegram ? [cleanTelegram] : undefined,
        position: position.trim() || undefined,
        company: company.trim() || undefined,
        extra_data: extraData,
        // Оптимистичная блокировка. Бэк умеет её с самого начала (PUT /entities
        // сверяет version и отдаёт 409), но фронт поле не слал — ветка не
        // выполнялась никогда, и два рекрутёра, открывшие карточку разом, тихо
        // затирали правки друг друга: побеждал тот, кто нажал «Сохранить»
        // последним. undefined (старая доска без поля) = прежнее поведение.
        version: card.version,
      });
      toast.success("Кандидат обновлён");
      onSaved({
        name: fullName,
        phone: normalizedPhone,
        email: email.trim() || undefined,
        telegram_username: cleanTelegram || undefined,
        position: position.trim() || undefined,
        company: company.trim() || undefined,
        // KanbanCard.salary/city — ОТДЕЛЬНЫЕ плоские поля (не читаются из
        // extra_data на фронте), backend их флэттенит из extra_data сам. Без
        // этого handleCardUpdated мержил только extra_data, а видимый
        // card.salary/card.city оставался старым до следующего fetchBoard() —
        // «работает только после обновления страницы».
        salary: extraData.salary,
        city: extraData.city,
        source: extraData.source,
        age: extraData.age != null ? String(extraData.age) : undefined,
        // extra_data — ЦЕЛИКОМ из ответа сервера: он смержил правку с остальным
        // (заметки, резюме) и пересчитал плашку дубля. Раньше сюда клали только
        // отредактированные поля, и плашка пропадала до перезагрузки страницы.
        extra_data: (saved?.extra_data as Record<string, unknown> | undefined) ?? {
          ...((card.extra_data || {}) as Record<string, unknown>),
          ...extraData,
        },
        // Свежая версия с сервера — иначе повторное «Сохранить» без перезагрузки
        // доски ушло бы со старой version и словило ложный 409.
        version: saved?.version,
      });
    } catch (err) {
      // 409 — карточку успел изменить кто-то ещё. Молчать тут нельзя: человек
      // видел бы «Ошибка сохранения» и не понимал, что его правки не потерялись,
      // а просто устарели и их надо перенести на свежую версию.
      const resp = (err as { response?: { status?: number } })?.response;
      toast.error(
        resp?.status === 409
          ? "Кандидата изменил кто-то ещё — обновите страницу и повторите правку"
          : "Ошибка сохранения",
      );
    } finally {
      setSaving(false);
    }
  };

  // Удаление — окном сайта, не браузера, и с правдой про корзину: кандидат
  // 7 дней хранится целиком, вернуть может админ (20.10.2026; до этого он
  // стирался насовсем, и «Действие необратимо» было правдой).
  const [confirmDelete, setConfirmDelete] = useState(false);
  const handleDelete = async () => {
    if (deleting) return;
    setDeleting(true);
    try {
      await deleteEntity(card.id);
      toast.success("Кандидат удалён — 7 дней его можно вернуть из корзины");
      setConfirmDelete(false);
      onDeleted();
    } catch {
      toast.error("Ошибка при удалении");
    } finally {
      setDeleting(false);
    }
  };

  const resumeFileName =
    (card.extra_data?.resume_file_name as string | undefined) ||
    `${card.name}.pdf`;

  const [downloadingResume, setDownloadingResume] = useState(false);
  const handleDownloadResume = async () => {
    if (downloadingResume) return;
    setDownloadingResume(true);
    try {
      const files = await getEntityFiles(card.id);
      const resumeFile =
        files.find((f) => f.file_type === "resume") || files[0];
      if (!resumeFile) {
        toast.error("Файл резюме не найден");
        return;
      }
      const blob = await downloadEntityFile(card.id, resumeFile.id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = resumeFile.file_name || resumeFileName;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch {
      toast.error("Ошибка при скачивании резюме");
    } finally {
      setDownloadingResume(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-[var(--hf-edit-overlay-z)] flex items-start justify-center overflow-auto bg-[var(--hf-black-alpha-30)] pt-[var(--hf-edit-overlay-top)] font-hf-body"
      {...backdropClose(onClose)}
    >
      <motion.div
        initial={{ scale: 0.985, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        exit={{ scale: 0.985, opacity: 0 }}
        transition={{ duration: 0.16, ease: [0.22, 1, 0.36, 1] }}
        onClick={(e) => e.stopPropagation()}
        className="mb-[var(--hf-space-xxl)] flex h-[var(--hf-edit-modal-h)] w-[var(--hf-edit-modal-w)] max-w-[var(--hf-edit-modal-max-w)] flex-col overflow-hidden rounded-[var(--hf-edit-modal-radius)] bg-transparent text-[length:var(--hf-fs-s)] leading-[var(--hf-edit-modal-lh)] text-[var(--hf-main-900)] shadow-none hf-dark-disabled:text-[var(--hf-white)]"
      >
        <div className="relative flex h-[var(--hf-edit-header-h)] flex-shrink-0 items-start justify-between rounded-t-[var(--hf-edit-modal-radius)] border-b-[length:var(--hf-edit-header-border)] border-[var(--hf-ui-divider)] bg-[var(--hf-white)] px-[var(--hf-space-xxl)] py-[var(--hf-space-xl)] pr-[var(--hf-edit-header-pr)] hf-dark-disabled:border-[color:var(--hf-white-alpha-10)] hf-dark-disabled:bg-[var(--hf-bg-dark)]">
          <div className="flex min-w-0 items-center gap-[var(--hf-space-l)]">
            <div className="h-[var(--hf-edit-avatar)] w-[var(--hf-edit-avatar)] flex-shrink-0 overflow-hidden rounded-full bg-[var(--hf-bg-muted)]">
              {card.photo_url ? (
                <img
                  src={card.photo_url}
                  alt=""
                  className="h-full w-full object-cover"
                />
              ) : (
                <div className="flex h-full w-full items-center justify-center text-[length:var(--hf-fs-xxs)] font-medium text-[var(--hf-main-600)]">
                  {getInitials(card.name)}
                </div>
              )}
            </div>
            <h3 className="truncate text-[length:var(--hf-edit-title-fs)] font-medium leading-[var(--hf-edit-title-lh)] tracking-normal text-[var(--hf-main-900)] hf-dark-disabled:text-[var(--hf-white)]">
              {card.name}
            </h3>
          </div>
          <button
            onClick={onClose}
            className="absolute right-[var(--hf-edit-close-right)] top-[var(--hf-edit-close-top)] inline-flex h-[var(--hf-edit-close-h)] w-[var(--hf-edit-close-w)] flex-shrink-0 items-center justify-center rounded-[var(--hf-radius-s)] text-[var(--hf-ui-close)] transition-colors hover:bg-[var(--hf-black-alpha-04)] hover:text-[var(--hf-main-700)] hf-dark-disabled:text-[color:var(--hf-white-alpha-70)] hf-dark-disabled:hover:bg-[var(--hf-white-alpha-06)]"
            aria-label="Закрыть"
          >
            <HuntflowClose28Icon className="h-[var(--hf-edit-close-icon)] w-[var(--hf-edit-close-icon)]" />
          </button>
        </div>

        <div className="flex h-[var(--hf-edit-body-h)] flex-shrink-0 overflow-hidden bg-[var(--hf-white)] px-[var(--hf-space-xxl)] hf-dark-disabled:bg-[var(--hf-bg-dark)]">
          <div className="w-[var(--hf-edit-left-w)] flex-shrink-0 overflow-y-auto py-[var(--hf-edit-column-py)] pr-[var(--hf-space-xxl)]">
            <EditField
              label="Фамилия"
              value={lastName}
              onChange={setLastName}
              required
              error={touched.name ? errors.name : null}
              onBlur={() => markTouched("name")}
              autoFocus
            />
            <EditField
              label="Имя"
              value={firstName}
              onChange={setFirstName}
              error={touched.name ? errors.name : null}
              onBlur={() => markTouched("name")}
            />
            <EditField
              label="Отчество"
              value={middleName}
              onChange={setMiddleName}
              error={touched.name ? errors.name : null}
              onBlur={() => markTouched("name")}
            />
            <EditField
              label="Телефон"
              value={phone}
              onChange={setPhone}
              placeholder="+7 999 123 4567"
              type="tel"
              error={touched.phone ? errors.phone : null}
              onBlur={() => markTouched("phone")}
            />
            <EditField
              label="Электронная почта"
              value={email}
              onChange={setEmail}
              placeholder="email@example.com"
              type="email"
              error={touched.email ? errors.email : null}
              onBlur={() => markTouched("email")}
            />
            <EditField
              label="Telegram"
              value={telegram}
              onChange={setTelegram}
              placeholder="@username"
              error={touched.telegram ? errors.telegram : null}
              onBlur={() => markTouched("telegram")}
            />
            <EditField
              label="Кем и где работает"
              value={position}
              onChange={setPosition}
              placeholder="QA engineer"
              error={touched.position ? errors.position : null}
              onBlur={() => markTouched("position")}
              compactGap
            />
            <EditField
              label="Компания"
              value={company}
              onChange={setCompany}
              placeholder="ООО"
              error={touched.company ? errors.company : null}
              onBlur={() => markTouched("company")}
              hideLabel
            />
            <EditField
              label="Зарплатные ожидания"
              value={salary}
              onChange={setSalary}
              placeholder=""
              addon={
                <select
                  value={salaryCurrency}
                  onChange={(e) => setSalaryCurrency(e.target.value)}
                  className="hf-candidate-currency-select h-[var(--hf-edit-field-h)] w-full rounded-[var(--hf-edit-field-radius)] border border-[color:var(--hf-black-alpha-16)] bg-[var(--hf-white)] pl-[var(--hf-edit-field-px)] text-[length:var(--hf-edit-field-fs)] text-[var(--hf-main-900)] focus:outline-none focus:border-[color:var(--hf-cyan-500)] hf-dark-disabled:bg-transparent hf-dark-disabled:text-[var(--hf-white)] hf-dark-disabled:border-[color:var(--hf-white-alpha-10)]"
                >
                  {SALARY_INPUT_CURRENCIES.map((c) => (
                    <option key={c.value} value={c.value}>{c.label}</option>
                  ))}
                </select>
              }
            />
            <EditField
              label="Город"
              value={city}
              onChange={setCity}
              placeholder="Москва"
            />
            <EditField
              label="Навыки"
              value={skills}
              onChange={setSkills}
              placeholder="через запятую"
            />
            <EditField
              label="Дата рождения"
              type="date"
              value={birthDate}
              onChange={setBirthDate}
              clearable
            />
          </div>

          <div className="min-w-0 flex-1 overflow-y-auto border-l border-[var(--hf-ui-divider)] py-[var(--hf-edit-column-py)] pl-[var(--hf-space-xxl)] hf-dark-disabled:border-[color:var(--hf-white-alpha-10)]">
            <div className="hf-candidate-source-block mb-[var(--hf-space-l)]">
              <label className="mb-[var(--hf-edit-label-mb)] block text-[length:var(--hf-edit-label-fs)] font-semibold leading-[var(--hf-edit-label-lh)] text-[var(--hf-main-900)] hf-dark-disabled:text-[var(--hf-white)]">
                Источник
              </label>
              <button
                type="button"
                className="hf-candidate-select-btn"
                onClick={() => setSourceMenuOpen((value) => !value)}
                aria-expanded={sourceMenuOpen}
              >
                <span
                  className={clsx(
                    "truncate",
                    !source && "hf-candidate-select-placeholder",
                  )}
                >
                  {source || "Источник"}
                </span>
                <HuntflowChevronDown24Icon className="hf-candidate-select-chevron" />
              </button>
              {sourceMenuOpen && (
                <div className="hf-candidate-source-menu">
                  <div className="hf-candidate-source-search">
                    <Search className="hf-candidate-source-search-icon" />
                    <input
                      value={sourceSearch}
                      onChange={(e) => setSourceSearch(e.target.value)}
                      className="hf-candidate-source-search-input"
                      placeholder="Поиск..."
                      autoFocus
                    />
                  </div>
                  <div className="hf-candidate-source-list">
                    {filteredSources.length > 0 ? (
                      filteredSources.map((option) => (
                        <button
                          key={option}
                          type="button"
                          className="hf-candidate-source-option"
                          onClick={() => {
                            setSource(option);
                            setSourceSearch("");
                            setSourceMenuOpen(false);
                          }}
                        >
                          {option}
                        </button>
                      ))
                    ) : (
                      <div className="hf-candidate-source-empty">Ничего не найдено</div>
                    )}
                  </div>
                </div>
              )}
            </div>
            <div>
              <label className="mb-[var(--hf-edit-label-mb)] block text-[length:var(--hf-edit-label-fs)] font-semibold leading-[var(--hf-edit-label-lh)] text-[var(--hf-main-900)] hf-dark-disabled:text-[var(--hf-white)]">
                Текст резюме
              </label>
              <textarea
                value={resumeText}
                onChange={(e) => setResumeText(e.target.value)}
                className="h-[var(--hf-edit-resume-h)] w-full resize-none rounded-[var(--hf-edit-field-radius)] border border-[color:var(--hf-black-alpha-16)] bg-transparent p-[var(--hf-space-l)] text-[length:var(--hf-edit-field-fs)] font-normal leading-[var(--hf-edit-field-lh)] tracking-normal text-[var(--hf-main-900)] outline-none placeholder:text-[var(--hf-main-500)] focus:border-[var(--hf-cyan-500)] hf-dark-disabled:border-[color:var(--hf-white-alpha-10)] hf-dark-disabled:text-[var(--hf-white)]"
                placeholder="Текст резюме"
              />
              <div className="mt-[var(--hf-edit-file-mt)] flex">
                <button
                  type="button"
                  onClick={handleDownloadResume}
                  disabled={downloadingResume}
                  title="Скачать резюме"
                  className="inline-flex h-[var(--hf-edit-file-h)] max-w-full items-center gap-[var(--hf-space-s)] rounded-full border border-[color:var(--hf-black-alpha-08)] bg-[var(--hf-white)] px-[var(--hf-space-s)] py-[var(--hf-space-xxs)] text-[length:var(--hf-fs-xxs)] leading-[var(--hf-lh-secondary)] text-[var(--hf-main-900)] shadow-[0_1px_1px_var(--hf-alpha-100)] transition-opacity hover:opacity-80 disabled:cursor-not-allowed disabled:opacity-60 hf-dark-disabled:border-[color:var(--hf-white-alpha-10)] hf-dark-disabled:bg-transparent hf-dark-disabled:text-[var(--hf-white)]"
                >
                  <HuntflowClip18Icon className="h-[var(--hf-edit-file-icon)] w-[var(--hf-edit-file-icon)] flex-shrink-0" />
                  <span className="min-w-[var(--hf-edit-file-name-min-w)] truncate font-medium">
                    {resumeFileName}
                  </span>
                  <HuntflowXClose16Icon className="h-[var(--hf-edit-file-close-icon)] w-[var(--hf-edit-file-close-icon)] flex-shrink-0 text-[var(--hf-ui-muted-2)]" />
                </button>
              </div>
            </div>
          </div>
        </div>

        <div className="flex h-[var(--hf-edit-footer-h)] flex-shrink-0 items-center justify-between rounded-b-[var(--hf-edit-modal-radius)] border-t-[length:var(--hf-edit-footer-border)] border-[var(--hf-ui-divider)] bg-[var(--hf-white)] px-[var(--hf-space-xxl)] py-[var(--hf-edit-footer-py)] hf-dark-disabled:border-[color:var(--hf-white-alpha-10)] hf-dark-disabled:bg-[var(--hf-bg-dark)]">
          <div className="flex items-center gap-[var(--hf-space-s)]">
            <button
              onClick={handleSave}
              disabled={saving || hasErrors}
              className="inline-flex h-[var(--hf-edit-btn-h)] min-w-[var(--hf-edit-save-min-w)] items-center justify-center rounded-[var(--hf-edit-btn-radius)] border-[length:var(--hf-edit-btn-border)] border-[var(--hf-main-900)] bg-[var(--hf-main-900)] px-[var(--hf-edit-btn-px)] text-[length:var(--hf-edit-btn-fs)] font-semibold leading-[var(--hf-edit-btn-lh)] text-[var(--hf-white)] transition-colors duration-[100ms] hover:bg-[var(--hf-main-800)] disabled:cursor-not-allowed disabled:border-[var(--hf-btn-disabled-bg)] disabled:bg-[var(--hf-btn-disabled-bg)] disabled:text-[var(--hf-main-600)] disabled:opacity-100 disabled:hover:bg-[var(--hf-btn-disabled-bg)] hf-dark-disabled:bg-[var(--hf-white)] hf-dark-disabled:text-[var(--hf-main-900)] hf-dark-disabled:hover:bg-[var(--hf-white-alpha-90)] hf-dark-disabled:disabled:bg-[var(--hf-white-alpha-08)] hf-dark-disabled:disabled:text-[color:var(--hf-white-alpha-35)]"
            >
              {saving ? (
                <HfLoadingSpinner
                  size="var(--hf-loading-spinner-size-sm)"
                  stroke="var(--hf-loading-spinner-border)"
                />
              ) : "Сохранить"}
            </button>
            <button
              onClick={onClose}
              className="inline-flex h-[var(--hf-edit-btn-h)] min-w-[var(--hf-edit-cancel-min-w)] items-center rounded-[var(--hf-edit-btn-radius)] border border-[var(--hf-ui-divider)] bg-[var(--hf-white)] px-[var(--hf-edit-btn-px)] text-[length:var(--hf-edit-btn-fs)] font-medium leading-[var(--hf-edit-btn-lh)] text-[var(--hf-main-900)] transition-colors hover:bg-[var(--hf-black-alpha-04)] hf-dark-disabled:border-[color:var(--hf-white-alpha-10)] hf-dark-disabled:bg-transparent hf-dark-disabled:text-[color:var(--hf-white-alpha-80)] hf-dark-disabled:hover:bg-[var(--hf-white-alpha-06)]"
            >
              Отмена
            </button>
          </div>
          <button
            type="button"
            onClick={() => setConfirmDelete(true)}
            disabled={deleting || saving}
            className="inline-flex h-[var(--hf-edit-btn-h)] min-w-[var(--hf-edit-delete-min-w)] items-center rounded-[var(--hf-edit-btn-radius)] px-[var(--hf-edit-btn-px)] text-[length:var(--hf-edit-btn-fs)] font-medium leading-[var(--hf-edit-btn-lh)] text-[var(--hf-ui-delete)] transition-colors hover:text-[var(--hf-red-500)] disabled:cursor-not-allowed disabled:opacity-60"
          >
            {deleting ? "Удаление…" : "Удалить"}
          </button>
        </div>
      </motion.div>
      {confirmDelete &&
        createPortal(
          <div
            className="hf-confirm-modal-backdrop"
            style={{ zIndex: 60 }}
            onClick={(e) => {
              e.stopPropagation();
              if (!deleting) setConfirmDelete(false);
            }}
          >
            <div className="hf-confirm-modal hf-confirm-modal-delete" onClick={(e) => e.stopPropagation()}>
              <div>
                <h3 className="hf-confirm-modal-title">Удалить кандидата?</h3>
                <p className="hf-confirm-modal-subtitle">«{card.name || "без имени"}»</p>
                <p className="hf-confirm-modal-subtitle">
                  Он пропадёт из базы и воронок. 7 дней его можно вернуть целиком — с воронками,
                  историей и файлами: «Настройки HR» → «Удалённые кандидаты».
                </p>
              </div>
              <div className="hf-confirm-modal-actions">
                <button
                  type="button"
                  onClick={() => setConfirmDelete(false)}
                  disabled={deleting}
                  className="hf-confirm-modal-cancel"
                >
                  Отмена
                </button>
                <button
                  type="button"
                  onClick={handleDelete}
                  disabled={deleting}
                  className="hf-confirm-modal-submit hf-confirm-modal-submit-danger"
                >
                  {deleting ? "Удаляем…" : "Удалить"}
                </button>
              </div>
            </div>
          </div>,
          document.body,
        )}
    </motion.div>
  );
}

export function EditField({
  label,
  value,
  onChange,
  placeholder,
  type,
  required,
  error,
  onBlur,
  className,
  hideLabel,
  clearable,
  compactGap,
  autoFocus,
  addon,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  type?: string;
  required?: boolean;
  error?: string | null;
  onBlur?: () => void;
  className?: string;
  hideLabel?: boolean;
  clearable?: boolean;
  compactGap?: boolean;
  autoFocus?: boolean;
  // Доп. контрол справа от инпута (напр. выбор валюты для зарплаты).
  addon?: ReactNode;
}) {
  return (
    <div className={clsx(compactGap ? "mb-[var(--hf-space-s)]" : "mb-[var(--hf-space-l)]", className)}>
      {!hideLabel && (
        <label className="mb-[var(--hf-edit-label-mb)] block text-[length:var(--hf-edit-label-fs)] font-medium leading-[var(--hf-edit-label-lh)] text-[var(--hf-main-900)] hf-dark-disabled:text-[var(--hf-white)]">
          {label}
          {required && <span className="sr-only"> *</span>}
        </label>
      )}
      <div className={addon ? "flex items-stretch gap-2" : undefined}>
      <div className="relative flex-1">
        {type === "date" ? (
          // В формах кандидата единственное date-поле — дата рождения → будущее запрещаем.
          <DatePickerFactorial
            value={value}
            onChange={onChange}
            placeholder={placeholder || "дд.мм.гггг"}
            disableFuture
          />
        ) : (
          <>
        <input
          type={type || "text"}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onBlur={onBlur}
          placeholder={placeholder}
          autoFocus={autoFocus}
          aria-invalid={!!error}
          className={clsx(
            "h-[var(--hf-edit-field-h)] w-full rounded-[var(--hf-edit-field-radius)] border bg-[var(--hf-white)] px-[var(--hf-edit-field-px)] pb-[var(--hf-border-xs)] text-[length:var(--hf-edit-field-fs)] font-normal leading-[var(--hf-edit-field-lh)] tracking-normal text-[var(--hf-main-900)] [align-items:center] placeholder:text-[var(--hf-main-500)] focus:outline-none hf-dark-disabled:bg-transparent hf-dark-disabled:text-[var(--hf-white)]",
            clearable && value ? "pr-[var(--hf-edit-field-pr-clear)]" : "",
            error
              ? "border-[color:var(--hf-red-500)] focus:border-[var(--hf-red-500)]"
              : "border-[color:var(--hf-black-alpha-16)] focus:border-[var(--hf-cyan-500)] hf-dark-disabled:border-[color:var(--hf-white-alpha-10)] hf-dark-disabled:focus:border-[var(--hf-cyan-500)]",
          )}
        />
        {clearable && value && (
          <button
            type="button"
            onClick={() => onChange("")}
            className="absolute right-[var(--hf-edit-clear-offset)] top-[var(--hf-edit-clear-offset)] inline-flex h-[var(--hf-edit-clear-h)] w-[var(--hf-edit-clear-w)] items-center justify-center bg-transparent text-[var(--hf-ui-muted-1)]"
            aria-label={`Очистить ${label}`}
          >
            <HuntflowRemoveIcon className="h-[var(--hf-edit-clear-icon)] w-[var(--hf-edit-clear-icon)] text-[var(--hf-ui-muted-7)]" />
          </button>
        )}
          </>
        )}
      </div>
      {addon && <div style={{ width: 110, flexShrink: 0 }}>{addon}</div>}
      </div>
      {error && (
        <p className="mt-[var(--hf-space-xs)] text-[length:var(--hf-edit-error-fs)] leading-[var(--hf-edit-error-lh)] text-[var(--hf-red-500)]">
          {error}
        </p>
      )}
    </div>
  );
}

// ================================================================
// LIST SETTINGS MODAL (Huntflow user settings)
// ================================================================

