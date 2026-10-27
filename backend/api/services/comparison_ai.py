"""
AI-powered candidate comparison service.

Uses the same context as Entity AI Assistant (files, chats, calls)
to provide intelligent comparison between two candidates.
"""
from typing import Optional, List, AsyncGenerator
from anthropic import AsyncAnthropic
import logging
import json

from ..config import get_settings
from ..models.database import Entity, Chat, CallRecording, EntityFile
from .entity_ai import EntityAIService
from .cache import smart_truncate

logger = logging.getLogger("hr-analyzer.comparison-ai")
settings = get_settings()

COMPARISON_PROMPT = """Сравни двух кандидатов на основе ВСЕХ доступных данных (резюме, переписки, звонки).

Для каждого критерия дай оценку и объяснение:

## Опыт работы
Сравни реальный опыт работы на основе:
- Резюме и документов
- Обсуждений в переписках
- Информации из звонков

## Зарплатные ожидания
Сравни ожидания по зарплате:
- Указанные в резюме
- Озвученные в переписках/звонках
- Гибкость в переговорах

## Локация
Сравни местоположение и готовность к релокации:
- Текущая локация
- Готовность к переезду/удалёнке
- Ограничения

## Навыки и компетенции
Сравни профессиональные навыки:
- Технические навыки
- Soft skills
- Уникальные компетенции

## Мотивация и заинтересованность
Оцени на основе коммуникации:
- Активность в переписке
- Заинтересованность в позиции
- Скорость ответов

## Общая оценка
- **Кто сильнее и почему:** (1-2 предложения)
- **Рекомендация:** кого выбрать и при каких условиях

Формат ответа — markdown. Будь конкретен, приводи факты из данных."""


class ComparisonAIService:
    """AI-powered candidate comparison using full context."""

    def __init__(self):
        self._client: Optional[AsyncAnthropic] = None
        self.model = settings.claude_model
        self.entity_ai = EntityAIService()

    @property
    def client(self) -> AsyncAnthropic:
        if self._client is None:
            if not settings.anthropic_api_key:
                raise ValueError("ANTHROPIC_API_KEY не настроен")
            self._client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        return self._client

    async def _build_candidate_context(
        self,
        entity: Entity,
        chats: List[Chat],
        calls: List[CallRecording],
        files: Optional[List[EntityFile]] = None
    ) -> str:
        """Build context for a single candidate."""
        return await self.entity_ai._build_entity_context(entity, chats, calls, files)

    async def compare_stream(
        self,
        entity1: Entity,
        entity1_chats: List[Chat],
        entity1_calls: List[CallRecording],
        entity1_files: Optional[List[EntityFile]],
        entity2: Entity,
        entity2_chats: List[Chat],
        entity2_calls: List[CallRecording],
        entity2_files: Optional[List[EntityFile]],
    ) -> AsyncGenerator[str, None]:
        """
        Stream AI comparison of two candidates.

        Uses full context from files, chats, and calls for both candidates.
        """
        # Build context for both candidates
        context1 = await self._build_candidate_context(
            entity1, entity1_chats, entity1_calls, entity1_files
        )
        context2 = await self._build_candidate_context(
            entity2, entity2_chats, entity2_calls, entity2_files
        )

        # Truncate if needed (keep more context for comparison)
        max_context_per_candidate = 15000
        if len(context1) > max_context_per_candidate:
            context1 = smart_truncate(context1, max_context_per_candidate)
        if len(context2) > max_context_per_candidate:
            context2 = smart_truncate(context2, max_context_per_candidate)

        system_prompt = f"""Ты — HR-аналитик. Твоя задача — объективно сравнить двух кандидатов.

# КАНДИДАТ 1: {entity1.name}
{context1}

# КАНДИДАТ 2: {entity2.name}
{context2}

ПРАВИЛА:
1. Отвечай на русском языке
2. Основывайся ТОЛЬКО на фактах из предоставленных данных
3. Если данных по какому-то критерию нет — так и напиши
4. Будь объективен, не придумывай факты
5. Приводи конкретные примеры из переписок/файлов где возможно
6. Используй markdown для форматирования"""

        logger.info(
            f"AI Comparison: {entity1.name} (id={entity1.id}) vs {entity2.name} (id={entity2.id})"
        )

        try:
            async with self.client.messages.stream(
                model=self.model,
                max_tokens=4096,
                system=system_prompt,
                messages=[{
                    "role": "user",
                    "content": COMPARISON_PROMPT
                }]
            ) as stream:
                async for text in stream.text_stream:
                    yield text
        except Exception as e:
            logger.error(f"AI Comparison error: {e}")
            raise


# Singleton instance
comparison_ai_service = ComparisonAIService()
