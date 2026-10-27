"""External integrations API — currently used by the Claude MCP server.

Auth: long-lived bearer tokens from `api_tokens` table.
Token CRUD endpoints live here too (auth via standard JWT).
"""
import hashlib
import secrets
import logging
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.database import ApiToken, User, Project
from ..services.auth import get_current_user
from ..services.task_trigger import create_tasks_from_message

logger = logging.getLogger("hr-analyzer.integrations")

router = APIRouter()


# ---------------------------------------------------------------------------
# Token CRUD — authenticated with standard JWT (user from cookie/header)
# ---------------------------------------------------------------------------

class CreateTokenRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=80, description="Human-readable label, e.g. 'Claude on MacBook'")


class TokenItem(BaseModel):
    id: int
    name: str
    prefix: str
    last_used_at: Optional[datetime]
    created_at: datetime


class CreateTokenResponse(BaseModel):
    id: int
    name: str
    prefix: str
    token: str = Field(..., description="Plaintext token — shown once, never stored. Save it now.")
    created_at: datetime


def _hash_token(plain: str) -> str:
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()


@router.get("/api-tokens", response_model=List[TokenItem])
async def list_my_tokens(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List API tokens belonging to the current user."""
    res = await db.execute(
        select(ApiToken).where(ApiToken.user_id == user.id).order_by(ApiToken.created_at.desc())
    )
    return [
        TokenItem(
            id=t.id, name=t.name, prefix=t.prefix,
            last_used_at=t.last_used_at, created_at=t.created_at,
        )
        for t in res.scalars().all()
    ]


@router.post("/api-tokens", response_model=CreateTokenResponse, status_code=201)
async def create_my_token(
    data: CreateTokenRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Generate a new API token for the current user. Plaintext shown once."""
    # 32 random bytes, hex-encoded → 64-char hex token. Prefix "enc_" so it's
    # recognisable. Total length 68 chars.
    raw = secrets.token_hex(32)
    plain = f"enc_{raw}"
    prefix = plain[:12]  # "enc_xxxxxxxx" for UI display
    token_hash = _hash_token(plain)

    record = ApiToken(
        user_id=user.id,
        name=data.name.strip(),
        token_hash=token_hash,
        prefix=prefix,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)

    return CreateTokenResponse(
        id=record.id,
        name=record.name,
        prefix=record.prefix,
        token=plain,
        created_at=record.created_at,
    )


@router.delete("/api-tokens/{token_id}", status_code=204)
async def revoke_my_token(
    token_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Revoke a token by id (must belong to the current user)."""
    res = await db.execute(
        select(ApiToken).where(ApiToken.id == token_id, ApiToken.user_id == user.id)
    )
    tok = res.scalar_one_or_none()
    if not tok:
        raise HTTPException(404, "Token not found")
    await db.delete(tok)
    await db.commit()


# ---------------------------------------------------------------------------
# Bearer-token auth helper — for endpoints called by the MCP server
# ---------------------------------------------------------------------------

async def auth_via_api_token(
    db: AsyncSession = Depends(get_db),
    authorization: Optional[str] = Header(None),
) -> User:
    """Authenticate via `Authorization: Bearer enc_...` header (api_tokens)."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Missing Bearer token")
    plain = authorization.split(None, 1)[1].strip()
    if not plain.startswith("enc_"):
        raise HTTPException(401, "Invalid token format")
    token_hash = _hash_token(plain)
    res = await db.execute(
        select(ApiToken).where(ApiToken.token_hash == token_hash)
    )
    tok = res.scalar_one_or_none()
    if not tok:
        raise HTTPException(401, "Invalid or revoked token")
    # touch last_used_at (best-effort)
    tok.last_used_at = datetime.utcnow()
    await db.commit()

    user_res = await db.execute(select(User).where(User.id == tok.user_id))
    user = user_res.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(401, "User inactive or deleted")
    return user


# ---------------------------------------------------------------------------
# Integration endpoints — used by Claude MCP
# ---------------------------------------------------------------------------

class IntegrationProjectItem(BaseModel):
    id: int
    name: str
    description: Optional[str] = None


@router.get("/projects", response_model=List[IntegrationProjectItem])
async def integration_list_projects(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(auth_via_api_token),
):
    """List projects in the user's organisation. Used by Claude to disambiguate."""
    from ..services.auth import get_user_org
    org = await get_user_org(user, db)
    if not org:
        return []
    res = await db.execute(
        select(Project).where(Project.org_id == org.id).order_by(Project.name)
    )
    return [
        IntegrationProjectItem(id=p.id, name=p.name, description=p.description)
        for p in res.scalars().all()
    ]


class CreateTaskRequest(BaseModel):
    message: str = Field(..., min_length=1, description="Natural-language task description, may include project name")
    project_hint: Optional[str] = Field(None, description="Optional explicit project name to scope to")


class CreatedTaskItem(BaseModel):
    task_id: int
    task_key: Optional[str] = None
    title: str
    project: str
    project_id: int
    assignee: Optional[str] = None


class CreateTaskResponse(BaseModel):
    created: List[CreatedTaskItem]


@router.post("/create-task", response_model=CreateTaskResponse)
async def integration_create_task(
    data: CreateTaskRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(auth_via_api_token),
):
    """Create one or more tasks from a natural-language message.

    Reuses the same `create_tasks_from_message` pipeline that the Telegram
    bot uses for /tasks and blockers — gets project matching (translit +
    fuzzy), AI parsing, assignee resolution out of the box.
    """
    # If a project hint is provided, prefix the message so the matcher catches it.
    msg = data.message.strip()
    if data.project_hint and data.project_hint.strip().lower() not in msg.lower():
        msg = f"{data.project_hint.strip()}: {msg}"

    try:
        created = await create_tasks_from_message(
            db=db,
            message_text=msg,
            user_name=user.name,
            telegram_user_id=user.telegram_id,
            chat_id=None,
            telegram_username=user.telegram_username,
            blocker_id=None,
        )
    except Exception as e:
        logger.exception("integration_create_task failed")
        raise HTTPException(500, f"Failed to create task: {e}")

    if not created:
        raise HTTPException(
            422,
            "Could not extract a task from the message. Make sure the project "
            "name is mentioned (e.g. 'Saturn: …') and the message describes "
            "concrete work."
        )

    return CreateTaskResponse(
        created=[
            CreatedTaskItem(
                task_id=t.get("task_id"),
                task_key=t.get("task_key"),
                title=t.get("title", ""),
                project=t.get("project", ""),
                project_id=t.get("project_id"),
                assignee=t.get("assignee"),
            )
            for t in created
        ]
    )
