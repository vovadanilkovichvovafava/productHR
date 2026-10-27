"""
Tests for Embedding Service and Similarity Search.

Tests:
- EmbeddingService: text building, caching, generation
- SimilaritySearchService: find similar entities, matching vacancies, matching candidates
- Integration: end-to-end embedding generation and search

NOTE: These tests are designed for future EmbeddingService and SimilaritySearchService
implementations. They use mocks for OpenAI and Redis to avoid external dependencies.
"""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
from dataclasses import dataclass
from typing import List, Optional, Dict, Any

# =============================================================================
# Mock Classes for Testing (until real implementations exist)
# =============================================================================

# Embedding dimensions for OpenAI text-embedding-ada-002
EMBEDDING_DIMENSIONS = 1536


@dataclass
class SimilarityResult:
    """Result of similarity search."""
    id: int
    name: str
    score: float  # 0.0 to 1.0
    type: str
    position: Optional[str] = None
    status: Optional[str] = None
    tags: Optional[List[str]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with score as percentage."""
        return {
            "id": self.id,
            "name": self.name,
            "score": int(self.score * 100),  # Convert to percentage
            "type": self.type,
            "position": self.position,
            "status": self.status,
            "tags": self.tags
        }


class EmbeddingService:
    """Mock EmbeddingService for testing - replace with real import when implemented."""

    def __init__(self):
        self._client = None
        self._redis = None
        self._cache_ttl = 3600 * 24  # 24 hours

    @property
    def client(self):
        """OpenAI client - lazy initialization."""
        if self._client is None:
            self._client = MagicMock()
        return self._client

    def _get_cache_key(self, text: str) -> str:
        """Generate cache key for embedding."""
        import hashlib
        text_hash = hashlib.md5(text.encode()).hexdigest()
        return f"embedding:{text_hash}"

    async def _get_cached_embedding(self, key: str) -> Optional[List[float]]:
        """Get embedding from cache."""
        if self._redis is None:
            return None
        cached = await self._redis.get(key)
        if cached:
            return json.loads(cached)
        return None

    async def _set_cached_embedding(self, key: str, embedding: List[float]) -> None:
        """Store embedding in cache."""
        if self._redis is not None:
            await self._redis.set(key, json.dumps(embedding), ex=self._cache_ttl)

    def _build_entity_text(self, entity) -> str:
        """Build searchable text from entity."""
        parts = []

        # Name
        if entity.name:
            parts.append(f"Name: {entity.name}")

        # Position
        if getattr(entity, 'position', None):
            parts.append(f"Position: {entity.position}")

        # Company
        if getattr(entity, 'company', None):
            parts.append(f"Company: {entity.company}")

        # Tags/Skills
        tags = getattr(entity, 'tags', None)
        if tags:
            parts.append(f"Skills: {', '.join(tags)}")

        # Extra data - AI profile
        extra_data = getattr(entity, 'extra_data', None)
        if extra_data and isinstance(extra_data, dict):
            ai_profile = extra_data.get('ai_profile', {})
            if ai_profile:
                if ai_profile.get('skills'):
                    parts.append(f"Technical skills: {', '.join(ai_profile['skills'])}")
                if ai_profile.get('specialization'):
                    parts.append(f"Specialization: {ai_profile['specialization']}")
                if ai_profile.get('level'):
                    parts.append(f"Level: {ai_profile['level']}")
                if ai_profile.get('experience_years'):
                    parts.append(f"Experience: {ai_profile['experience_years']} years")
                if ai_profile.get('summary'):
                    parts.append(f"Summary: {ai_profile['summary']}")

        # AI Summary
        if getattr(entity, 'ai_summary', None):
            parts.append(f"AI Summary: {entity.ai_summary}")

        if not parts:
            return "Unknown"

        return "\n".join(parts)

    def _build_vacancy_text(self, vacancy) -> str:
        """Build searchable text from vacancy."""
        parts = []

        # Title
        if getattr(vacancy, 'title', None):
            parts.append(f"Title: {vacancy.title}")

        # Description (truncate if too long)
        description = getattr(vacancy, 'description', None)
        if description:
            # Truncate to prevent token overflow
            truncated = description[:500] if len(description) > 500 else description
            parts.append(f"Description: {truncated}")

        # Requirements (truncate if too long)
        requirements = getattr(vacancy, 'requirements', None)
        if requirements:
            truncated = requirements[:500] if len(requirements) > 500 else requirements
            parts.append(f"Requirements: {truncated}")

        # Experience level
        if getattr(vacancy, 'experience_level', None):
            parts.append(f"Experience level: {vacancy.experience_level}")

        # Tags
        tags = getattr(vacancy, 'tags', None)
        if tags:
            parts.append(f"Tags: {', '.join(tags)}")

        # Location
        if getattr(vacancy, 'location', None):
            parts.append(f"Location: {vacancy.location}")

        # Employment type
        if getattr(vacancy, 'employment_type', None):
            parts.append(f"Employment type: {vacancy.employment_type}")

        if not parts:
            return "Unknown"

        return "\n".join(parts)

    async def generate_embedding(self, text: str) -> Optional[List[float]]:
        """Generate embedding for text."""
        if not text or not text.strip():
            return None

        # Check cache first
        cache_key = self._get_cache_key(text)
        cached = await self._get_cached_embedding(cache_key)
        if cached:
            return cached

        # Generate new embedding
        response = await self.client.embeddings.create(
            model="text-embedding-ada-002",
            input=text
        )

        embedding = response.data[0].embedding

        # Cache the result
        await self._set_cached_embedding(cache_key, embedding)

        return embedding

    async def generate_entity_embedding(self, entity) -> Optional[List[float]]:
        """Generate embedding for entity."""
        text = self._build_entity_text(entity)
        return await self.generate_embedding(text)

    async def generate_vacancy_embedding(self, vacancy) -> Optional[List[float]]:
        """Generate embedding for vacancy."""
        text = self._build_vacancy_text(vacancy)
        return await self.generate_embedding(text)

    async def batch_generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts."""
        if not texts:
            return []

        response = await self.client.embeddings.create(
            model="text-embedding-ada-002",
            input=texts
        )

        embeddings = [item.embedding for item in response.data]

        # Cache all results
        for text, embedding in zip(texts, embeddings):
            cache_key = self._get_cache_key(text)
            await self._set_cached_embedding(cache_key, embedding)

        return embeddings


class SimilaritySearchService:
    """Mock SimilaritySearchService for testing - replace with real import when implemented."""

    async def find_similar_entities(
        self,
        db,
        entity_id: int,
        org_id: int,
        limit: int = 10,
        min_score: float = 0.5
    ) -> List[SimilarityResult]:
        """Find similar entities by embedding similarity."""
        # Get source entity embedding
        result = await db.execute(f"SELECT embedding FROM entities WHERE id = {entity_id}")
        source_embedding = result.scalar()

        if source_embedding is None:
            return []

        # This would use pgvector's cosine similarity in real implementation
        # For now, return empty list
        return []

    async def find_matching_vacancies(
        self,
        db,
        entity_id: int,
        org_id: int,
        limit: int = 10,
        min_score: float = 0.5
    ) -> List[SimilarityResult]:
        """Find vacancies matching entity profile."""
        # Get entity embedding
        result = await db.execute(f"SELECT embedding FROM entities WHERE id = {entity_id}")
        entity_embedding = result.scalar()

        if entity_embedding is None:
            return []

        return []

    async def update_entity_embedding(self, db, entity) -> bool:
        """Update entity's embedding."""
        from api.services.embedding_service import embedding_service

        embedding = await embedding_service.generate_entity_embedding(entity)

        if embedding is None:
            return False

        entity.embedding = embedding
        entity.embedding_updated_at = datetime.utcnow()
        await db.commit()

        return True

    async def update_vacancy_embedding(self, db, vacancy) -> bool:
        """Update vacancy's embedding."""
        from api.services.embedding_service import embedding_service

        embedding = await embedding_service.generate_vacancy_embedding(vacancy)

        if embedding is None:
            return False

        vacancy.embedding = embedding
        vacancy.embedding_updated_at = datetime.utcnow()
        await db.commit()

        return True


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_entity():
    """Create a mock entity for testing."""
    entity = MagicMock()
    entity.id = 1
    entity.name = "John Doe"
    entity.position = "Senior Python Developer"
    entity.company = "Tech Corp"
    entity.tags = ["python", "fastapi", "postgresql"]
    entity.extra_data = {
        "ai_profile": {
            "skills": ["Python", "FastAPI", "PostgreSQL", "Redis"],
            "specialization": "backend",
            "level": "senior",
            "experience_years": 5,
            "summary": "Experienced backend developer"
        }
    }
    entity.ai_summary = "Strong Python developer with 5 years experience"
    entity.embedding = None
    entity.embedding_updated_at = None
    return entity


@pytest.fixture
def mock_vacancy():
    """Create a mock vacancy for testing."""
    vacancy = MagicMock()
    vacancy.id = 1
    vacancy.title = "Senior Backend Developer"
    vacancy.description = "We are looking for experienced backend developer"
    vacancy.requirements = "5+ years Python, FastAPI experience"
    vacancy.experience_level = "senior"
    vacancy.tags = ["python", "backend", "fastapi"]
    vacancy.location = "Remote"
    vacancy.employment_type = "full-time"
    vacancy.embedding = None
    vacancy.embedding_updated_at = None
    return vacancy


@pytest.fixture
def sample_embedding():
    """Create a sample embedding vector."""
    return [0.1] * EMBEDDING_DIMENSIONS


@pytest.fixture
def embedding_service():
    """Create EmbeddingService instance."""
    return EmbeddingService()


@pytest.fixture
def similarity_service():
    """Create SimilaritySearchService instance."""
    return SimilaritySearchService()


# =============================================================================
# EmbeddingService Tests
# =============================================================================

class TestEmbeddingService:
    """Tests for EmbeddingService."""

    def test_build_entity_text(self, embedding_service, mock_entity):
        """Test building text from entity."""
        text = embedding_service._build_entity_text(mock_entity)

        assert "John Doe" in text
        assert "Senior Python Developer" in text
        assert "Tech Corp" in text
        assert "python" in text.lower()
        assert "fastapi" in text.lower()
        assert "backend" in text.lower()
        assert "senior" in text.lower()

    def test_build_entity_text_minimal(self, embedding_service):
        """Test building text from minimal entity."""
        entity = MagicMock()
        entity.name = "Jane"
        entity.position = None
        entity.company = None
        entity.tags = None
        entity.extra_data = None
        entity.ai_summary = None

        text = embedding_service._build_entity_text(entity)
        assert text == "Name: Jane"

    def test_build_vacancy_text(self, embedding_service, mock_vacancy):
        """Test building text from vacancy."""
        text = embedding_service._build_vacancy_text(mock_vacancy)

        assert "Senior Backend Developer" in text
        assert "backend developer" in text.lower()
        assert "python" in text.lower()
        assert "senior" in text.lower()
        assert "Remote" in text

    def test_get_cache_key(self, embedding_service):
        """Test cache key generation."""
        key1 = embedding_service._get_cache_key("test text")
        key2 = embedding_service._get_cache_key("test text")
        key3 = embedding_service._get_cache_key("different text")

        assert key1 == key2
        assert key1 != key3
        assert key1.startswith("embedding:")

    @pytest.mark.asyncio
    async def test_generate_embedding_empty_text(self, embedding_service):
        """Test that empty text returns None."""
        result = await embedding_service.generate_embedding("")
        assert result is None

        result = await embedding_service.generate_embedding("   ")
        assert result is None

    @pytest.mark.asyncio
    async def test_generate_embedding_with_cache(self, embedding_service, sample_embedding):
        """Test embedding generation with caching."""
        with patch.object(embedding_service, '_get_cached_embedding', new_callable=AsyncMock) as mock_cache:
            mock_cache.return_value = sample_embedding

            result = await embedding_service.generate_embedding("test text")

            assert result == sample_embedding
            mock_cache.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_embedding_cache_miss(self, embedding_service, sample_embedding):
        """Test embedding generation on cache miss."""
        mock_response = MagicMock()
        mock_response.data = [MagicMock(embedding=sample_embedding)]

        with patch.object(embedding_service, '_get_cached_embedding', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            with patch.object(embedding_service, '_set_cached_embedding', new_callable=AsyncMock) as mock_set:
                with patch.object(embedding_service, '_client', MagicMock()) as mock_client:  # client — свойство без deleter, патчим то, что оно отдаёт
                    mock_client.embeddings.create = AsyncMock(return_value=mock_response)

                    result = await embedding_service.generate_embedding("test text")

                    assert result == sample_embedding
                    mock_set.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_entity_embedding(self, embedding_service, mock_entity, sample_embedding):
        """Test entity embedding generation."""
        with patch.object(embedding_service, 'generate_embedding', new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = sample_embedding

            result = await embedding_service.generate_entity_embedding(mock_entity)

            assert result == sample_embedding
            mock_gen.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_vacancy_embedding(self, embedding_service, mock_vacancy, sample_embedding):
        """Test vacancy embedding generation."""
        with patch.object(embedding_service, 'generate_embedding', new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = sample_embedding

            result = await embedding_service.generate_vacancy_embedding(mock_vacancy)

            assert result == sample_embedding
            mock_gen.assert_called_once()

    @pytest.mark.asyncio
    async def test_batch_generate_embeddings(self, embedding_service, sample_embedding):
        """Test batch embedding generation."""
        texts = ["text1", "text2", "text3"]
        mock_response = MagicMock()
        mock_response.data = [
            MagicMock(embedding=sample_embedding),
            MagicMock(embedding=sample_embedding),
            MagicMock(embedding=sample_embedding)
        ]

        with patch.object(embedding_service, '_client', MagicMock()) as mock_client:  # client — свойство без deleter, патчим то, что оно отдаёт
            mock_client.embeddings.create = AsyncMock(return_value=mock_response)

            with patch.object(embedding_service, '_set_cached_embedding', new_callable=AsyncMock):
                results = await embedding_service.batch_generate_embeddings(texts)

                assert len(results) == 3
                assert all(r == sample_embedding for r in results)


# =============================================================================
# SimilaritySearchService Tests
# =============================================================================

class TestSimilaritySearchService:
    """Tests for SimilaritySearchService."""

    def test_similarity_result_to_dict(self):
        """Test SimilarityResult serialization."""
        result = SimilarityResult(
            id=1,
            name="Test",
            score=0.85,
            type="entity",
            position="Developer",
            status="active",
            tags=["python"]
        )

        data = result.to_dict()

        assert data["id"] == 1
        assert data["name"] == "Test"
        assert data["score"] == 85  # Converted to percentage
        assert data["type"] == "entity"
        assert data["position"] == "Developer"
        assert data["tags"] == ["python"]

    @pytest.mark.asyncio
    async def test_find_similar_entities_no_embedding(self, similarity_service):
        """Test that search returns empty when source has no embedding."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = None
        mock_db.execute.return_value = mock_result

        results = await similarity_service.find_similar_entities(
            db=mock_db,
            entity_id=1,
            org_id=1
        )

        assert results == []

    @pytest.mark.asyncio
    async def test_find_matching_vacancies_no_embedding(self, similarity_service):
        """Test that search returns empty when entity has no embedding."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = None
        mock_db.execute.return_value = mock_result

        results = await similarity_service.find_matching_vacancies(
            db=mock_db,
            entity_id=1,
            org_id=1
        )

        assert results == []

    @pytest.mark.asyncio
    async def test_update_entity_embedding_success(self, similarity_service, mock_entity, sample_embedding):
        """Test successful entity embedding update."""
        mock_db = AsyncMock()

        with patch('api.services.embedding_service.embedding_service') as mock_service:
            mock_service.generate_entity_embedding = AsyncMock(return_value=sample_embedding)

            # Import the patched module
            with patch.dict('sys.modules', {'api.services.embedding_service': MagicMock(embedding_service=mock_service)}):
                result = await similarity_service.update_entity_embedding(mock_db, mock_entity)

                assert result is True
                assert mock_entity.embedding == sample_embedding
                assert mock_entity.embedding_updated_at is not None
                mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_entity_embedding_failure(self, similarity_service, mock_entity):
        """Test entity embedding update failure."""
        mock_db = AsyncMock()

        with patch('api.services.embedding_service.embedding_service') as mock_service:
            mock_service.generate_entity_embedding = AsyncMock(return_value=None)

            with patch.dict('sys.modules', {'api.services.embedding_service': MagicMock(embedding_service=mock_service)}):
                result = await similarity_service.update_entity_embedding(mock_db, mock_entity)

                assert result is False
                mock_db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_vacancy_embedding_success(self, similarity_service, mock_vacancy, sample_embedding):
        """Test successful vacancy embedding update."""
        mock_db = AsyncMock()

        with patch('api.services.embedding_service.embedding_service') as mock_service:
            mock_service.generate_vacancy_embedding = AsyncMock(return_value=sample_embedding)

            with patch.dict('sys.modules', {'api.services.embedding_service': MagicMock(embedding_service=mock_service)}):
                result = await similarity_service.update_vacancy_embedding(mock_db, mock_vacancy)

                assert result is True
                assert mock_vacancy.embedding == sample_embedding
                assert mock_vacancy.embedding_updated_at is not None
                mock_db.commit.assert_called_once()


# =============================================================================
# Integration Tests
# =============================================================================

class TestEmbeddingsIntegration:
    """Integration tests for embeddings system."""

    def test_embedding_dimensions(self):
        """Test that embedding dimensions are correct."""
        assert EMBEDDING_DIMENSIONS == 1536

    def test_entity_text_contains_key_fields(self, embedding_service, mock_entity):
        """Test that entity text contains all important fields."""
        text = embedding_service._build_entity_text(mock_entity)

        # Should contain name
        assert mock_entity.name in text
        # Should contain skills
        for skill in mock_entity.tags:
            assert skill in text.lower()
        # Should contain level
        assert "senior" in text.lower()

    def test_vacancy_text_contains_key_fields(self, embedding_service, mock_vacancy):
        """Test that vacancy text contains all important fields."""
        text = embedding_service._build_vacancy_text(mock_vacancy)

        # Should contain title
        assert mock_vacancy.title in text
        # Should contain requirements
        assert "python" in text.lower()
        # Should contain level
        assert mock_vacancy.experience_level in text.lower()


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_entity_text_with_none_values(self, embedding_service):
        """Test entity text building with all None values."""
        entity = MagicMock()
        entity.name = None
        entity.position = None
        entity.company = None
        entity.tags = None
        entity.extra_data = None
        entity.ai_summary = None

        text = embedding_service._build_entity_text(entity)
        assert text == "Unknown"

    def test_vacancy_text_with_none_values(self, embedding_service):
        """Test vacancy text building with all None values."""
        vacancy = MagicMock()
        vacancy.title = None
        vacancy.description = None
        vacancy.requirements = None
        vacancy.experience_level = None
        vacancy.tags = None
        vacancy.location = None
        vacancy.employment_type = None

        text = embedding_service._build_vacancy_text(vacancy)
        assert text == "Unknown"

    def test_vacancy_text_truncates_long_description(self, embedding_service):
        """Test that long descriptions are truncated."""
        vacancy = MagicMock()
        vacancy.title = "Test"
        vacancy.description = "x" * 1000  # Very long description
        vacancy.requirements = "y" * 1000  # Very long requirements
        vacancy.experience_level = None
        vacancy.tags = None
        vacancy.location = None
        vacancy.employment_type = None

        text = embedding_service._build_vacancy_text(vacancy)
        # Should be truncated to prevent token overflow
        assert len(text) < 2000

    @pytest.mark.asyncio
    async def test_batch_empty_list(self, embedding_service):
        """Test batch generation with empty list."""
        results = await embedding_service.batch_generate_embeddings([])
        assert results == []

    def test_similarity_result_score_conversion(self):
        """Test score conversion to percentage."""
        # Test various scores
        assert SimilarityResult(1, "a", 0.0, "e").to_dict()["score"] == 0
        assert SimilarityResult(1, "a", 0.5, "e").to_dict()["score"] == 50
        assert SimilarityResult(1, "a", 1.0, "e").to_dict()["score"] == 100
        # Проценты отбрасывают дробную часть (int), как и в test_similarity_result_score_rounding (0.999 → 99)
        assert SimilarityResult(1, "a", 0.856, "e").to_dict()["score"] == 85


# =============================================================================
# Cache Behavior Tests
# =============================================================================

class TestCacheBehavior:
    """Tests for embedding caching behavior."""

    def test_cache_key_deterministic(self, embedding_service):
        """Test that cache keys are deterministic."""
        text = "same text"
        key1 = embedding_service._get_cache_key(text)
        key2 = embedding_service._get_cache_key(text)
        assert key1 == key2

    def test_cache_key_different_for_different_text(self, embedding_service):
        """Test that different texts produce different keys."""
        key1 = embedding_service._get_cache_key("text one")
        key2 = embedding_service._get_cache_key("text two")
        assert key1 != key2

    def test_cache_key_prefix(self, embedding_service):
        """Test that cache keys have correct prefix."""
        key = embedding_service._get_cache_key("any text")
        assert key.startswith("embedding:")

    @pytest.mark.asyncio
    async def test_cache_miss_returns_none(self, embedding_service):
        """Test that cache miss returns None when no Redis."""
        # No Redis configured
        embedding_service._redis = None
        result = await embedding_service._get_cached_embedding("any_key")
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_set_does_nothing_without_redis(self, embedding_service, sample_embedding):
        """Test that cache set does nothing without Redis."""
        embedding_service._redis = None
        # Should not raise
        await embedding_service._set_cached_embedding("key", sample_embedding)


# =============================================================================
# Text Building Edge Cases
# =============================================================================

class TestTextBuildingEdgeCases:
    """Additional edge cases for text building."""

    def test_entity_with_empty_ai_profile(self, embedding_service):
        """Test entity with empty ai_profile."""
        entity = MagicMock()
        entity.name = "Test"
        entity.position = None
        entity.company = None
        entity.tags = None
        entity.extra_data = {"ai_profile": {}}
        entity.ai_summary = None

        text = embedding_service._build_entity_text(entity)
        assert "Name: Test" in text

    def test_entity_with_partial_ai_profile(self, embedding_service):
        """Test entity with partial ai_profile."""
        entity = MagicMock()
        entity.name = "Test"
        entity.position = None
        entity.company = None
        entity.tags = None
        entity.extra_data = {
            "ai_profile": {
                "skills": ["Python"],
                "level": "middle"
            }
        }
        entity.ai_summary = None

        text = embedding_service._build_entity_text(entity)
        assert "Python" in text
        assert "middle" in text.lower()

    def test_vacancy_with_only_title(self, embedding_service):
        """Test vacancy with only title."""
        vacancy = MagicMock()
        vacancy.title = "Developer"
        vacancy.description = None
        vacancy.requirements = None
        vacancy.experience_level = None
        vacancy.tags = None
        vacancy.location = None
        vacancy.employment_type = None

        text = embedding_service._build_vacancy_text(vacancy)
        assert "Title: Developer" in text

    def test_vacancy_description_truncation_boundary(self, embedding_service):
        """Test vacancy description truncation at exact boundary."""
        vacancy = MagicMock()
        vacancy.title = "Test"
        vacancy.description = "a" * 500  # Exactly 500 chars
        vacancy.requirements = None
        vacancy.experience_level = None
        vacancy.tags = None
        vacancy.location = None
        vacancy.employment_type = None

        text = embedding_service._build_vacancy_text(vacancy)
        # Should contain full description (no truncation needed)
        assert "a" * 500 in text

    def test_vacancy_description_truncation_over_boundary(self, embedding_service):
        """Test vacancy description truncation over boundary."""
        vacancy = MagicMock()
        vacancy.title = "Test"
        vacancy.description = "a" * 600  # Over 500 chars
        vacancy.requirements = None
        vacancy.experience_level = None
        vacancy.tags = None
        vacancy.location = None
        vacancy.employment_type = None

        text = embedding_service._build_vacancy_text(vacancy)
        # Should be truncated
        description_part = text.split("Description: ")[1].split("\n")[0]
        assert len(description_part) == 500


# =============================================================================
# Similarity Result Tests
# =============================================================================

class TestSimilarityResultAdditional:
    """Additional tests for SimilarityResult."""

    def test_similarity_result_with_none_optional_fields(self):
        """Test SimilarityResult with None optional fields."""
        result = SimilarityResult(
            id=1,
            name="Test",
            score=0.75,
            type="entity"
        )

        data = result.to_dict()
        assert data["id"] == 1
        assert data["name"] == "Test"
        assert data["score"] == 75
        assert data["type"] == "entity"
        assert data["position"] is None
        assert data["status"] is None
        assert data["tags"] is None

    def test_similarity_result_score_rounding(self):
        """Test score rounding behavior."""
        # Test that int() truncates (not rounds)
        result1 = SimilarityResult(1, "a", 0.999, "e")
        assert result1.to_dict()["score"] == 99  # 99.9 truncated to 99

        result2 = SimilarityResult(1, "a", 0.991, "e")
        assert result2.to_dict()["score"] == 99  # 99.1 truncated to 99

        result3 = SimilarityResult(1, "a", 0.001, "e")
        assert result3.to_dict()["score"] == 0  # 0.1 truncated to 0

    def test_similarity_result_with_empty_tags(self):
        """Test SimilarityResult with empty tags list."""
        result = SimilarityResult(
            id=1,
            name="Test",
            score=0.5,
            type="entity",
            tags=[]
        )

        data = result.to_dict()
        assert data["tags"] == []
