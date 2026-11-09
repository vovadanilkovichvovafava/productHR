import { useCallback, useEffect, useMemo, useState } from "react";
import { getOrgStages } from "@/services/api/auth";
import { useAuthStore } from "@/stores/authStore";
import type { StageColumn } from "@/components/vacancies/StagesConfigModal";
import type { Vacancy } from "@/types";
import { STATUS_LABELS } from "@/types";
import {
  FUNNEL_STAGE_ORDER,
  STAGE_LABEL_BY_STAGE,
  STATUS_BY_STAGE,
} from "@/constants/hrStages";

// Этапы открытой воронки: свои колонки вакансии (custom_stages) или общий
// порядок, подписи с учётом настроек организации (вынесено из
// RecruiterFunnelsPage, 20.10.2026, без изменения поведения).

export interface FunnelStagesConfig {
  /** Ключи видимых колонок в порядке вкладок. */
  keys: string[];
  /** Подпись колонки по ключу. */
  labels: Record<string, string>;
  /** Этап заявки → колонки, которые его показывают (виртуальные — через maps_to). */
  enumToKeys: Record<string, string[]>;
}

const STAGE_LABELS: Record<string, string> = {
  ...STAGE_LABEL_BY_STAGE,
  new: STAGE_LABEL_BY_STAGE.applied,
};

/**
 * Чистая сборка конфигурации. orgOverrides — подписи организации по статусу
 * кандидата (GET /auth/org-stages): у воронки ключи — этапы заявки, поэтому
 * подпись ищем через пару «этап → статус».
 */
export function buildFunnelStagesConfig(
  customColumns: StageColumn[] | undefined,
  orgOverrides: Record<string, string>,
): FunnelStagesConfig {
  const labelFor = (appStage: string, fallback: string): string => {
    const entityKey = (STATUS_BY_STAGE as Record<string, string>)[appStage];
    if (entityKey && orgOverrides[entityKey]) return orgOverrides[entityKey];
    return fallback;
  };
  if (customColumns && customColumns.length > 0) {
    const visible = customColumns.filter((c) => c.visible);
    const enumToKeys: Record<string, string[]> = {};
    for (const c of visible) {
      const enumVal = c.maps_to || c.key;
      if (!enumToKeys[enumVal]) enumToKeys[enumVal] = [];
      enumToKeys[enumVal].push(c.key);
    }
    return {
      keys: visible.map((c) => c.key),
      // Свои колонки вакансии главнее, но пустую подпись берём у организации.
      labels: Object.fromEntries(visible.map((c) => [c.key, labelFor(c.maps_to || c.key, c.label)])),
      enumToKeys,
    };
  }
  return {
    keys: [...FUNNEL_STAGE_ORDER],
    labels: Object.fromEntries(
      FUNNEL_STAGE_ORDER.map((s) => [s, labelFor(s, STAGE_LABELS[s] || s)]),
    ),
    enumToKeys: Object.fromEntries(FUNNEL_STAGE_ORDER.map((s) => [s, [s]])),
  };
}

/**
 * Скоуп по этапам (09.11.2026, наставники видят только «Практику»): оставить
 * вкладки, чей этап заявки соответствует разрешённым статусам кандидата.
 * Сервер и так не отдаёт заявки других этапов — без этого воронка открывалась
 * на пустом «Новом», а нужная вкладка пряталась среди пустых.
 */
export function limitFunnelStagesToStatuses(
  config: FunnelStagesConfig,
  allowedStatuses: readonly string[] | undefined,
): FunnelStagesConfig {
  if (!allowedStatuses || allowedStatuses.length === 0) return config;
  const allowed = new Set(allowedStatuses);
  const keyToEnum: Record<string, string> = {};
  for (const [enumVal, keys] of Object.entries(config.enumToKeys)) {
    for (const k of keys) keyToEnum[k] = enumVal;
  }
  const statusOf = (key: string) =>
    (STATUS_BY_STAGE as Record<string, string>)[keyToEnum[key] || key];
  const keys = config.keys.filter((k) => allowed.has(statusOf(k)));
  if (keys.length === 0) return config; // нечего показать — не ломаем воронку
  const keep = new Set(keys);
  return {
    keys,
    labels: config.labels,
    enumToKeys: Object.fromEntries(
      Object.entries(config.enumToKeys)
        .map(([e, ks]) => [e, ks.filter((k) => keep.has(k))] as const)
        .filter(([, ks]) => ks.length > 0),
    ),
  };
}

export function useFunnelStages(selectedVacancy: Vacancy | undefined) {
  const scopeStatuses = useAuthStore((s) => s.user?.scope_statuses);
  // Подписи этапов организации (те же, что у колонок «Все кандидаты»).
  const [orgStageOverrides, setOrgStageOverrides] = useState<Record<string, string>>({});
  useEffect(() => {
    getOrgStages()
      .then((r) => {
        const map: Record<string, string> = {};
        r.stages.forEach((s) => {
          map[s.key] = s.label;
        });
        setOrgStageOverrides(map);
      })
      .catch(() => {
        /* не критично — будут дефолты */
      });
  }, []);

  const stagesConfig = useMemo(
    () =>
      limitFunnelStagesToStatuses(
        buildFunnelStagesConfig(
          selectedVacancy?.custom_stages?.columns as StageColumn[] | undefined,
          orgStageOverrides,
        ),
        scopeStatuses,
      ),
    [selectedVacancy, orgStageOverrides, scopeStatuses],
  );

  // Контейнеры влитых (исторических) кандидатов хранят статус как статус
  // кандидата (practice/tech_practice/…), а не этап заявки — без STATUS_LABELS
  // плашка показывала сырой ключ («practice» вместо «Интервью с HR»).
  const getVacancyStageLabel = useCallback(
    (stageOrKey: string) =>
      stagesConfig.labels[stageOrKey] ||
      STAGE_LABELS[stageOrKey] ||
      (STATUS_LABELS as Record<string, string>)[stageOrKey] ||
      stageOrKey,
    [stagesConfig],
  );

  const vacancyStageDropdownLabels = useMemo(() => {
    const labels: Record<string, string> = {};
    for (const key of stagesConfig.keys) labels[key] = getVacancyStageLabel(key);
    for (const stage of FUNNEL_STAGE_ORDER) labels[stage] = getVacancyStageLabel(stage);
    return labels;
  }, [getVacancyStageLabel, stagesConfig.keys]);

  return { stagesConfig, getVacancyStageLabel, vacancyStageDropdownLabels };
}
