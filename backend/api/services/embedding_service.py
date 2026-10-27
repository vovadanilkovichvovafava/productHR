"""
Embedding Service - generates and manages embeddings for similarity search.

Features:
- Generate embeddings via OpenAI text-embedding-3-small
- Cache embeddings in Redis (7 days TTL)
- Batch generation for multiple entities/vacancies
- Auto-update on entity/vacancy changes
"""

import logging
import json
import hashlib
from typing import List, Optional, Dict, Any

from openai import AsyncOpenAI

from ..config import get_settings
from .redis_cache import redis_cache

logger = logging.getLogger("hr-analyzer.embedding-service")
settings = get_settings()

# Embedding model config
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536
REDIS_TTL = 7 * 24 * 3600  # 7 days


class EmbeddingService:
    """Service for generating and managing embeddings."""

    def __init__(self):
        self._client: Optional[AsyncOpenAI] = None

    @property
    def client(self) -> AsyncOpenAI:
        """Lazy initialization of OpenAI client."""
        if self._client is None:
            if not settings.openai_api_key:
                raise ValueError("OPENAI_API_KEY is not configured")
            self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        return self._client

    def _build_entity_text(self, entity) -> str:
        """Build text representation of entity for embedding.

        Args:
            entity: Entity model instance

        Returns:
            Text representation suitable for embedding generation
        """
        parts = []

        if entity.name:
            parts.append(f"Name: {entity.name}")
        if entity.position:
            parts.append(f"Position: {entity.position}")
        if entity.company:
            parts.append(f"Company: {entity.company}")
        if entity.tags:
            parts.append(f"Skills: {', '.join(entity.tags)}")

        # From extra_data (contains ai_profile from AI analysis)
        extra = entity.extra_data or {}
        if "ai_profile" in extra:
            profile = extra["ai_profile"]
            if profile.get("skills"):
                parts.append(f"Technical skills: {', '.join(profile.get('skills', []))}")
            if profile.get("specialization"):
                parts.append(f"Specialization: {profile['specialization']}")
            if profile.get("level"):
                parts.append(f"Level: {profile['level']}")
            if profile.get("experience_years"):
                parts.append(f"Experience: {profile['experience_years']} years")
            if profile.get("summary"):
                parts.append(f"Summary: {profile['summary']}")

        # AI-generated summary from entity memory
        if entity.ai_summary:
            parts.append(f"AI Summary: {entity.ai_summary}")

        return "\n".join(parts) if parts else entity.name or "Unknown"

    def _build_vacancy_text(self, vacancy) -> str:
        """Build text representation of vacancy for embedding.

        Args:
            vacancy: Vacancy model instance

        Returns:
            Text representation suitable for embedding generation
        """
        parts = []

        if vacancy.title:
            parts.append(f"Title: {vacancy.title}")
        if vacancy.description:
            # Limit description to 500 chars to avoid token limits
            parts.append(f"Description: {vacancy.description[:500]}")
        if vacancy.requirements:
            parts.append(f"Requirements: {vacancy.requirements[:500]}")
        if vacancy.experience_level:
            parts.append(f"Level: {vacancy.experience_level}")
        if vacancy.tags:
            parts.append(f"Skills: {', '.join(vacancy.tags)}")
        if vacancy.location:
            parts.append(f"Location: {vacancy.location}")
        if vacancy.employment_type:
            parts.append(f"Employment: {vacancy.employment_type}")
        if vacancy.responsibilities:
            parts.append(f"Responsibilities: {vacancy.responsibilities[:300]}")

        return "\n".join(parts) if parts else vacancy.title or "Unknown"

    def _get_cache_key(self, text: str) -> str:
        """Generate cache key from text hash.

        Uses MD5 for speed (not security-critical here).
        """
        text_hash = hashlib.md5(text.encode()).hexdigest()
        return f"embedding:{text_hash}"

    async def _get_cached_embedding(self, text: str) -> Optional[List[float]]:
        """Get embedding from Redis cache."""
        try:
            cache_key = self._get_cache_key(text)
            cached = await redis_cache.get(cache_key)
            if cached:
                return json.loads(cached)
        except json.JSONDecodeError as e:
            logger.warning(f"Redis cache JSON decode error: {e}")
        except Exception as e:
            logger.warning(f"Redis cache get error: {e}")
        return None

    async def _set_cached_embedding(self, text: str, embedding: List[float]) -> None:
        """Store embedding in Redis cache."""
        try:
            cache_key = self._get_cache_key(text)
            await redis_cache.set(cache_key, json.dumps(embedding), ttl_seconds=REDIS_TTL)
        except Exception as e:
            logger.warning(f"Redis cache set error: {e}")

    async def generate_embedding(self, text: str, use_cache: bool = True) -> Optional[List[float]]:
        """Generate embedding for text using OpenAI.

        Args:
            text: Text to generate embedding for
            use_cache: Whether to use Redis cache (default True)

        Returns:
            List of floats (1536 dimensions) or None on error
        """
        if not text or not text.strip():
            logger.debug("Empty text provided, skipping embedding generation")
            return None

        # Check cache first
        if use_cache:
            cached = await self._get_cached_embedding(text)
            if cached:
                logger.debug("Embedding cache hit")
                return cached

        try:
            response = await self.client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=text,
                dimensions=EMBEDDING_DIMENSIONS
            )
            embedding = response.data[0].embedding

            # Cache the result
            if use_cache:
                await self._set_cached_embedding(text, embedding)

            logger.debug(f"Generated embedding for text of length {len(text)}")
            return embedding

        except Exception as e:
            logger.error(f"Embedding generation error: {e}")
            return None

    async def generate_entity_embedding(self, entity) -> Optional[List[float]]:
        """Generate embedding for an entity.

        Args:
            entity: Entity model instance

        Returns:
            Embedding vector or None
        """
        text = self._build_entity_text(entity)
        logger.debug(f"Building embedding for entity {entity.id}: {entity.name}")
        return await self.generate_embedding(text)

    async def generate_vacancy_embedding(self, vacancy) -> Optional[List[float]]:
        """Generate embedding for a vacancy.

        Args:
            vacancy: Vacancy model instance

        Returns:
            Embedding vector or None
        """
        text = self._build_vacancy_text(vacancy)
        logger.debug(f"Building embedding for vacancy {vacancy.id}: {vacancy.title}")
        return await self.generate_embedding(text)

    async def batch_generate_embeddings(
        self,
        texts: List[str],
        use_cache: bool = True
    ) -> List[Optional[List[float]]]:
        """Generate embeddings for multiple texts in batch.

        OpenAI's API supports batch embeddings, which is more efficient
        than generating one by one.

        Args:
            texts: List of texts to generate embeddings for
            use_cache: Whether to use Redis cache

        Returns:
            List of embeddings (same order as input texts)
        """
        if not texts:
            return []

        # Filter out empty texts and track indices
        valid_texts = []
        valid_indices = []
        results: List[Optional[List[float]]] = [None] * len(texts)

        for i, text in enumerate(texts):
            if text and text.strip():
                # Check cache first
                if use_cache:
                    cached = await self._get_cached_embedding(text)
                    if cached:
                        results[i] = cached
                        continue
                valid_texts.append(text)
                valid_indices.append(i)

        # If all texts were cached or empty, return early
        if not valid_texts:
            logger.debug("All embeddings served from cache")
            return results

        try:
            # Batch API call
            response = await self.client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=valid_texts,
                dimensions=EMBEDDING_DIMENSIONS
            )

            # Map results back to original indices
            for item, original_idx, text in zip(response.data, valid_indices, valid_texts):
                embedding = item.embedding
                results[original_idx] = embedding

                # Cache each result
                if use_cache:
                    await self._set_cached_embedding(text, embedding)

            logger.info(f"Batch generated {len(valid_texts)} embeddings")
            return results

        except Exception as e:
            logger.error(f"Batch embedding error: {e}")
            # Return partial results (cached ones)
            return results

    async def batch_generate_entity_embeddings(
        self,
        entities: list
    ) -> Dict[int, Optional[List[float]]]:
        """Generate embeddings for multiple entities.

        Args:
            entities: List of Entity model instances

        Returns:
            Dict mapping entity_id to embedding
        """
        if not entities:
            return {}

        texts = [self._build_entity_text(e) for e in entities]
        embeddings = await self.batch_generate_embeddings(texts)

        return {
            entity.id: embedding
            for entity, embedding in zip(entities, embeddings)
        }

    async def batch_generate_vacancy_embeddings(
        self,
        vacancies: list
    ) -> Dict[int, Optional[List[float]]]:
        """Generate embeddings for multiple vacancies.

        Args:
            vacancies: List of Vacancy model instances

        Returns:
            Dict mapping vacancy_id to embedding
        """
        if not vacancies:
            return {}

        texts = [self._build_vacancy_text(v) for v in vacancies]
        embeddings = await self.batch_generate_embeddings(texts)

        return {
            vacancy.id: embedding
            for vacancy, embedding in zip(vacancies, embeddings)
        }

    async def invalidate_entity_cache(self, entity) -> None:
        """Invalidate cached embedding for an entity.

        Call this when entity data changes significantly.
        """
        text = self._build_entity_text(entity)
        cache_key = self._get_cache_key(text)
        await redis_cache.delete(cache_key)
        logger.debug(f"Invalidated embedding cache for entity {entity.id}")

    async def invalidate_vacancy_cache(self, vacancy) -> None:
        """Invalidate cached embedding for a vacancy.

        Call this when vacancy data changes significantly.
        """
        text = self._build_vacancy_text(vacancy)
        cache_key = self._get_cache_key(text)
        await redis_cache.delete(cache_key)
        logger.debug(f"Invalidated embedding cache for vacancy {vacancy.id}")


# Global service instance
embedding_service = EmbeddingService()
