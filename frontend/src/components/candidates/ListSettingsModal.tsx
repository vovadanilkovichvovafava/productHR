import { useState } from "react";

import { motion } from "framer-motion";
import { X } from "lucide-react";
import clsx from "clsx";
import toast from "react-hot-toast";

import { saveCandidateListSettings, type CandidateListFields, type CandidateListSettings } from "@/components/entities/candidateDetail/model";

import { backdropClose } from '@/utils/backdropClose';

// Окно «Настройки списка» на «Все кандидаты» (вынесено из AllCandidatesPage, 20.10.2026).

export function ListSettingsModal({
  onClose,
  initial,
  onApply,
}: {
  onClose: () => void;
  initial: CandidateListSettings;
  onApply: (settings: CandidateListSettings) => void;
}) {
  const [scope, setScope] = useState<"mine" | "all">(initial.scope);
  const [fields, setFields] = useState<CandidateListFields>(initial.fields);

  const setField = (key: keyof CandidateListFields, checked: boolean) => {
    if (key === "name") return;
    setFields((prev) => ({ ...prev, [key]: checked }));
  };

  const handleSave = () => {
    const next: CandidateListSettings = { scope, fields };
    saveCandidateListSettings(next);
    onApply(next);
    toast.success("Настройки списка сохранены");
    onClose();
  };

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-[var(--hf-list-settings-z)] flex items-start justify-center bg-transparent pt-[var(--hf-list-settings-top)]"
      {...backdropClose(onClose)}
    >
      <motion.div
        initial={{ opacity: 0, y: -8, scale: 0.985 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: -8, scale: 0.985 }}
        transition={{ duration: 0.16, ease: [0.22, 1, 0.36, 1] }}
        onClick={(e) => e.stopPropagation()}
        className="w-[var(--hf-list-settings-w)] overflow-hidden rounded-[var(--hf-list-settings-radius)] bg-[var(--hf-white)] text-[var(--hf-main-900)] leading-[var(--hf-list-settings-lh)] hf-dark-disabled:bg-[var(--hf-bg-dark)] hf-dark-disabled:text-[var(--hf-white)]"
      >
        <div className="flex h-[var(--hf-list-settings-header-h)] items-center justify-between border-b border-[var(--hf-ui-divider)] px-[var(--hf-list-settings-x)] pr-[var(--hf-list-settings-x)] hf-dark-disabled:border-[color:var(--hf-white-alpha-10)]">
          <h3 className="text-[length:var(--hf-list-settings-title-fs)] font-medium leading-[var(--hf-list-settings-title-lh)] tracking-normal">
            Настройка списков кандидатов
          </h3>
          <button
            type="button"
            onClick={onClose}
            className="inline-flex h-[var(--hf-list-settings-close)] w-[var(--hf-list-settings-close)] items-center justify-center rounded-[var(--hf-list-settings-close-radius)] text-[var(--hf-main-600)] transition-colors hover:bg-[var(--hf-bg-panel)] hover:text-[var(--hf-main-900)] hf-dark-disabled:hover:bg-[var(--hf-white-alpha-10)] hf-dark-disabled:hover:text-[var(--hf-white)]"
            aria-label="Закрыть"
          >
            <X className="h-[var(--hf-list-settings-close-icon)] w-[var(--hf-list-settings-close-icon)]" />
          </button>
        </div>

        <div className="px-[var(--hf-list-settings-x)] py-[var(--hf-space-xxl)] leading-[var(--hf-list-settings-lh)]">
          <section className="pb-[var(--hf-space-xxl)]">
            <h4 className="mb-[var(--hf-list-settings-heading-mb)] text-[length:var(--hf-list-settings-heading-fs)] font-normal leading-[var(--hf-list-settings-heading-lh)] tracking-normal">
              Показывать всех кандидатов на этапах
            </h4>
            <ListSettingRadio
              label="Только по моим вакансиям"
              checked={scope === "mine"}
              onChange={() => setScope("mine")}
            />
            <ListSettingRadio
              label="По всем открытым вакансиям"
              checked={scope === "all"}
              onChange={() => setScope("all")}
              className="mt-[var(--hf-space-xs)]"
            />
          </section>

          <section className="border-t border-[var(--hf-ui-divider)] pt-[var(--hf-space-xxl)] hf-dark-disabled:border-[color:var(--hf-white-alpha-10)]">
            <h4 className="mb-[var(--hf-list-settings-heading-mb-sm)] text-[length:var(--hf-list-settings-heading-fs)] font-normal leading-[var(--hf-list-settings-heading-lh)] tracking-normal">
              Отображать в списках кандидатов
            </h4>
            <ListSettingCheckbox
              label="ФИО кандидата"
              checked={fields.name}
              disabled
              onChange={(value) => setField("name", value)}
            />
            <ListSettingCheckbox
              label="Желаемая должность"
              checked={fields.desiredPosition}
              onChange={(value) => setField("desiredPosition", value)}
            />
            <ListSettingCheckbox
              label="Желаемая зарплата"
              checked={fields.desiredSalary}
              onChange={(value) => setField("desiredSalary", value)}
            />
            <ListSettingCheckbox
              label="Возраст и дата рождения"
              checked={fields.age}
              onChange={(value) => setField("age", value)}
            />
            <ListSettingCheckbox
              label="Общий стаж"
              checked={fields.experience}
              onChange={(value) => setField("experience", value)}
            />
            <ListSettingCheckbox
              label="Должность на последнем месте работы"
              checked={fields.lastPosition}
              onChange={(value) => setField("lastPosition", value)}
            />
            <ListSettingCheckbox
              label="Последнее место работы"
              checked={fields.lastCompany}
              onChange={(value) => setField("lastCompany", value)}
            />
            <ListSettingCheckbox
              label="Источник"
              checked={fields.source}
              onChange={(value) => setField("source", value)}
            />
            <ListSettingCheckbox
              label="Число вакансий, на которых кандидат в работе"
              checked={fields.vacanciesCount}
              onChange={(value) => setField("vacanciesCount", value)}
            />
            <ListSettingCheckbox
              label="Метки"
              checked={fields.tags}
              onChange={(value) => setField("tags", value)}
            />
          </section>
        </div>

        <div className="flex h-[var(--hf-list-settings-footer-h)] items-center gap-[var(--hf-space-s)] border-t border-[var(--hf-ui-divider)] px-[var(--hf-list-settings-x)] py-[var(--hf-edit-footer-py)] hf-dark-disabled:border-[color:var(--hf-white-alpha-10)]">
          <button
            type="button"
            onClick={handleSave}
            className="inline-flex h-[var(--hf-edit-btn-h)] items-center justify-center rounded-[var(--hf-edit-btn-radius)] border border-[var(--hf-main-900)] bg-[var(--hf-main-900)] px-[var(--hf-edit-btn-px)] text-[length:var(--hf-edit-btn-fs)] font-medium leading-[var(--hf-edit-btn-lh)] !text-[var(--hf-white)] transition-colors hover:bg-[var(--hf-main-800)] active:bg-[var(--hf-black)] disabled:cursor-not-allowed disabled:!bg-[var(--hf-btn-disabled-bg)] disabled:!text-[var(--hf-main-600)] disabled:opacity-100 disabled:hover:!bg-[var(--hf-btn-disabled-bg)] hf-dark-disabled:disabled:!bg-[var(--hf-white-alpha-08)] hf-dark-disabled:disabled:!text-[color:var(--hf-white-alpha-35)]"
          >
            Сохранить
          </button>
          <button
            type="button"
            onClick={onClose}
            className="inline-flex h-[var(--hf-edit-btn-h)] min-w-[var(--hf-edit-cancel-min-w)] items-center justify-center rounded-[var(--hf-edit-btn-radius)] border border-[var(--hf-ui-card-border)] bg-[var(--hf-white)] px-[var(--hf-edit-btn-px)] text-[length:var(--hf-edit-btn-fs)] font-medium leading-[var(--hf-edit-btn-lh)] text-[var(--hf-main-900)] transition-colors hover:bg-[var(--hf-ui-hover)] active:bg-[var(--hf-main-200)] hf-dark-disabled:border-[color:var(--hf-white-alpha-10)] hf-dark-disabled:bg-[var(--hf-white-alpha-05)] hf-dark-disabled:text-[var(--hf-white)] hf-dark-disabled:hover:bg-[var(--hf-white-alpha-10)]"
          >
            Отмена
          </button>
        </div>
      </motion.div>
    </motion.div>
  );
}

function ListSettingCheckbox({
  label,
  checked,
  disabled,
  onChange,
}: {
  label: string;
  checked: boolean;
  disabled?: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label
      className={clsx(
        "mb-[var(--hf-space-s)] flex h-[var(--hf-list-settings-option-h)] w-max items-center gap-[var(--hf-list-settings-option-gap)] text-[length:var(--hf-list-settings-option-fs)] font-normal leading-[var(--hf-list-settings-option-lh)] last:mb-0",
        disabled
          ? "cursor-default text-[var(--hf-main-600)]"
          : "cursor-pointer text-[var(--hf-main-900)] hf-dark-disabled:text-[var(--hf-white)]",
      )}
    >
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
        className="peer sr-only"
      />
      <span
        className={clsx(
          "relative inline-flex h-[var(--hf-list-settings-check)] w-[var(--hf-list-settings-check)] flex-shrink-0 items-center justify-center rounded-[var(--hf-list-settings-check-radius)] border",
          disabled && checked
            ? "border-[var(--hf-main-400)] bg-[var(--hf-main-400)]"
            : checked
              ? "border-[var(--hf-cyan-600)] bg-[var(--hf-cyan-600)]"
              : "border-[var(--hf-main-300)] bg-[var(--hf-white)]",
        )}
        aria-hidden="true"
      >
        {checked ? (
          <svg
            viewBox="0 0 12 12"
            className="h-[var(--hf-list-settings-check-icon)] w-[var(--hf-list-settings-check-icon)] text-[var(--hf-white)]"
            fill="none"
            aria-hidden="true"
          >
            <path
              d="M2.4 6.2 4.8 8.5 9.7 3.5"
              stroke="currentColor"
              strokeWidth="1.7"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        ) : null}
      </span>
      {label}
    </label>
  );
}

function ListSettingRadio({
  label,
  checked,
  onChange,
  className,
}: {
  label: string;
  checked: boolean;
  onChange: () => void;
  className?: string;
}) {
  return (
    <label
      className={clsx(
        "flex h-[var(--hf-list-settings-option-h)] w-max cursor-pointer items-center gap-[var(--hf-list-settings-option-gap)] text-[length:var(--hf-list-settings-option-fs)] leading-[var(--hf-list-settings-option-lh)] text-[var(--hf-main-900)] hf-dark-disabled:text-[var(--hf-white)]",
        className,
      )}
    >
      <input
        type="radio"
        checked={checked}
        onChange={onChange}
        className="peer sr-only"
      />
      <span
        className="relative inline-flex h-[var(--hf-list-settings-check)] w-[var(--hf-list-settings-check)] flex-shrink-0 items-center justify-center rounded-full border border-[var(--hf-main-300)] bg-[var(--hf-white)] peer-checked:border-[var(--hf-cyan-600)]"
        aria-hidden="true"
      >
        {checked ? (
          <span className="h-[var(--hf-list-settings-dot)] w-[var(--hf-list-settings-dot)] rounded-full bg-[var(--hf-cyan-600)]" />
        ) : null}
      </span>
      {label}
    </label>
  );
}
