import { useEffect, useState } from "react";

import { getEntityTeam } from "@/services/api/entities";
import { getBoardDepartments, type BoardDepartment } from "@/services/api/staffBoard";
import type { TransitionFields, TransitionStage } from "@/utils/stageTransition";

/**
 * Поля над комментарием в окне смены этапа (мит 19.11.2026): «Практика» —
 * дата выхода и ментор; «Перешёл в отдел» — дата выхода и отдел. Вид — как у
 * «Причины отказа» (`hf-reject-reason-*`).
 */
export function StageTransitionFields({
  entityId,
  stage,
  value,
  onChange,
}: {
  entityId: number;
  stage: TransitionStage;
  value: TransitionFields;
  onChange: (next: TransitionFields) => void;
}) {
  const [mentors, setMentors] = useState<string[]>([]);
  const [currentMentor, setCurrentMentor] = useState<string | null>(null);
  const [departments, setDepartments] = useState<BoardDepartment[]>([]);

  useEffect(() => {
    let alive = true;
    if (stage === "probation") {
      getEntityTeam(entityId)
        .then((team) => {
          if (!alive) return;
          setMentors(team.mentor_options ?? []);
          setCurrentMentor(team.mentor ?? null);
        })
        .catch(() => undefined); // без списка менторов дата всё равно сохранится
    } else {
      getBoardDepartments()
        .then((all) => {
          if (!alive) return;
          setDepartments(
            all
              .filter((d) => d.kind === "team" && !d.hidden && (d.offered ?? true))
              .sort((a, b) => (a.canon_order ?? 999) - (b.canon_order ?? 999) || a.name.localeCompare(b.name)),
          );
        })
        .catch(() => undefined);
    }
    return () => {
      alive = false;
    };
  }, [entityId, stage]);

  const practice = stage === "probation";
  return (
    <div className="hf-stage-transition">
      <label className="hf-stage-transition-row">
        <span className="hf-stage-transition-label">
          {practice ? "Выход на практику" : "Выход в отдел"}
        </span>
        <input
          type="date"
          required
          className="hf-reject-reason-field hf-stage-transition-input"
          value={value.date}
          onChange={(e) => onChange({ ...value, date: e.target.value })}
        />
      </label>
      {practice ? (
        <label className="hf-stage-transition-row">
          <span className="hf-stage-transition-label">Ментор</span>
          <select
            className="hf-reject-reason-field hf-stage-transition-input"
            value={value.mentor}
            onChange={(e) => onChange({ ...value, mentor: e.target.value })}
          >
            <option value="">{currentMentor ? `${currentMentor} (сейчас)` : "Не менять"}</option>
            {mentors
              .filter((m) => m !== currentMentor)
              .map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
          </select>
        </label>
      ) : (
        <label className="hf-stage-transition-row">
          <span className="hf-stage-transition-label">Отдел</span>
          <select
            className="hf-reject-reason-field hf-stage-transition-input"
            value={value.departmentId ?? ""}
            onChange={(e) =>
              onChange({ ...value, departmentId: e.target.value ? Number(e.target.value) : null })
            }
          >
            <option value="">Не менять</option>
            {departments.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </select>
        </label>
      )}
    </div>
  );
}
