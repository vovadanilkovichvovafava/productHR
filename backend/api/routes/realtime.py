"""
WebSocket realtime event system for HR-bot.

Provides real-time notifications for:
- Entity CRUD operations
- Chat messages
- Share events
- And other resource updates

Architecture:
- Endpoint: ws://host/ws?token=<jwt_token>
- Authentication: JWT token in query parameter
- Event format: {"type": "event.type", "payload": {...}, "timestamp": "ISO8601"}
- Access control: Users only receive events for their organization
"""

from datetime import datetime
from typing import Dict, Set, Optional, Any, List
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
import json
import logging
import asyncio

from ..database import get_db
from ..models.database import (
    User, UserRole, Entity, Chat, CallRecording,
    SharedAccess, ResourceType, DepartmentMember, DeptRole, OrgMember, OrgRole
)
from ..services.auth import get_user_from_token

logger = logging.getLogger("hr-analyzer.realtime")

router = APIRouter()


class ConnectionManager:
    """Manages WebSocket connections and event broadcasting."""

    def __init__(self):
        # Map of user_id -> set of WebSocket connections
        self.active_connections: Dict[int, Set[WebSocket]] = {}
        # Map of user_id -> organization_id for quick access control
        self.user_orgs: Dict[int, int] = {}
        # Lock for thread-safe operations
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, user: User, org_id: int):
        """Register a new WebSocket connection for a user."""
        await websocket.accept()

        async with self._lock:
            if user.id not in self.active_connections:
                self.active_connections[user.id] = set()

            self.active_connections[user.id].add(websocket)
            self.user_orgs[user.id] = org_id

        logger.info(f"User {user.id} connected to WebSocket (org_id={org_id})")

    async def disconnect(self, websocket: WebSocket, user_id: int):
        """Remove a WebSocket connection."""
        async with self._lock:
            if user_id in self.active_connections:
                self.active_connections[user_id].discard(websocket)

                # Clean up if no more connections for this user
                if not self.active_connections[user_id]:
                    del self.active_connections[user_id]
                    if user_id in self.user_orgs:
                        del self.user_orgs[user_id]

        logger.info(f"User {user_id} disconnected from WebSocket")

    async def broadcast_to_org(self, org_id: int, event_type: str, payload: Dict[str, Any]):
        """Broadcast an event to all users in an organization.

        Args:
            org_id: Organization ID to broadcast to
            event_type: Event type (e.g., "entity.created")
            payload: Event payload data
        """
        event = {
            "type": event_type,
            "payload": payload,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        message = json.dumps(event)

        # Find all users in this organization
        disconnected = []
        async with self._lock:
            for user_id, user_org_id in list(self.user_orgs.items()):
                if user_org_id == org_id and user_id in self.active_connections:
                    for websocket in list(self.active_connections[user_id]):
                        try:
                            await websocket.send_text(message)
                        except Exception as e:
                            logger.warning(f"Failed to send to user {user_id}: {e}")
                            disconnected.append((websocket, user_id))

        # Clean up disconnected clients
        for websocket, user_id in disconnected:
            await self.disconnect(websocket, user_id)

    async def broadcast_to_user(self, user_id: int, event_type: str, payload: Dict[str, Any]):
        """Broadcast an event to a specific user.

        Args:
            user_id: User ID to send to
            event_type: Event type (e.g., "share.created")
            payload: Event payload data
        """
        event = {
            "type": event_type,
            "payload": payload,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        message = json.dumps(event)

        disconnected = []
        async with self._lock:
            if user_id in self.active_connections:
                for websocket in list(self.active_connections[user_id]):
                    try:
                        await websocket.send_text(message)
                    except Exception as e:
                        logger.warning(f"Failed to send to user {user_id}: {e}")
                        disconnected.append((websocket, user_id))

        # Clean up disconnected clients
        for websocket, user_id in disconnected:
            await self.disconnect(websocket, user_id)

    async def broadcast_to_users(self, user_ids: List[int], event_type: str, payload: Dict[str, Any]):
        """Broadcast an event to specific users only.

        Args:
            user_ids: List of user IDs to send to
            event_type: Event type (e.g., "chat.updated")
            payload: Event payload data
        """
        if not user_ids:
            return

        event = {
            "type": event_type,
            "payload": payload,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        message = json.dumps(event)

        disconnected = []
        async with self._lock:
            for user_id in user_ids:
                if user_id in self.active_connections:
                    for websocket in list(self.active_connections[user_id]):
                        try:
                            await websocket.send_text(message)
                        except Exception as e:
                            logger.warning(f"Failed to send to user {user_id}: {e}")
                            disconnected.append((websocket, user_id))

        # Clean up disconnected clients
        for websocket, user_id in disconnected:
            await self.disconnect(websocket, user_id)

    async def send_to_connection(self, websocket: WebSocket, event_type: str, payload: Dict[str, Any]):
        """Send an event to a specific WebSocket connection.

        Args:
            websocket: WebSocket connection
            event_type: Event type
            payload: Event payload data
        """
        event = {
            "type": event_type,
            "payload": payload,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        try:
            await websocket.send_text(json.dumps(event))
        except Exception as e:
            logger.warning(f"Failed to send event: {e}")


# Global connection manager instance
manager = ConnectionManager()


async def authenticate_websocket(token: Optional[str], websocket: WebSocket, db: AsyncSession) -> Optional[User]:
    """Authenticate WebSocket connection using JWT token or cookie.

    Supports two authentication methods:
    1. JWT token in query parameter: ws://host/ws?token=<jwt_token>
    2. access_token cookie (httpOnly) - automatically sent by browser

    Args:
        token: JWT token from query parameter (optional)
        websocket: WebSocket connection to extract cookies from
        db: Database session

    Returns:
        User object if authenticated, None otherwise
    """
    # Try query parameter token first
    if token:
        user = await get_user_from_token(token, db)
        if user:
            return user

    # Fallback to cookie-based auth
    cookies = websocket.cookies
    cookie_token = cookies.get("access_token")
    if cookie_token:
        user = await get_user_from_token(cookie_token, db)
        if user:
            return user

    return None


async def get_user_org_id(user: User, db: AsyncSession) -> Optional[int]:
    """Get user's organization ID.

    Args:
        user: User object
        db: Database session

    Returns:
        Organization ID or None
    """
    from ..services.auth import get_user_org
    org = await get_user_org(user, db)
    return org.id if org else None


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: Optional[str] = Query(None),
):
    """WebSocket endpoint for real-time events.

    Authentication methods (in order of priority):
    1. JWT token in query parameter: ws://host/ws?token=<jwt_token>
    2. access_token cookie (httpOnly) - automatically sent by browser

    Events are broadcast in the following format:
    {
        "type": "event.type",
        "payload": {...},
        "timestamp": "2024-01-01T12:00:00.000Z"
    }

    Supported event types:
    - entity.created
    - entity.updated
    - entity.deleted
    - chat.message
    - share.created
    - share.revoked
    - call.progress (call processing progress update)
    - call.completed (call processing finished successfully)
    - call.failed (call processing failed with error)
    """
    # Аутентификация + org — на КОРОТКОЙ сессии, которую сразу закрываем. Раньше
    # WS держал коннект пула всю свою жизнь (десятки вкладок × долгая сессия →
    # исчерпание пула 50 → любой запрос виснет pool_timeout и 500, /health зелёный).
    db_gen = get_db()
    db = await anext(db_gen)
    try:
        user = await authenticate_websocket(token, websocket, db)
        if not user:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Unauthorized")
            return
        org_id = await get_user_org_id(user, db)
        if not org_id:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="No organization")
            return
    finally:
        try:
            await db_gen.aclose()
        except Exception as e:
            logger.warning(f"Error closing WS auth session: {e}")

    # Register connection (manager не нуждается в db)
    await manager.connect(websocket, user, org_id)

    # Keep connection alive and handle token expiry — БЕЗ удержания коннекта пула.
    try:
        while True:
            try:
                # Set a timeout to periodically check token validity
                data = await asyncio.wait_for(websocket.receive_text(), timeout=60.0)
                # Currently we just keep the connection alive

            except asyncio.TimeoutError:
                # Periodic token re-validation на СВЕЖЕЙ короткой сессии.
                reval_gen = get_db()
                reval_db = await anext(reval_gen)
                try:
                    current_user = await authenticate_websocket(token, websocket, reval_db)
                finally:
                    try:
                        await reval_gen.aclose()
                    except Exception:
                        pass
                if not current_user or current_user.id != user.id:
                    await websocket.close(
                        code=status.WS_1008_POLICY_VIOLATION,
                        reason="Token expired"
                    )
                    break

                # Send ping to keep connection alive
                try:
                    await websocket.send_text(json.dumps({
                        "type": "ping",
                        "timestamp": datetime.utcnow().isoformat() + "Z"
                    }))
                except Exception as e:
                    logger.warning(f"WebSocket ping failed for user {user.id}: {e}")
                    break

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket error for user {user.id}: {e}")
    finally:
        await manager.disconnect(websocket, user.id)


# ============================================================================
# ACCESS CONTROL FOR BROADCASTS
# ============================================================================

async def get_users_with_resource_access(
    db: AsyncSession,
    org_id: int,
    resource_type: ResourceType,
    resource_id: int,
    owner_id: int,
    entity_id: Optional[int] = None
) -> List[int]:
    """Get list of user IDs who have access to a resource.

    Access is granted to:
    1. Resource owner
    2. Org owners
    3. Superadmins in org
    4. Users with SharedAccess
    5. Dept leads/sub_admins if owner or linked entity is in their department

    Args:
        db: Database session
        org_id: Organization ID
        resource_type: Type of resource (chat, call, entity)
        resource_id: Resource ID
        owner_id: Owner of the resource
        entity_id: Optional entity ID the resource is linked to
    """
    user_ids = set()

    # 1. Resource owner always has access
    if owner_id:
        user_ids.add(owner_id)

    # 2. Org owners and admins
    # Use enum value for SQL comparison
    org_admins_result = await db.execute(
        select(OrgMember.user_id).where(
            OrgMember.org_id == org_id,
            OrgMember.role == OrgRole.owner
        )
    )
    for uid in org_admins_result.scalars().all():
        user_ids.add(uid)

    # 3. Superadmins in org
    superadmins_result = await db.execute(
        select(OrgMember.user_id).join(
            User, User.id == OrgMember.user_id
        ).where(
            OrgMember.org_id == org_id,
            User.role == UserRole.superadmin
        )
    )
    for uid in superadmins_result.scalars().all():
        user_ids.add(uid)

    # 4. Users with SharedAccess
    shared_result = await db.execute(
        select(SharedAccess.shared_with_id).where(
            SharedAccess.resource_type == resource_type,
            SharedAccess.resource_id == resource_id,
            or_(SharedAccess.expires_at.is_(None), SharedAccess.expires_at > datetime.utcnow())
        )
    )
    for uid in shared_result.scalars().all():
        user_ids.add(uid)

    # 5. Dept leads/sub_admins - check through owner's department
    if owner_id:
        # Get departments owner belongs to
        owner_depts_result = await db.execute(
            select(DepartmentMember.department_id).where(
                DepartmentMember.user_id == owner_id
            )
        )
        owner_dept_ids = [r for r in owner_depts_result.scalars().all()]

        if owner_dept_ids:
            # Get leads/sub_admins of those departments
            dept_leads_result = await db.execute(
                select(DepartmentMember.user_id).where(
                    DepartmentMember.department_id.in_(owner_dept_ids),
                    DepartmentMember.role.in_([DeptRole.lead, DeptRole.sub_admin])
                )
            )
            for uid in dept_leads_result.scalars().all():
                user_ids.add(uid)

    # 6. Dept leads/sub_admins - check through linked entity's department
    if entity_id:
        entity_result = await db.execute(
            select(Entity.department_id).where(Entity.id == entity_id)
        )
        entity_dept_id = entity_result.scalar_one_or_none()

        if entity_dept_id:
            dept_leads_result = await db.execute(
                select(DepartmentMember.user_id).where(
                    DepartmentMember.department_id == entity_dept_id,
                    DepartmentMember.role.in_([DeptRole.lead, DeptRole.sub_admin])
                )
            )
            for uid in dept_leads_result.scalars().all():
                user_ids.add(uid)

    # Модель A («общий пул HR»): кандидаты видны всем членам орга, поэтому
    # real-time события по ENTITY получают ВСЕ члены орга — иначе рекрутёр
    # (OrgRole.member) не получал апдейтов по чужим кандидатам и обновлял
    # страницу руками. Для chat/call (строже) не расширяем.
    if resource_type == ResourceType.entity:
        members_result = await db.execute(
            select(OrgMember.user_id).where(OrgMember.org_id == org_id)
        )
        for uid in members_result.scalars().all():
            user_ids.add(uid)

    return list(user_ids)


# ============================================================================
# BROADCAST HELPER FUNCTIONS
# ============================================================================

async def broadcast_entity_created(org_id: int, entity_data: Dict[str, Any], db: AsyncSession = None):
    """Broadcast entity.created event to users with access."""
    if db and entity_data.get("id") and entity_data.get("owner_id"):
        user_ids = await get_users_with_resource_access(
            db, org_id, ResourceType.entity,
            entity_data["id"], entity_data["owner_id"],
            entity_id=None  # Entity itself doesn't have parent entity
        )
        await manager.broadcast_to_users(user_ids, "entity.created", entity_data)
    else:
        # Fallback to org broadcast if no db
        await manager.broadcast_to_org(org_id, "entity.created", entity_data)


async def broadcast_entity_updated(org_id: int, entity_data: Dict[str, Any], db: AsyncSession = None):
    """Broadcast entity.updated event to users with access."""
    if db and entity_data.get("id") and entity_data.get("owner_id"):
        user_ids = await get_users_with_resource_access(
            db, org_id, ResourceType.entity,
            entity_data["id"], entity_data["owner_id"],
            entity_id=None
        )
        await manager.broadcast_to_users(user_ids, "entity.updated", entity_data)
    else:
        await manager.broadcast_to_org(org_id, "entity.updated", entity_data)


async def broadcast_entity_deleted(org_id: int, entity_id: int, owner_id: int = None, db: AsyncSession = None):
    """Broadcast entity.deleted event to users with access."""
    payload = {"id": entity_id, "resource_type": "entity"}
    if db and owner_id:
        user_ids = await get_users_with_resource_access(
            db, org_id, ResourceType.entity, entity_id, owner_id
        )
        await manager.broadcast_to_users(user_ids, "entity.deleted", payload)
    else:
        await manager.broadcast_to_org(org_id, "entity.deleted", payload)


async def broadcast_chat_message(org_id: int, message_data: Dict[str, Any], db: AsyncSession = None):
    """Broadcast chat.message event to users with access."""
    chat_id = message_data.get("chat_id")
    if db and chat_id:
        # Get chat to find owner and entity_id
        chat_result = await db.execute(select(Chat).where(Chat.id == chat_id))
        chat = chat_result.scalar_one_or_none()
        if chat:
            user_ids = await get_users_with_resource_access(
                db, org_id, ResourceType.chat, chat_id, chat.owner_id, chat.entity_id
            )
            await manager.broadcast_to_users(user_ids, "chat.message", message_data)
            return
    await manager.broadcast_to_org(org_id, "chat.message", message_data)


async def broadcast_chat_created(org_id: int, chat_data: Dict[str, Any], db: AsyncSession = None):
    """Broadcast chat.created event to users with access."""
    if db and chat_data.get("id") and chat_data.get("owner_id"):
        user_ids = await get_users_with_resource_access(
            db, org_id, ResourceType.chat,
            chat_data["id"], chat_data["owner_id"],
            entity_id=chat_data.get("entity_id")
        )
        await manager.broadcast_to_users(user_ids, "chat.created", chat_data)
    else:
        await manager.broadcast_to_org(org_id, "chat.created", chat_data)


async def broadcast_chat_updated(org_id: int, chat_data: Dict[str, Any], db: AsyncSession = None):
    """Broadcast chat.updated event to users with access."""
    if db and chat_data.get("id") and chat_data.get("owner_id"):
        user_ids = await get_users_with_resource_access(
            db, org_id, ResourceType.chat,
            chat_data["id"], chat_data["owner_id"],
            entity_id=chat_data.get("entity_id")
        )
        await manager.broadcast_to_users(user_ids, "chat.updated", chat_data)
    else:
        await manager.broadcast_to_org(org_id, "chat.updated", chat_data)


async def broadcast_chat_deleted(org_id: int, chat_id: int, owner_id: int = None, entity_id: int = None, db: AsyncSession = None):
    """Broadcast chat.deleted event to users with access."""
    payload = {"id": chat_id, "resource_type": "chat"}
    if db and owner_id:
        user_ids = await get_users_with_resource_access(
            db, org_id, ResourceType.chat, chat_id, owner_id, entity_id
        )
        await manager.broadcast_to_users(user_ids, "chat.deleted", payload)
    else:
        await manager.broadcast_to_org(org_id, "chat.deleted", payload)


async def broadcast_share_created(user_id: int, share_data: Dict[str, Any]):
    """Broadcast share.created event to specific user."""
    await manager.broadcast_to_user(user_id, "share.created", share_data)


async def broadcast_share_revoked(user_id: int, share_data: Dict[str, Any]):
    """Broadcast share.revoked event to specific user."""
    await manager.broadcast_to_user(user_id, "share.revoked", share_data)


# ============================================================================
# CALL PROCESSING EVENTS
# ============================================================================

async def broadcast_call_progress(org_id: int, call_data: Dict[str, Any]):
    """Broadcast call.progress event to organization.

    Args:
        org_id: Organization ID
        call_data: Call progress data including:
            - id: Call ID
            - progress: Progress percentage (0-100)
            - progress_stage: Current stage description
            - status: Current status (pending, transcribing, analyzing, etc.)
    """
    await manager.broadcast_to_org(org_id, "call.progress", call_data)


async def broadcast_call_completed(org_id: int, call_data: Dict[str, Any]):
    """Broadcast call.completed event to organization.

    Args:
        org_id: Organization ID
        call_data: Completed call data including:
            - id: Call ID
            - title: Call title
            - status: "done"
            - has_summary: Whether summary is available
            - has_transcript: Whether transcript is available
            - duration_seconds: Call duration
    """
    await manager.broadcast_to_org(org_id, "call.completed", call_data)


async def broadcast_call_failed(org_id: int, call_data: Dict[str, Any]):
    """Broadcast call.failed event to organization.

    Args:
        org_id: Organization ID
        call_data: Failed call data including:
            - id: Call ID
            - error_message: Error description
            - status: "failed"
    """
    await manager.broadcast_to_org(org_id, "call.failed", call_data)


async def broadcast_form_submission(user_id: int, payload: Dict[str, Any]):
    """Ответ на анкету — одному человеку (зовётся по каждому из
    hr_notifications.form_answer_recipients)."""
    await manager.broadcast_to_user(user_id, "form.submission", payload)
