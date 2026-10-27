"""
Prometheus Detailed Review Service.

Generates AI-powered comprehensive reviews of candidates
based on their learning platform data from Prometheus.

The review acts as a professional profile/resume that helps HR
quickly understand the candidate's experience, capabilities, and
readiness for team integration.
"""
import json
import logging
from typing import Optional, List, Dict, Any

from anthropic import AsyncAnthropic

from ..config import get_settings

logger = logging.getLogger("hr-analyzer.prometheus-review")
settings = get_settings()

SYSTEM_PROMPT = """Ты — старший HR-аналитик, специализирующийся на оценке кандидатов по данным обучения.
Твоя задача — написать детальное профессиональное ревью кандидата на основе его активности на обучающей платформе Prometheus.

Ревью должно помочь HR-менеджерам и руководителям отделов:
1. Быстро понять, кто этот человек и что он из себя представляет
2. Оценить его навыки, опыт обучения и потенциал
3. Принять решение о его интеграции в команду или отдел

Формат ответа — СТРОГО JSON (без markdown-блоков, без ```json):
{
  "professionalProfile": {
    "title": "Краткий заголовок профиля (1 строка)",
    "summary": "Развёрнутое профессиональное резюме кандидата (3-5 предложений). Кто он, что умеет, в чём его сильные стороны.",
    "keyStrengths": ["Сильная сторона 1", "Сильная сторона 2", "Сильная сторона 3"],
    "growthAreas": ["Зона роста 1", "Зона роста 2"]
  },
  "competencyAnalysis": {
    "technicalReadiness": {
      "score": 0-100,
      "label": "Начинающий / Растущий / Уверенный / Продвинутый",
      "detail": "Пояснение оценки (1-2 предложения)"
    },
    "learningAbility": {
      "score": 0-100,
      "label": "Низкая / Средняя / Высокая / Выдающаяся",
      "detail": "Пояснение (1-2 предложения)"
    },
    "consistency": {
      "score": 0-100,
      "label": "Нестабильная / Умеренная / Стабильная / Образцовая",
      "detail": "Пояснение (1-2 предложения)"
    },
    "engagement": {
      "score": 0-100,
      "label": "Пассивный / Умеренный / Активный / Лидер",
      "detail": "Пояснение (1-2 предложения)"
    }
  },
  "trailInsights": [
    {
      "trailName": "Название трейла",
      "verdict": "Краткий вердикт по трейлу (1 предложение)",
      "relevantSkills": ["Навык 1", "Навык 2"]
    }
  ],
  "teamFitRecommendation": {
    "readinessLevel": "not_ready | developing | ready | highly_ready",
    "recommendedRoles": ["Роль 1", "Роль 2"],
    "integrationAdvice": "Совет по интеграции в команду (2-3 предложения)",
    "watchPoints": ["На что обратить внимание 1", "На что обратить внимание 2"]
  },
  "overallVerdict": "Итоговое заключение — ёмкое, на 2-3 предложения. Подытоживает весь профиль."
}

ВАЖНО:
- Будь объективен, опирайся только на данные
- Не выдумывай факты, если данных мало — укажи это
- Используй русский язык
- Ответ — только JSON, ничего кроме JSON"""


class PrometheusReviewService:
    """Generates AI-powered detailed reviews from Prometheus learning data."""

    def __init__(self):
        self.client: Optional[AsyncAnthropic] = None
        self.model = settings.claude_model

    def _get_client(self) -> AsyncAnthropic:
        if self.client is None:
            self.client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        return self.client

    def _build_user_prompt(
        self,
        intern: dict,
        achievements: Optional[dict],
        review_data: dict,
    ) -> str:
        """Build a detailed prompt with all available candidate data."""
        name = intern.get("name", "Неизвестный")
        email = intern.get("email", "—")
        total_xp = intern.get("totalXP", 0)
        days_since_active = intern.get("daysSinceActive")
        last_active = intern.get("lastActiveAt")
        created_at = intern.get("createdAt")

        lines = [
            f"# Данные кандидата: {name}",
            f"Email: {email}",
            f"Дата регистрации: {created_at or '—'}",
            f"Последняя активность: {last_active or '—'}",
            f"Дней без активности: {days_since_active if days_since_active is not None else '—'}",
            f"Общий XP: {total_xp}",
            "",
        ]

        # Trail data from review
        metrics = review_data.get("metrics", {})
        lines.append(f"## Общий прогресс")
        lines.append(f"- Модулей пройдено: {metrics.get('completedModules', 0)} из {metrics.get('totalModules', 0)}")
        lines.append(f"- Процент завершения: {metrics.get('overallCompletionPercent', 0)}%")
        lines.append(f"- Количество трейлов: {metrics.get('trailCount', 0)}")
        lines.append("")

        # Detailed trails
        trails = review_data.get("trails", [])
        if trails:
            lines.append("## Прогресс по трейлам")
            for t in trails:
                lines.append(f"\n### {t.get('trailName', 'Без названия')}")
                lines.append(f"- Завершено: {t.get('completedModules', 0)}/{t.get('totalModules', 0)} ({t.get('completionPercent', 0)}%)")
                lines.append(f"- XP: {t.get('earnedXP', 0)}")
                avg = t.get("avgScore")
                if avg is not None:
                    lines.append(f"- Средний балл: {avg}")
                subs = t.get("submissions")
                if subs and subs.get("total", 0) > 0:
                    lines.append(f"- Сдано работ: {subs['total']} (одобрено: {subs.get('approved', 0)}, на проверке: {subs.get('pending', 0)}, на доработке: {subs.get('revision', 0)})")
            lines.append("")

        # Student achievements if available
        if achievements:
            student_info = achievements.get("student", {})
            if student_info:
                lines.append("## Информация о студенте")
                lines.append(f"- Роль: {student_info.get('role', '—')}")
                lines.append(f"- XP (подробно): {student_info.get('totalXP', 0)}")
                rank = student_info.get("leaderboardRank")
                if rank:
                    lines.append(f"- Позиция в лидерборде: #{rank}")
                lines.append(f"- Модулей завершено: {student_info.get('modulesCompleted', 0)}")
                lines.append("")

            # Submission stats
            sub_stats = achievements.get("submissionStats", {})
            if sub_stats.get("total", 0) > 0:
                lines.append("## Статистика сдач")
                lines.append(f"- Всего: {sub_stats.get('total', 0)}")
                lines.append(f"- Одобрено: {sub_stats.get('approved', 0)}")
                lines.append(f"- На проверке: {sub_stats.get('pending', 0)}")
                lines.append(f"- На доработке: {sub_stats.get('revision', 0)}")
                lines.append(f"- Отклонено: {sub_stats.get('failed', 0)}")
                lines.append("")

            # Trail progress
            trail_progress = achievements.get("trailProgress", [])
            if trail_progress:
                lines.append("## Детальный прогресс по трейлам (из достижений)")
                for tp in trail_progress:
                    lines.append(f"- {tp.get('trailTitle', '?')}: {tp.get('completionPercent', 0)}% ({tp.get('completedModules', 0)}/{tp.get('totalModules', 0)})")
                    if tp.get("completedAt"):
                        lines.append(f"  Завершён: {tp['completedAt']}")
                lines.append("")

            # Certificates
            certificates = achievements.get("certificates", [])
            if certificates:
                lines.append("## Сертификаты")
                for c in certificates:
                    trail_info = c.get("trail", {})
                    lines.append(f"- {trail_info.get('title', '?')} — уровень: {c.get('level', '?')}, XP: {c.get('totalXP', 0)}, выдан: {c.get('issuedAt', '?')}")
                lines.append("")

        # Flags
        flags = review_data.get("flags", {})
        lines.append("## Флаги")
        lines.append(f"- Активен: {'Да' if flags.get('active') else 'Нет'}")
        lines.append(f"- Риск отсева: {'Да' if flags.get('risk') else 'Нет'}")
        if flags.get("riskReason"):
            lines.append(f"- Причина риска: {flags['riskReason']}")
        top = flags.get("topTrails", [])
        if top:
            lines.append(f"- Сильные трейлы: {', '.join(top)}")

        return "\n".join(lines)

    async def generate_detailed_review(
        self,
        intern: dict,
        review_data: dict,
        achievements: Optional[dict] = None,
    ) -> Dict[str, Any]:
        """
        Generate a comprehensive AI review of a candidate based on Prometheus data.

        Args:
            intern: Raw intern data from Prometheus
            review_data: Deterministic review already generated by _generate_review()
            achievements: Optional student achievements data

        Returns:
            Structured dict with professional profile, competency analysis,
            trail insights, team fit, and overall verdict.
        """
        client = self._get_client()
        user_prompt = self._build_user_prompt(intern, achievements, review_data)

        system = [
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ]

        try:
            response = await client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=system,
                messages=[{"role": "user", "content": user_prompt}],
            )
            raw_text = response.content[0].text.strip()

            # Parse JSON from response
            parsed = self._parse_json_response(raw_text)
            if parsed is None:
                logger.warning("Failed to parse AI review JSON, returning fallback")
                return self._build_fallback_review(intern, review_data)

            return parsed

        except Exception as e:
            logger.error("AI review generation error: %s", e)
            return self._build_fallback_review(intern, review_data)

    def _parse_json_response(self, text: str) -> Optional[Dict[str, Any]]:
        """Try to parse JSON from AI response, handling markdown wrappers."""
        # Strip markdown code block if present
        cleaned = text.strip()
        if cleaned.startswith("```"):
            first_newline = cleaned.find("\n")
            if first_newline != -1:
                cleaned = cleaned[first_newline + 1:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3].strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            # Try to find JSON object in text
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(cleaned[start:end + 1])
                except json.JSONDecodeError:
                    pass
        return None

    def _build_fallback_review(self, intern: dict, review_data: dict) -> Dict[str, Any]:
        """Build a deterministic fallback if AI fails."""
        name = intern.get("name", "Кандидат")
        metrics = review_data.get("metrics", {})
        pct = metrics.get("overallCompletionPercent", 0)
        trails = review_data.get("trails", [])
        flags = review_data.get("flags", {})

        if pct >= 80:
            readiness = "ready"
            tech_label = "Уверенный"
        elif pct >= 50:
            readiness = "developing"
            tech_label = "Растущий"
        elif pct > 0:
            readiness = "developing"
            tech_label = "Начинающий"
        else:
            readiness = "not_ready"
            tech_label = "Начинающий"

        top_trail_names = [t["trailName"] for t in trails if t.get("completionPercent", 0) >= 70]
        all_trail_names = [t["trailName"] for t in trails]

        return {
            "professionalProfile": {
                "title": f"{name} — кандидат с платформы Prometheus",
                "summary": review_data.get("summary", f"{name} проходит обучение на платформе Prometheus."),
                "keyStrengths": top_trail_names[:3] if top_trail_names else ["Обучается на платформе"],
                "growthAreas": [t["trailName"] for t in trails if 0 < t.get("completionPercent", 0) < 30][:2] or ["Требуется больше данных"],
            },
            "competencyAnalysis": {
                "technicalReadiness": {
                    "score": min(pct + 10, 100) if pct > 0 else 0,
                    "label": tech_label,
                    "detail": f"Завершено {metrics.get('completedModules', 0)} из {metrics.get('totalModules', 0)} модулей.",
                },
                "learningAbility": {
                    "score": pct,
                    "label": "Высокая" if pct >= 70 else "Средняя" if pct >= 40 else "Низкая",
                    "detail": f"Общий прогресс {pct}% по {len(trails)} трейлам.",
                },
                "consistency": {
                    "score": 50 if flags.get("active") else 20,
                    "label": "Стабильная" if flags.get("active") else "Нестабильная",
                    "detail": "Активен на платформе." if flags.get("active") else "Низкая активность на платформе.",
                },
                "engagement": {
                    "score": min(pct + 5, 100) if pct > 0 else 0,
                    "label": "Активный" if flags.get("active") else "Пассивный",
                    "detail": f"XP: {metrics.get('totalXP', 0)}.",
                },
            },
            "trailInsights": [
                {
                    "trailName": t["trailName"],
                    "verdict": f"Прогресс: {t.get('completionPercent', 0)}%",
                    "relevantSkills": [],
                }
                for t in trails[:5]
            ],
            "teamFitRecommendation": {
                "readinessLevel": readiness,
                "recommendedRoles": [],
                "integrationAdvice": "Необходимо дополнительное собеседование для оценки готовности.",
                "watchPoints": [flags.get("riskReason")] if flags.get("riskReason") else [],
            },
            "overallVerdict": review_data.get("summary", "Недостаточно данных для формирования полного ревью."),
        }


prometheus_review_service = PrometheusReviewService()
