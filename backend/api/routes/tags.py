"""Entity tags / labels endpoints."""
import re
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from pydantic import BaseModel, field_validator

from ..models.database import (
    EntityTag, Entity, User, OrgMember, entity_tag_association,
    NameTag, entity_name_tag_association,
)
from ..database import get_db
from ..services.auth import get_current_user

router = APIRouter()


_HTML_TAG_RE = re.compile(r"<[^>]*>")

# Тип метки. С 21.09.2026 метки — ТОЛЬКО сорсеры (кто привёл кандидата): всё,
# что вписали в метку, считается сорсером. 'general' остаётся допустимым в
# фильтре списка ради старых клиентов, но новых таких меток не бывает — create
# и update ставят 'sourcer' сами. Теги у ФИО — отдельный справочник (ниже).
TAG_KINDS = ("general", "sourcer")
LABEL_KIND = "sourcer"


class TagCreate(BaseModel):
    name: str
    color: str = "#3b82f6"
    # Принимаем ради старых клиентов, но игнорируем: метка всегда сорсер.
    kind: str | None = None

    @field_validator("name")
    @classmethod
    def _clean_name(cls, v: str) -> str:
        if not v:
            raise ValueError("name cannot be empty")
        cleaned = _HTML_TAG_RE.sub("", v).strip()
        if not cleaned:
            raise ValueError("name cannot be empty")
        if len(cleaned) > 80:
            raise ValueError("name must be 80 characters or fewer")
        return cleaned


class TagOut(BaseModel):
    id: int
    org_id: int
    name: str
    color: str
    created_by: int | None = None
    created_at: datetime | None = None
    archived_at: datetime | None = None
    kind: str = "general"
    # Заполняется только там, где метка отдаётся В КОНТЕКСТЕ кандидата
    # (get_entity_tags): признак живёт на связи, а не на самой метке.
    show_at_name: bool = False

    class Config:
        from_attributes = True


class EntityTagAttach(BaseModel):
    """Тело простановки метки. show_at_name — наследство, игнорируется."""
    show_at_name: bool = False


async def _get_org_id(db: AsyncSession, user: User) -> int:
    result = await db.execute(
        select(OrgMember.org_id).where(OrgMember.user_id == user.id).limit(1)
    )
    org_id = result.scalar_one_or_none()
    if not org_id:
        raise HTTPException(404, "No organization")
    return org_id


@router.get("", response_model=list[TagOut])
async def list_tags(
    include_archived: bool = False,
    kind: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Метки организации для выбора. Скрытые («удалённые за ненадобностью») не
    отдаём: они больше не предлагаются в списке, но продолжают показываться на
    карточках кандидатов, которым уже проставлены (см. get_entity_tags).
    include_archived=true — для экрана управления метками."""
    org_id = await _get_org_id(db, current_user)
    query = select(EntityTag).where(EntityTag.org_id == org_id)
    if kind is not None:
        if kind not in TAG_KINDS:
            raise HTTPException(422, f"kind must be one of {TAG_KINDS}")
        query = query.where(EntityTag.kind == kind)
    if not include_archived:
        query = query.where(EntityTag.archived_at.is_(None))
    result = await db.execute(query.order_by(EntityTag.name))
    return list(result.scalars().all())


@router.post("", response_model=TagOut)
async def create_tag(
    data: TagCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new tag for the organization."""
    org_id = await _get_org_id(db, current_user)

    # Check for duplicate name
    existing = (await db.execute(
        select(EntityTag).where(
            EntityTag.org_id == org_id,
            EntityTag.name == data.name.strip(),
        )
    )).scalar_one_or_none()
    if existing is not None:
        if existing.archived_at is None:
            raise HTTPException(409, "Tag with this name already exists")
        # Метку с таким именем когда-то скрыли, а теперь заводят снова —
        # возвращаем её из архива вместо второй записи с тем же именем
        # (unique(org_id, name) второй всё равно не даст создать).
        existing.archived_at = None
        existing.color = data.color
        existing.kind = LABEL_KIND
        await db.commit()
        await db.refresh(existing)
        return existing

    tag = EntityTag(
        org_id=org_id,
        name=data.name.strip(),
        color=data.color,
        kind=LABEL_KIND,
        created_by=current_user.id,
    )
    db.add(tag)
    await db.commit()
    await db.refresh(tag)
    return tag


@router.delete("/{tag_id}")
async def delete_tag(
    tag_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """НАСТОЯЩЕЕ удаление: сносит метку и со ВСЕХ карточек разом (у entity_tags
    стоит ondelete=CASCADE). Интерфейс этим НЕ пользуется — кнопка «удалить за
    ненадобностью» вызывает /archive, чтобы у кандидатов метка осталась.
    Оставлено для чистки мусора вручную; вешать на кнопку без явного
    подтверждения «сорвать у всех» нельзя."""
    org_id = await _get_org_id(db, current_user)
    result = await db.execute(
        select(EntityTag).where(EntityTag.id == tag_id, EntityTag.org_id == org_id)
    )
    tag = result.scalar_one_or_none()
    if not tag:
        raise HTTPException(404, "Tag not found")

    await db.delete(tag)
    await db.commit()
    return {"ok": True}


class TagUpdate(BaseModel):
    # Только 'sourcer': «обычных» меток больше нет (21.09.2026).
    kind: str | None = None
    color: str | None = None

    @field_validator("kind")
    @classmethod
    def _check_kind(cls, v: str | None) -> str | None:
        if v is not None and v != LABEL_KIND:
            raise ValueError("метки — только сорсеры")
        return v


@router.patch("/{tag_id}", response_model=TagOut)
async def update_tag(
    tag_id: int,
    data: TagUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Поменять цвет метки (тип — только 'sourcer'). Имя не меняем — по нему
    метку узнают на карточках."""
    org_id = await _get_org_id(db, current_user)
    tag = (await db.execute(
        select(EntityTag).where(EntityTag.id == tag_id, EntityTag.org_id == org_id)
    )).scalar_one_or_none()
    if not tag:
        raise HTTPException(404, "Tag not found")
    if data.kind is not None:
        tag.kind = data.kind
    if data.color is not None:
        tag.color = data.color
    await db.commit()
    await db.refresh(tag)
    return tag


@router.post("/{tag_id}/archive", response_model=TagOut)
async def archive_tag(
    tag_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Убрать метку из списка выбора, НЕ трогая карточки кандидатов.

    Это и есть «удалить за ненадобностью» с точки зрения рекрутёра: метка
    перестаёт предлагаться при добавлении, но у тех, кому уже проставлена,
    остаётся — снять её оттуда можно крестиком на самой карточке.
    Идемпотентно: повторный вызов ничего не меняет.
    """
    org_id = await _get_org_id(db, current_user)
    tag = (await db.execute(
        select(EntityTag).where(EntityTag.id == tag_id, EntityTag.org_id == org_id)
    )).scalar_one_or_none()
    if not tag:
        raise HTTPException(404, "Tag not found")
    if tag.archived_at is None:
        tag.archived_at = datetime.utcnow()
        await db.commit()
        await db.refresh(tag)
    return tag


@router.post("/{tag_id}/restore", response_model=TagOut)
async def restore_tag(
    tag_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Вернуть скрытую метку в список выбора."""
    org_id = await _get_org_id(db, current_user)
    tag = (await db.execute(
        select(EntityTag).where(EntityTag.id == tag_id, EntityTag.org_id == org_id)
    )).scalar_one_or_none()
    if not tag:
        raise HTTPException(404, "Tag not found")
    if tag.archived_at is not None:
        tag.archived_at = None
        await db.commit()
        await db.refresh(tag)
    return tag


# ==================== Entity <-> Tag ====================

@router.get("/entities/{entity_id}/tags", response_model=list[TagOut])
async def get_entity_tags(
    entity_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all tags for an entity."""
    # Скоуп по воронкам: чужой кандидат не отвечает ничем, даже метками.
    from ..services.vacancy_scope import ensure_entity_visible
    await ensure_entity_visible(entity_id, current_user, db)
    org_id = await _get_org_id(db, current_user)

    # Verify entity belongs to org
    entity_result = await db.execute(
        select(Entity).where(Entity.id == entity_id, Entity.org_id == org_id)
    )
    entity = entity_result.scalar_one_or_none()
    if not entity:
        raise HTTPException(404, "Entity not found")

    # Теги у ФИО теперь в своём справочнике (/tags/entities/{id}/name-tags),
    # здесь — только метки; show_at_name в ответе всегда false.
    result = await db.execute(
        select(EntityTag)
        .join(entity_tag_association, EntityTag.id == entity_tag_association.c.tag_id)
        .where(entity_tag_association.c.entity_id == entity_id)
        .order_by(EntityTag.name)
    )
    return list(result.scalars().all())


@router.post("/entities/{entity_id}/tags/{tag_id}")
async def add_tag_to_entity(
    entity_id: int,
    tag_id: int,
    data: EntityTagAttach | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Повесить метку на кандидата.

    Тело (show_at_name) принимается ради старых клиентов и игнорируется: теги у
    ФИО с 21.09.2026 — отдельный справочник, метка всегда обычная связь.
    """
    org_id = await _get_org_id(db, current_user)

    # Verify entity
    entity_result = await db.execute(
        select(Entity).where(Entity.id == entity_id, Entity.org_id == org_id)
    )
    if not entity_result.scalar_one_or_none():
        raise HTTPException(404, "Entity not found")

    # Verify tag
    tag_result = await db.execute(
        select(EntityTag).where(EntityTag.id == tag_id, EntityTag.org_id == org_id)
    )
    if not tag_result.scalar_one_or_none():
        raise HTTPException(404, "Tag not found")

    # Check if already linked
    existing = await db.execute(
        select(entity_tag_association).where(
            entity_tag_association.c.entity_id == entity_id,
            entity_tag_association.c.tag_id == tag_id,
        )
    )
    if existing.first():
        return {"ok": True, "message": "Already tagged"}

    await db.execute(
        entity_tag_association.insert().values(entity_id=entity_id, tag_id=tag_id)
    )
    await db.commit()
    return {"ok": True}


@router.delete("/entities/{entity_id}/tags/{tag_id}")
async def remove_tag_from_entity(
    entity_id: int,
    tag_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove a tag from an entity."""
    org_id = await _get_org_id(db, current_user)

    # Verify entity belongs to org
    entity_result = await db.execute(
        select(Entity).where(Entity.id == entity_id, Entity.org_id == org_id)
    )
    if not entity_result.scalar_one_or_none():
        raise HTTPException(404, "Entity not found")

    await db.execute(
        delete(entity_tag_association).where(
            entity_tag_association.c.entity_id == entity_id,
            entity_tag_association.c.tag_id == tag_id,
        )
    )
    await db.commit()
    return {"ok": True}


# ==================== Теги у ФИО (отдельно от меток) ====================
# С 21.09.2026 «+ тег» рядом с именем — свой справочник (entity_name_tags_catalog),
# не связанный с метками. Для пользователя работает как раньше: выбрать из
# списка, завести новый с цветом, снять крестиком, убрать из списка корзиной.


class NameTagCreate(BaseModel):
    name: str
    color: str = "var(--hf-status-pink)"

    @field_validator("name")
    @classmethod
    def _clean_name(cls, v: str) -> str:
        cleaned = _HTML_TAG_RE.sub("", v or "").strip()
        if not cleaned:
            raise ValueError("name cannot be empty")
        if len(cleaned) > 80:
            raise ValueError("name must be 80 characters or fewer")
        return cleaned


class NameTagOut(BaseModel):
    id: int
    org_id: int
    name: str
    color: str
    created_by: int | None = None
    created_at: datetime | None = None
    archived_at: datetime | None = None

    class Config:
        from_attributes = True


async def _get_name_tag(db: AsyncSession, tag_id: int, org_id: int) -> NameTag:
    tag = (await db.execute(
        select(NameTag).where(NameTag.id == tag_id, NameTag.org_id == org_id)
    )).scalar_one_or_none()
    if not tag:
        raise HTTPException(404, "Name tag not found")
    return tag


async def _check_entity(db: AsyncSession, entity_id: int, org_id: int) -> None:
    found = (await db.execute(
        select(Entity.id).where(Entity.id == entity_id, Entity.org_id == org_id)
    )).scalar_one_or_none()
    if not found:
        raise HTTPException(404, "Entity not found")


@router.get("/name-tags", response_model=list[NameTagOut])
async def list_name_tags(
    include_archived: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Теги у имени для выбора (скрытые — только с include_archived)."""
    org_id = await _get_org_id(db, current_user)
    query = select(NameTag).where(NameTag.org_id == org_id)
    if not include_archived:
        query = query.where(NameTag.archived_at.is_(None))
    return list((await db.execute(query.order_by(NameTag.name))).scalars().all())


@router.post("/name-tags", response_model=NameTagOut)
async def create_name_tag(
    data: NameTagCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Завести тег. Скрытый с тем же именем возвращается из архива."""
    org_id = await _get_org_id(db, current_user)
    existing = (await db.execute(
        select(NameTag).where(NameTag.org_id == org_id, NameTag.name == data.name)
    )).scalar_one_or_none()
    if existing is not None:
        if existing.archived_at is None:
            raise HTTPException(409, "Name tag with this name already exists")
        existing.archived_at = None
        existing.color = data.color
        await db.commit()
        await db.refresh(existing)
        return existing
    tag = NameTag(org_id=org_id, name=data.name, color=data.color, created_by=current_user.id)
    db.add(tag)
    await db.commit()
    await db.refresh(tag)
    return tag


@router.post("/name-tags/{tag_id}/archive", response_model=NameTagOut)
async def archive_name_tag(
    tag_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Убрать тег из списка выбора; у кандидатов, кому стоит, остаётся."""
    org_id = await _get_org_id(db, current_user)
    tag = await _get_name_tag(db, tag_id, org_id)
    if tag.archived_at is None:
        tag.archived_at = datetime.utcnow()
        await db.commit()
        await db.refresh(tag)
    return tag


@router.post("/name-tags/{tag_id}/restore", response_model=NameTagOut)
async def restore_name_tag(
    tag_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = await _get_org_id(db, current_user)
    tag = await _get_name_tag(db, tag_id, org_id)
    if tag.archived_at is not None:
        tag.archived_at = None
        await db.commit()
        await db.refresh(tag)
    return tag


@router.get("/entities/{entity_id}/name-tags", response_model=list[NameTagOut])
async def get_entity_name_tags(
    entity_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Скоуп по воронкам: чужой кандидат не отвечает ничем, даже метками.
    from ..services.vacancy_scope import ensure_entity_visible
    await ensure_entity_visible(entity_id, current_user, db)
    org_id = await _get_org_id(db, current_user)
    await _check_entity(db, entity_id, org_id)
    rows = await db.execute(
        select(NameTag)
        .join(entity_name_tag_association, NameTag.id == entity_name_tag_association.c.tag_id)
        .where(entity_name_tag_association.c.entity_id == entity_id)
        .order_by(NameTag.name)
    )
    return list(rows.scalars().all())


@router.post("/entities/{entity_id}/name-tags/{tag_id}")
async def add_name_tag_to_entity(
    entity_id: int,
    tag_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = await _get_org_id(db, current_user)
    await _check_entity(db, entity_id, org_id)
    await _get_name_tag(db, tag_id, org_id)
    already = (await db.execute(
        select(entity_name_tag_association).where(
            entity_name_tag_association.c.entity_id == entity_id,
            entity_name_tag_association.c.tag_id == tag_id,
        )
    )).first()
    if already:
        return {"ok": True, "message": "Already tagged"}
    await db.execute(
        entity_name_tag_association.insert().values(entity_id=entity_id, tag_id=tag_id)
    )
    await db.commit()
    return {"ok": True}


@router.delete("/entities/{entity_id}/name-tags/{tag_id}")
async def remove_name_tag_from_entity(
    entity_id: int,
    tag_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = await _get_org_id(db, current_user)
    await _check_entity(db, entity_id, org_id)
    await db.execute(
        delete(entity_name_tag_association).where(
            entity_name_tag_association.c.entity_id == entity_id,
            entity_name_tag_association.c.tag_id == tag_id,
        )
    )
    await db.commit()
    return {"ok": True}
