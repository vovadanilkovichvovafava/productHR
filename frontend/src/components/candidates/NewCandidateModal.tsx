import { useState, useEffect, useMemo } from "react";
import type { ReactNode } from "react";

import { motion } from "framer-motion";
import { Search, Mail, Upload } from "lucide-react";
import clsx from "clsx";
import toast from "react-hot-toast";

import { HfLoadingSpinner } from "@/components/ui/HfLoadingSpinner";

import { SALARY_INPUT_CURRENCIES } from "@/utils/currency";
import { calculateAge } from "@/utils/date";
import { createEntity } from "@/services/api/entities";
import { getAllVacancies, createApplication } from "@/services/api/vacancies";
import DatePickerFactorial from "@/factorial/components/DatePickerFactorial";

import { HuntflowClose28Icon, HuntflowChevronDown24Icon } from "@/components/candidates/HuntflowIcons";
import { joinSalaryCurrency } from "@/components/candidates/candidateFormat";
import {
  normalizePhone,
  validateName,
  validatePhone,
  validateEmail,
  validateTelegram,
  validateFreeText,
  CANDIDATE_SOURCE_OPTIONS,
} from "@/components/candidates/candidateValidation";
import { backdropClose } from '@/utils/backdropClose';
import { useNavigate } from "react-router-dom";
import {
  ExistingCandidatesPanel,
  checkDuplicateBeforeCreate,
  hasAnyMatch,
  type DuplicateCheckResult,
} from "@/components/candidates/ExistingCandidatesPanel";

// Окно «Новый кандидат» (вынесено из AllCandidatesPage, 20.10.2026).

export function NewCandidateModal({
  onClose,
  onSaved,
  onOpenParser,
}: {
  onClose: () => void;
  // id созданного — страница открывает ЕГО карточку (см. ниже, onSaved).
  onSaved: (createdId?: number) => void;
  onOpenParser: () => void;
}) {
  const [lastName, setLastName] = useState("");
  const [firstName, setFirstName] = useState("");
  const [middleName, setMiddleName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [telegram, setTelegram] = useState("");
  const [position, setPosition] = useState("");
  const [company, setCompany] = useState("");
  const [salary, setSalary] = useState("");
  const [salaryCurrency, setSalaryCurrency] = useState("RUB");
  const [city, setCity] = useState("");
  const [skills, setSkills] = useState("");
  const [birthDate, setBirthDate] = useState("");
  const [source, setSource] = useState("Другой источник");
  const [sourceMenuOpen, setSourceMenuOpen] = useState(false);
  const [sourceSearch, setSourceSearch] = useState("");
  const [resumeText, setResumeText] = useState("");
  const [saving, setSaving] = useState(false);
  const [uploadMenuOpen, setUploadMenuOpen] = useState(false);
  const [touched, setTouched] = useState<Record<string, boolean>>({});
  const [vacancyOptions, setVacancyOptions] = useState<Array<{ id: number; title: string }>>([]);
  const [selectedVacancyId, setSelectedVacancyId] = useState<number | ''>('');

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const all = await getAllVacancies({ status: 'open' });
        if (cancelled) return;
        const seen = new Set<string>();
        const myOpen = all
          .filter(v => v.status === 'open' || v.status === 'pending_review')
          // Легаси-клоны (extra_data.cloned_from_request_id) — это дубли воронки
          // (как и на странице «Заявки», где они тоже исключаются). Иначе в
          // списке «Трафик» ×2, «Reverse» ×2.
          .filter(v => typeof (v.extra_data as Record<string, unknown> | undefined)?.cloned_from_request_id !== 'number')
          .map(v => ({ id: v.id, title: v.title }))
          // Подстраховка: схлопываем одинаковые названия (первое побеждает).
          .filter(v => {
            const key = (v.title || '').trim().toLowerCase();
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
          });
        setVacancyOptions(myOpen);
      } catch (e) {
        console.warn('Failed to load vacancies:', e);
      }
    })();
    return () => { cancelled = true; };
  }, []);
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
  const filteredSources = useMemo(() => {
    const needle = sourceSearch.trim().toLowerCase();
    if (!needle) return CANDIDATE_SOURCE_OPTIONS;
    return CANDIDATE_SOURCE_OPTIONS.filter((option) =>
      option.toLowerCase().includes(needle),
    );
  }, [sourceSearch]);

  const markTouched = (_field: string) => undefined;

  // «Уже есть в базе» до создания (22.10.2026): первая «Сохранить» проверяет
  // общим матчером дублей; нашлось — показываем, кнопка становится «Всё равно
  // создать». Поменяли ФИО/контакты — проверяем заново.
  const navigate = useNavigate();
  const [dupCheck, setDupCheck] = useState<DuplicateCheckResult | null>(null);
  const [dupCheckedFor, setDupCheckedFor] = useState<string | null>(null);
  const dupSignature = JSON.stringify([fullName.trim(), email.trim(), phone.trim(), telegram.trim()]);
  const dupWarned = dupCheckedFor === dupSignature && hasAnyMatch(dupCheck);
  const openExisting = (entityId: number, archived?: boolean) => {
    if (archived) {
      onClose();
      navigate(`/all-candidates?entity=${entityId}&archived=1`);
    } else {
      onSaved(entityId);
    }
  };

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
      if (dupCheckedFor !== dupSignature) {
        let res: DuplicateCheckResult | null = null;
        try {
          res = await checkDuplicateBeforeCreate({
            full_name: fullName,
            email: email.trim() || undefined,
            phone: normalizedPhone,
            telegram: cleanTelegram || undefined,
          });
        } catch {
          res = null; // проверка — подсказка, не замок: сбой не мешает создать
        }
        setDupCheck(res);
        setDupCheckedFor(dupSignature);
        if (hasAnyMatch(res)) return;
      }
      const trimmedBirthDate = birthDate.trim();
      const created = await createEntity({
        type: "candidate",
        name: fullName,
        status: "new",
        phone: normalizedPhone,
        email: email.trim() || undefined,
        telegram_usernames: cleanTelegram ? [cleanTelegram] : undefined,
        position: position.trim() || undefined,
        company: company.trim() || undefined,
        extra_data: {
          birth_date: trimmedBirthDate || undefined,
          // См. calculateAge — возраст всегда считается из точной даты
          // рождения, если она указана при создании.
          age: trimmedBirthDate ? calculateAge(trimmedBirthDate) ?? undefined : undefined,
          resume_text: resumeText.trim() || undefined,
          source: source.trim() || undefined,
          salary: joinSalaryCurrency(salary, salaryCurrency) || undefined,
          city: city.trim() || undefined,
          skills: skills.split(",").map((s) => s.trim()).filter(Boolean),
        },
      });

      if (selectedVacancyId) {
        try {
          await createApplication(Number(selectedVacancyId), {
            vacancy_id: Number(selectedVacancyId),
            entity_id: created.id,
            source: 'manual_add',
          });
          const vacancyTitle = vacancyOptions.find(v => v.id === selectedVacancyId)?.title;
          toast.success(`Кандидат добавлен на воронку «${vacancyTitle ?? '...'}»`);
        } catch (e) {
          console.error('Attach to vacancy failed:', e);
          toast.error('Кандидат создан, но не удалось добавить на воронку');
        }
      } else {
        toast.success("Кандидат добавлен");
      }
      onSaved(created.id);
    } catch {
      toast.error("Ошибка создания кандидата");
    } finally {
      setSaving(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="hf-candidate-modal-overlay font-hf-body"
      style={{ background: 'rgba(0, 0, 0, 0.7)' }}
      // Не onClick={onClose}: выделение текста с отпусканием мыши за краем окна
      // закрывало его (жалоба 24.09.2026, см. backdropClose).
      {...backdropClose(onClose)}
      role="dialog"
      aria-modal="true"
      aria-labelledby="new-candidate-modal-title"
    >
      <motion.div
        initial={{ scale: 0.985, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        exit={{ scale: 0.985, opacity: 0 }}
        transition={{ duration: 0.16, ease: [0.22, 1, 0.36, 1] }}
        onClick={(e) => e.stopPropagation()}
        className="hf-candidate-modal"
      >
        <div className="hf-candidate-modal-header">
          <div className="hf-candidate-header-content">
            <div className="hf-candidate-avatar">
              <span className="hf-candidate-avatar-head" />
              <span className="hf-candidate-avatar-body" />
            </div>
            <div className="hf-candidate-title-stack">
              <h3 id="new-candidate-modal-title" className="hf-candidate-title">
                Новый кандидат
              </h3>
              <div className="hf-candidate-import-row">
                <button
                  type="button"
                  className="hf-candidate-import-btn"
                  onClick={() =>
                    toast("Импорт из почты пока недоступен в HR-bot")
                  }
                >
                  <Mail className="hf-candidate-import-icon" />
                  Импорт из почты
                </button>
                <div className="hf-candidate-upload-wrap">
                  <button
                    type="button"
                    className="hf-candidate-import-btn"
                    onClick={() => {
                      setSourceMenuOpen(false);
                      setUploadMenuOpen((value) => !value);
                    }}
                    aria-expanded={uploadMenuOpen}
                  >
                    <Upload className="hf-candidate-import-icon" />
                    Загрузка из файла
                    <HuntflowChevronDown24Icon className="hf-candidate-import-chevron" />
                  </button>
                  {uploadMenuOpen && (
                    <div className="hf-candidate-upload-menu">
                      <button
                        type="button"
                        className="hf-candidate-upload-option"
                        onClick={onOpenParser}
                      >
                        Из pdf, docx, rtf и др.
                      </button>
                      <button
                        type="button"
                        className="hf-candidate-upload-option"
                        onClick={() =>
                          toast("Импорт кандидатов из xlsx пока недоступен в HR-bot")
                        }
                      >
                        Из xlsx
                      </button>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
          <button
            onClick={onClose}
            className="hf-candidate-close-btn"
            aria-label="Закрыть"
          >
            <HuntflowClose28Icon className="hf-candidate-close-icon" />
          </button>
        </div>

        <div className="hf-candidate-modal-body">
          <div className="hf-candidate-left-col">
            <CandidateField
              label="Фамилия"
              value={lastName}
              onChange={setLastName}
              required
              error={touched.name ? errors.name : null}
              onBlur={() => markTouched("name")}
              autoFocus
            />
            <CandidateField
              label="Имя"
              value={firstName}
              onChange={setFirstName}
              error={touched.name ? errors.name : null}
              onBlur={() => markTouched("name")}
            />
            <CandidateField
              label="Отчество"
              value={middleName}
              onChange={setMiddleName}
              error={touched.name ? errors.name : null}
              onBlur={() => markTouched("name")}
            />
            <CandidateField
              label="Телефон"
              value={phone}
              onChange={setPhone}
              type="tel"
              error={touched.phone ? errors.phone : null}
              onBlur={() => markTouched("phone")}
            />
            <CandidateField
              label="Электронная почта"
              value={email}
              onChange={setEmail}
              type="email"
              error={touched.email ? errors.email : null}
              onBlur={() => markTouched("email")}
            />
            <CandidateField
              label="Telegram"
              value={telegram}
              onChange={setTelegram}
              error={touched.telegram ? errors.telegram : null}
              onBlur={() => markTouched("telegram")}
            />
            <CandidateField
              label="Кем и где работает"
              value={position}
              onChange={setPosition}
              placeholder="Должность"
              error={touched.position ? errors.position : null}
              onBlur={() => markTouched("position")}
              compactGap
            />
            <CandidateField
              label="Компания"
              value={company}
              onChange={setCompany}
              placeholder="Компания"
              error={touched.company ? errors.company : null}
              hideLabel
            />
            <CandidateField
              label="Зарплатные ожидания"
              value={salary}
              onChange={setSalary}
              addon={
                <select
                  value={salaryCurrency}
                  onChange={(e) => setSalaryCurrency(e.target.value)}
                  className="hf-candidate-input hf-candidate-currency-select"
                >
                  {SALARY_INPUT_CURRENCIES.map((c) => (
                    <option key={c.value} value={c.value}>{c.label}</option>
                  ))}
                </select>
              }
            />
            <CandidateField
              label="Город"
              value={city}
              onChange={setCity}
            />
            <CandidateField
              label="Навыки"
              value={skills}
              onChange={setSkills}
              placeholder="через запятую"
            />
            <CandidateField
              label="Дата рождения"
              type="date"
              value={birthDate}
              onChange={setBirthDate}
            />
          </div>

          <div className="hf-candidate-right-col">
            <div className="hf-candidate-source-block">
              <label className="hf-candidate-label">Источник</label>
              <button
                type="button"
                className="hf-candidate-select-btn"
                onClick={() => {
                  setUploadMenuOpen(false);
                  setSourceMenuOpen((value) => !value);
                }}
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
              <label className="hf-candidate-label">Текст резюме</label>
              <textarea
                value={resumeText}
                onChange={(e) => setResumeText(e.target.value)}
                className="hf-candidate-resume-textarea"
              />
            </div>
            <div className="hf-candidate-source-block">
              <label className="hf-candidate-label">Отправить в воронку (опционально)</label>
              <select
                value={selectedVacancyId}
                onChange={(e) => setSelectedVacancyId(e.target.value ? Number(e.target.value) : '')}
                className="hf-candidate-select-btn"
                style={{
                  width: '100%',
                  padding: '8px 12px',
                  border: '1px solid #ccc',
                  borderRadius: '4px',
                  backgroundColor: '#f5f5f5',
                  cursor: 'pointer',
                }}
              >
                <option value="">— без воронки —</option>
                {vacancyOptions.map(v => (
                  <option key={v.id} value={v.id}>{v.title}</option>
                ))}
              </select>
              {vacancyOptions.length === 0 && (
                <p className="hf-candidate-error" style={{ marginTop: '6px' }}>У вас нет открытых воронок</p>
              )}
            </div>
          </div>
        </div>

        {dupWarned && (
          <div className="px-6 pb-3">
            <ExistingCandidatesPanel result={dupCheck} onOpen={openExisting} />
          </div>
        )}
        <div className="hf-candidate-modal-footer">
          <button
            onClick={handleSave}
            disabled={saving}
            className="hf-candidate-primary-btn"
          >
            {saving ? (
              <HfLoadingSpinner
                size="var(--hf-loading-spinner-size-sm)"
                stroke="var(--hf-loading-spinner-border)"
              />
            ) : dupWarned ? "Всё равно создать" : "Сохранить"}
          </button>
          <button onClick={onClose} className="hf-candidate-secondary-btn">
            Отмена
          </button>
        </div>
      </motion.div>
    </motion.div>
  );
}

export function CandidateField({
  label,
  value,
  onChange,
  placeholder,
  type,
  required,
  error,
  onBlur,
  hideLabel,
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
  hideLabel?: boolean;
  compactGap?: boolean;
  autoFocus?: boolean;
  // Доп. контрол справа от инпута (напр. выбор валюты для зарплаты).
  addon?: ReactNode;
}) {
  const input =
    type === "date" ? (
      // В формах кандидата единственное date-поле — дата рождения → будущее запрещаем.
      <DatePickerFactorial
        value={value}
        onChange={onChange}
        placeholder={placeholder || "дд.мм.гггг"}
        disableFuture
      />
    ) : (
      <input
        type={type || "text"}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onBlur={onBlur}
        placeholder={placeholder}
        autoFocus={autoFocus}
        aria-invalid={!!error}
        className={clsx("hf-candidate-input", error && "hf-candidate-input-error")}
      />
    );
  return (
    <div className={clsx("hf-candidate-field", compactGap && "hf-candidate-field-compact")}>
      {!hideLabel && (
        <label className="hf-candidate-label">
          {label}
          {required && <span className="sr-only"> *</span>}
        </label>
      )}
      {addon ? (
        <div style={{ display: "flex", gap: 8, alignItems: "stretch" }}>
          <div style={{ flex: 1 }}>{input}</div>
          <div style={{ width: 110, flexShrink: 0 }}>{addon}</div>
        </div>
      ) : (
        input
      )}
      {error && <p className="hf-candidate-error">{error}</p>}
    </div>
  );
}

