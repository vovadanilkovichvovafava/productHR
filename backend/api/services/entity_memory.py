"""
Entity Long-term Memory Service

Provides AI memory persistence for entities:
- Auto-summarization of all interactions
- Key events extraction and tracking
- Context building for AI that preserves history without token overflow

The summary is updated periodically (not on every message) to save API costs.
"""
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import anthropic

from ..config import get_settings

logger = logging.getLogger("hr-analyzer.entity-memory")
settings = get_settings()

# Update summary if older than this
SUMMARY_UPDATE_INTERVAL = timedelta(hours=24)

# Minimum new content to trigger summary update
MIN_NEW_CONTENT_LENGTH = 500


SUMMARY_PROMPT = """Ты — AI-ассистент для HR. Обнови краткое резюме о контакте на основе ВСЕЙ доступной информации.

ТЕКУЩЕЕ РЕЗЮМЕ (если есть):
{current_summary}

НОВЫЕ ДАННЫЕ:
{new_content}

КЛЮЧЕВЫЕ СОБЫТИЯ (если есть):
{key_events}

---

Напиши ОБНОВЛЁННОЕ резюме (2-4 абзаца), которое включает:
1. Кто этот человек (роль, компания, позиция)
2. История взаимодействия (как пришёл, что происходило)
3. Ключевые достижения или проблемы
4. Текущий статус отношений
5. Что важно помнить для будущих взаимодействий

Пиши кратко, но информативно. Фокусируйся на фактах, а не эмоциях.
НЕ теряй важную информацию из предыдущего резюме!"""


KEY_EVENTS_PROMPT = """Извлеки ключевые события/вехи из этого контента.

КОНТЕНТ:
{content}

УЖЕ ИЗВЕСТНЫЕ СОБЫТИЯ:
{existing_events}

---

Верни JSON-массив НОВЫХ событий (которых ещё нет в списке):
[
  {{"date": "2024-01-15", "event": "hired", "details": "Нанят в отдел разработки"}},
  {{"date": "2024-03-20", "event": "promotion", "details": "Повышен до Senior"}},
]

Типы событий: hired, fired, promotion, demotion, transfer, warning, achievement, meeting, offer, rejection, interview, onboarding, offboarding, other

Если новых событий нет — верни пустой массив []
Верни ТОЛЬКО JSON, без пояснений."""


class EntityMemoryService:
    """Service for managing entity long-term AI memory."""

    def __init__(self):
        self._client: Optional[anthropic.AsyncAnthropic] = None
        self.model = settings.claude_model

    @property
    def client(self) -> anthropic.AsyncAnthropic:
        if self._client is None:
            self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        return self._client

    def should_update_summary(self, entity, new_content_length: int = 0) -> bool:
        """Check if entity summary should be updated."""
        # No summary yet - definitely update
        if not entity.ai_summary:
            return new_content_length >= MIN_NEW_CONTENT_LENGTH

        # Summary is old - update
        if entity.ai_summary_updated_at:
            age = datetime.utcnow() - entity.ai_summary_updated_at
            if age > SUMMARY_UPDATE_INTERVAL:
                return True

        # Significant new content
        return new_content_length >= MIN_NEW_CONTENT_LENGTH * 2

    async def update_summary(
        self,
        entity,
        new_content: str,
        db_session
    ) -> str:
        """Update entity summary with new content."""
        try:
            # Format key events
            key_events_str = ""
            if entity.key_events:
                for event in entity.key_events:
                    key_events_str += f"- {event.get('date', '?')}: {event.get('event', '?')} - {event.get('details', '')}\n"

            prompt = SUMMARY_PROMPT.format(
                current_summary=entity.ai_summary or "Нет предыдущего резюме",
                new_content=new_content[:8000],  # Limit to avoid token overflow
                key_events=key_events_str or "Нет записанных событий"
            )

            response = await self.client.messages.create(
                model=self.model,
                max_tokens=1000,
                messages=[{"role": "user", "content": prompt}]
            )

            new_summary = response.content[0].text

            # Update entity
            entity.ai_summary = new_summary
            entity.ai_summary_updated_at = datetime.utcnow()
            await db_session.commit()

            logger.info(f"Updated summary for entity {entity.id}")
            return new_summary

        except Exception as e:
            logger.error(f"Failed to update entity summary: {e}")
            return entity.ai_summary or ""

    async def extract_key_events(
        self,
        entity,
        content: str,
        db_session
    ) -> List[Dict[str, Any]]:
        """Extract and add key events from content."""
        try:
            # Format existing events
            existing_str = ""
            if entity.key_events:
                for event in entity.key_events:
                    existing_str += f"- {event.get('date', '?')}: {event.get('event', '?')}\n"

            prompt = KEY_EVENTS_PROMPT.format(
                content=content[:5000],
                existing_events=existing_str or "Нет"
            )

            response = await self.client.messages.create(
                model=self.model,
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}]
            )

            # Parse JSON response
            import json
            text = response.content[0].text.strip()
            # Handle markdown code blocks
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()

            new_events = json.loads(text)

            if new_events and isinstance(new_events, list):
                # Add new events
                current_events = entity.key_events or []
                current_events.extend(new_events)

                # Sort by date
                current_events.sort(key=lambda x: x.get("date", "9999"))

                entity.key_events = current_events
                await db_session.commit()

                logger.info(f"Added {len(new_events)} key events for entity {entity.id}")
                return new_events

            return []

        except Exception as e:
            logger.error(f"Failed to extract key events: {e}")
            return []

    def build_memory_context(self, entity) -> str:
        """Build memory context for AI prompts."""
        parts = []

        # Add summary if exists
        if entity.ai_summary:
            parts.append(f"## 📋 Резюме контакта\n{entity.ai_summary}")

        # Add key events if exist
        if entity.key_events:
            events_str = "## 📅 Ключевые события\n"
            for event in entity.key_events[-10:]:  # Last 10 events
                emoji = {
                    "hired": "✅",
                    "fired": "❌",
                    "promotion": "⬆️",
                    "demotion": "⬇️",
                    "transfer": "🔄",
                    "warning": "⚠️",
                    "achievement": "🏆",
                    "meeting": "📅",
                    "offer": "📝",
                    "rejection": "🚫",
                    "interview": "🎤",
                }.get(event.get("event", ""), "📌")

                events_str += f"- {event.get('date', '?')} {emoji} {event.get('details', event.get('event', ''))}\n"

            parts.append(events_str)

        return "\n\n".join(parts) if parts else ""


# Singleton instance
entity_memory_service = EntityMemoryService()
