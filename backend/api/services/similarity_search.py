"""
Similarity Search Service - unified search using embeddings.

Features:
- Find similar candidates (candidate <-> candidate)
- Find matching vacancies for candidate (candidate <-> vacancy)
- Find matching candidates for vacancy (vacancy <-> candidate)
- All searches use cosine similarity via pgvector
- Results in <100ms

Requirements:
- pgvector extension enabled in PostgreSQL
- Entity and Vacancy models need 'embedding' column (Vector type)
- EmbeddingService for generating embeddings

Usage:
    from api.services.similarity_search import similarity_search

    # Find similar candidates
    results = await similarity_search.find_similar_entities(db, entity_id, org_id)

    # Find vacancies for candidate
    results = await similarity_search.find_matching_vacancies(db, entity_id, org_id)

    # Find candidates for vacancy
    results = await similarity_search.find_matching_candidates(db, vacancy_id, org_id)
"""

import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.database import Entity, Vacancy, EntityType, EntityStatus, VacancyStatus

logger = logging.getLogger("hr-analyzer.similarity-search")


@dataclass
class SimilarityResult:
    """Result of similarity search."""
    id: int
    name: str
    score: float  # 0.0 - 1.0 (1.0 = identical)
    type: str  # "entity" or "vacancy"

    # Additional info
    position: Optional[str] = None
    status: Optional[str] = None
    tags: List[str] = field(default_factory=list)

    # Extra fields for display
    email: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "score": round(self.score * 100),  # Convert to percentage
            "type": self.type,
            "position": self.position,
            "status": self.status,
            "tags": self.tags,
            "email": self.email,
            "phone": self.phone,
            "company": self.company,
        }


class SimilaritySearchService:
    """
    Unified similarity search service using embeddings.

    Uses pgvector for fast cosine similarity search.
    Cosine distance operator in pgvector: <=>
    Similarity = 1 - distance (so 1 = identical, 0 = orthogonal)
    """

    def __init__(self):
        """Initialize the similarity search service."""
        self._embedding_service = None

    @property
    def embedding_service(self):
        """Lazy load embedding service to avoid circular imports."""
        if self._embedding_service is None:
            try:
                from .embedding_service import embedding_service
                self._embedding_service = embedding_service
            except ImportError:
                logger.warning("EmbeddingService not available - similarity search will fail")
                self._embedding_service = None
        return self._embedding_service

    async def _check_embedding_column_exists(self, db: AsyncSession, table: str) -> bool:
        """Check if embedding column exists in the table."""
        try:
            query = text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = :table_name AND column_name = 'embedding'
            """)
            result = await db.execute(query, {"table_name": table})
            return result.scalar() is not None
        except Exception as e:
            logger.error(f"Error checking embedding column: {e}")
            return False

    async def find_similar_entities(
        self,
        db: AsyncSession,
        entity_id: int,
        org_id: int,
        limit: int = 10,
        min_score: float = 0.3,
        exclude_statuses: Optional[List[EntityStatus]] = None
    ) -> List[SimilarityResult]:
        """
        Find similar entities (candidates) to the given entity.
        Uses cosine similarity on embeddings.

        Args:
            db: Database session
            entity_id: Source entity ID
            org_id: Organization ID for filtering
            limit: Maximum number of results
            min_score: Minimum similarity score (0.0 - 1.0)
            exclude_statuses: Entity statuses to exclude from results

        Returns:
            List of SimilarityResult sorted by score descending
        """
        if exclude_statuses is None:
            exclude_statuses = [EntityStatus.rejected, EntityStatus.hired]

        # Check if embedding column exists
        if not await self._check_embedding_column_exists(db, "entities"):
            logger.warning("Embedding column not found in entities table. Run migration first.")
            return []

        # Get source entity embedding
        source_query = select(Entity).where(Entity.id == entity_id)
        source_result = await db.execute(source_query)
        source_entity = source_result.scalar_one_or_none()

        if source_entity is None:
            logger.warning(f"Entity {entity_id} not found")
            return []

        # Check if entity has embedding
        if not hasattr(source_entity, 'embedding') or source_entity.embedding is None:
            logger.warning(f"Entity {entity_id} has no embedding")
            return []

        # Build exclude statuses for SQL (as comma-separated string for ANY())
        exclude_status_values = [s.value for s in exclude_statuses]

        # Find similar entities using pgvector cosine similarity
        # Note: pgvector uses <=> for cosine distance, so 1 - distance = similarity
        # We use raw SQL for pgvector operations as SQLAlchemy doesn't have native support
        query = text("""
            SELECT
                e.id,
                e.name,
                e.position,
                e.status,
                e.tags,
                e.email,
                e.phone,
                e.company,
                1 - (e.embedding <=> :source_embedding::vector) as similarity
            FROM entities e
            WHERE e.id != :entity_id
              AND e.org_id = :org_id
              AND e.type = :entity_type
              AND e.status != ALL(:exclude_statuses)
              AND e.embedding IS NOT NULL
              AND 1 - (e.embedding <=> :source_embedding::vector) >= :min_score
            ORDER BY similarity DESC
            LIMIT :limit
        """)

        try:
            # Convert embedding to string format for pgvector
            embedding_str = f"[{','.join(str(x) for x in source_entity.embedding)}]"

            result = await db.execute(
                query,
                {
                    "source_embedding": embedding_str,
                    "entity_id": entity_id,
                    "org_id": org_id,
                    "entity_type": EntityType.candidate.value,
                    "exclude_statuses": exclude_status_values,
                    "min_score": min_score,
                    "limit": limit
                }
            )

            rows = result.fetchall()

            return [
                SimilarityResult(
                    id=row.id,
                    name=row.name,
                    score=float(row.similarity),
                    type="entity",
                    position=row.position,
                    status=row.status,
                    tags=row.tags or [],
                    email=row.email,
                    phone=row.phone,
                    company=row.company,
                )
                for row in rows
            ]

        except Exception as e:
            logger.error(f"Error finding similar entities: {e}")
            return []

    async def find_matching_vacancies(
        self,
        db: AsyncSession,
        entity_id: int,
        org_id: int,
        limit: int = 10,
        min_score: float = 0.3
    ) -> List[SimilarityResult]:
        """
        Find matching vacancies for a candidate.
        Uses cosine similarity between entity and vacancy embeddings.

        Args:
            db: Database session
            entity_id: Candidate entity ID
            org_id: Organization ID for filtering
            limit: Maximum number of results
            min_score: Minimum similarity score (0.0 - 1.0)

        Returns:
            List of SimilarityResult sorted by score descending
        """
        # Check if embedding columns exist
        if not await self._check_embedding_column_exists(db, "entities"):
            logger.warning("Embedding column not found in entities table")
            return []
        if not await self._check_embedding_column_exists(db, "vacancies"):
            logger.warning("Embedding column not found in vacancies table")
            return []

        # Get entity embedding
        entity_query = select(Entity).where(Entity.id == entity_id)
        entity_result = await db.execute(entity_query)
        entity = entity_result.scalar_one_or_none()

        if entity is None:
            logger.warning(f"Entity {entity_id} not found")
            return []

        if not hasattr(entity, 'embedding') or entity.embedding is None:
            logger.warning(f"Entity {entity_id} has no embedding")
            return []

        # Find matching vacancies
        query = text("""
            SELECT
                v.id,
                v.title as name,
                v.experience_level as position,
                v.status,
                v.tags,
                v.location,
                v.salary_min,
                v.salary_max,
                v.salary_currency,
                1 - (v.embedding <=> :entity_embedding::vector) as similarity
            FROM vacancies v
            WHERE v.org_id = :org_id
              AND v.status = :vacancy_status
              AND v.embedding IS NOT NULL
              AND 1 - (v.embedding <=> :entity_embedding::vector) >= :min_score
            ORDER BY similarity DESC
            LIMIT :limit
        """)

        try:
            # Convert embedding to string format for pgvector
            embedding_str = f"[{','.join(str(x) for x in entity.embedding)}]"

            result = await db.execute(
                query,
                {
                    "entity_embedding": embedding_str,
                    "org_id": org_id,
                    "vacancy_status": VacancyStatus.open.value,
                    "min_score": min_score,
                    "limit": limit
                }
            )

            rows = result.fetchall()

            return [
                SimilarityResult(
                    id=row.id,
                    name=row.name,
                    score=float(row.similarity),
                    type="vacancy",
                    position=row.position,
                    status=row.status,
                    tags=row.tags or [],
                )
                for row in rows
            ]

        except Exception as e:
            logger.error(f"Error finding matching vacancies: {e}")
            return []

    async def find_matching_candidates(
        self,
        db: AsyncSession,
        vacancy_id: int,
        org_id: int,
        limit: int = 10,
        min_score: float = 0.3,
        exclude_statuses: Optional[List[EntityStatus]] = None
    ) -> List[SimilarityResult]:
        """
        Find matching candidates for a vacancy.
        Uses cosine similarity between vacancy and entity embeddings.

        Args:
            db: Database session
            vacancy_id: Target vacancy ID
            org_id: Organization ID for filtering
            limit: Maximum number of results
            min_score: Minimum similarity score (0.0 - 1.0)
            exclude_statuses: Entity statuses to exclude from results

        Returns:
            List of SimilarityResult sorted by score descending
        """
        if exclude_statuses is None:
            exclude_statuses = [EntityStatus.rejected, EntityStatus.hired]

        # Check if embedding columns exist
        if not await self._check_embedding_column_exists(db, "vacancies"):
            logger.warning("Embedding column not found in vacancies table")
            return []
        if not await self._check_embedding_column_exists(db, "entities"):
            logger.warning("Embedding column not found in entities table")
            return []

        # Get vacancy embedding
        vacancy_query = select(Vacancy).where(Vacancy.id == vacancy_id)
        vacancy_result = await db.execute(vacancy_query)
        vacancy = vacancy_result.scalar_one_or_none()

        if vacancy is None:
            logger.warning(f"Vacancy {vacancy_id} not found")
            return []

        if not hasattr(vacancy, 'embedding') or vacancy.embedding is None:
            logger.warning(f"Vacancy {vacancy_id} has no embedding")
            return []

        # Build exclude statuses for SQL (as list for ANY())
        exclude_status_values = [s.value for s in exclude_statuses]

        # Find matching candidates
        query = text("""
            SELECT
                e.id,
                e.name,
                e.position,
                e.status,
                e.tags,
                e.email,
                e.phone,
                e.company,
                1 - (e.embedding <=> :vacancy_embedding::vector) as similarity
            FROM entities e
            WHERE e.org_id = :org_id
              AND e.type = :entity_type
              AND e.status != ALL(:exclude_statuses)
              AND e.embedding IS NOT NULL
              AND 1 - (e.embedding <=> :vacancy_embedding::vector) >= :min_score
            ORDER BY similarity DESC
            LIMIT :limit
        """)

        try:
            # Convert embedding to string format for pgvector
            embedding_str = f"[{','.join(str(x) for x in vacancy.embedding)}]"

            result = await db.execute(
                query,
                {
                    "vacancy_embedding": embedding_str,
                    "org_id": org_id,
                    "entity_type": EntityType.candidate.value,
                    "exclude_statuses": exclude_status_values,
                    "min_score": min_score,
                    "limit": limit
                }
            )

            rows = result.fetchall()

            return [
                SimilarityResult(
                    id=row.id,
                    name=row.name,
                    score=float(row.similarity),
                    type="entity",
                    position=row.position,
                    status=row.status,
                    tags=row.tags or [],
                    email=row.email,
                    phone=row.phone,
                    company=row.company,
                )
                for row in rows
            ]

        except Exception as e:
            logger.error(f"Error finding matching candidates: {e}")
            return []

    async def update_entity_embedding(
        self,
        db: AsyncSession,
        entity: Entity
    ) -> bool:
        """
        Generate and store embedding for entity.

        Args:
            db: Database session
            entity: Entity to update embedding for

        Returns:
            True if successful, False otherwise
        """
        if self.embedding_service is None:
            logger.error("EmbeddingService not available")
            return False

        try:
            embedding = await self.embedding_service.generate_entity_embedding(entity)
            if embedding:
                entity.embedding = embedding
                entity.embedding_updated_at = datetime.utcnow()
                await db.commit()
                logger.info(f"Updated embedding for entity {entity.id}")
                return True
            else:
                logger.warning(f"Failed to generate embedding for entity {entity.id}")
                return False
        except Exception as e:
            logger.error(f"Failed to update entity embedding: {e}")
            await db.rollback()
            return False

    async def update_vacancy_embedding(
        self,
        db: AsyncSession,
        vacancy: Vacancy
    ) -> bool:
        """
        Generate and store embedding for vacancy.

        Args:
            db: Database session
            vacancy: Vacancy to update embedding for

        Returns:
            True if successful, False otherwise
        """
        if self.embedding_service is None:
            logger.error("EmbeddingService not available")
            return False

        try:
            embedding = await self.embedding_service.generate_vacancy_embedding(vacancy)
            if embedding:
                vacancy.embedding = embedding
                vacancy.embedding_updated_at = datetime.utcnow()
                await db.commit()
                logger.info(f"Updated embedding for vacancy {vacancy.id}")
                return True
            else:
                logger.warning(f"Failed to generate embedding for vacancy {vacancy.id}")
                return False
        except Exception as e:
            logger.error(f"Failed to update vacancy embedding: {e}")
            await db.rollback()
            return False

    async def batch_update_entity_embeddings(
        self,
        db: AsyncSession,
        org_id: int,
        batch_size: int = 50
    ) -> Dict[str, int]:
        """
        Batch update embeddings for all entities in an organization.

        Args:
            db: Database session
            org_id: Organization ID
            batch_size: Number of entities to process at once

        Returns:
            Dict with counts: {"updated": N, "failed": M, "skipped": K}
        """
        if self.embedding_service is None:
            logger.error("EmbeddingService not available")
            return {"updated": 0, "failed": 0, "skipped": 0, "error": "EmbeddingService not available"}

        stats = {"updated": 0, "failed": 0, "skipped": 0}

        # Get all entities without embeddings
        query = select(Entity).where(
            Entity.org_id == org_id,
            Entity.type == EntityType.candidate
        )
        result = await db.execute(query)
        entities = result.scalars().all()

        for entity in entities:
            # Skip if already has recent embedding
            if hasattr(entity, 'embedding') and entity.embedding is not None:
                if hasattr(entity, 'embedding_updated_at') and entity.embedding_updated_at:
                    # Skip if updated within last 24 hours
                    age = datetime.utcnow() - entity.embedding_updated_at
                    if age.total_seconds() < 86400:
                        stats["skipped"] += 1
                        continue

            success = await self.update_entity_embedding(db, entity)
            if success:
                stats["updated"] += 1
            else:
                stats["failed"] += 1

        logger.info(f"Batch update completed for org {org_id}: {stats}")
        return stats

    async def batch_update_vacancy_embeddings(
        self,
        db: AsyncSession,
        org_id: int,
        batch_size: int = 50
    ) -> Dict[str, int]:
        """
        Batch update embeddings for all vacancies in an organization.

        Args:
            db: Database session
            org_id: Organization ID
            batch_size: Number of vacancies to process at once

        Returns:
            Dict with counts: {"updated": N, "failed": M, "skipped": K}
        """
        if self.embedding_service is None:
            logger.error("EmbeddingService not available")
            return {"updated": 0, "failed": 0, "skipped": 0, "error": "EmbeddingService not available"}

        stats = {"updated": 0, "failed": 0, "skipped": 0}

        # Get all active vacancies
        query = select(Vacancy).where(
            Vacancy.org_id == org_id,
            Vacancy.status.in_([VacancyStatus.open, VacancyStatus.draft])
        )
        result = await db.execute(query)
        vacancies = result.scalars().all()

        for vacancy in vacancies:
            # Skip if already has recent embedding
            if hasattr(vacancy, 'embedding') and vacancy.embedding is not None:
                if hasattr(vacancy, 'embedding_updated_at') and vacancy.embedding_updated_at:
                    # Skip if updated within last 24 hours
                    age = datetime.utcnow() - vacancy.embedding_updated_at
                    if age.total_seconds() < 86400:
                        stats["skipped"] += 1
                        continue

            success = await self.update_vacancy_embedding(db, vacancy)
            if success:
                stats["updated"] += 1
            else:
                stats["failed"] += 1

        logger.info(f"Batch update completed for org {org_id} vacancies: {stats}")
        return stats


# Global service instance
similarity_search = SimilaritySearchService()
