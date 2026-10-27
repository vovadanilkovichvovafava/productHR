"""
Sandbox/testing environment endpoints.
"""

from typing import Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.exc import IntegrityError

from .common import (
    get_db,
    get_superadmin,
    User,
    UserRole,
    OrgRole,
    DeptRole,
    Organization,
    OrgMember,
    Department,
    DepartmentMember,
    Entity,
    EntityType,
    EntityStatus,
    Chat,
    ChatType,
    Message,
    CallRecording,
    CallSource,
    CallStatus,
    SharedAccess,
    ResourceType,
    AccessLevel,
    ImpersonationLog,
    SandboxCreateRequest,
    SandboxCreateResponse,
    SandboxUserInfo,
    SandboxEntityInfo,
    SandboxChatInfo,
    SandboxCallInfo,
    SandboxStatusResponse,
    SandboxStatsInfo,
    hash_password,
    create_impersonation_token,
    is_secure_context,
    settings,
)


router = APIRouter()


@router.post("/sandbox/create", response_model=SandboxCreateResponse)
async def create_sandbox(
    request_body: Optional[SandboxCreateRequest] = None,
    superadmin: User = Depends(get_superadmin),
    db: AsyncSession = Depends(get_db)
):
    """
    Create an isolated test environment for testing and development.

    Creates:
    - "Sandbox Test Department" department in specified organization
    - 4 test users with different roles:
      - sandbox_owner@test.local (OrgRole.owner)
      - sandbox_admin@test.local (DeptRole.lead)
      - sandbox_subadmin@test.local (DeptRole.sub_admin)
      - sandbox_member@test.local (DeptRole.member)
    - 5 test entities (contacts) with different owners
    - 3 test chats linked to entities
    - 2 test call recordings
    - Sharing relationships between users

    All sandbox data is tagged with "sandbox" for easy identification.
    All sandbox users have password: "sandbox123"

    **Only SUPERADMIN can access this endpoint.**
    """
    # Re-fetch superadmin to avoid detached instance issues
    superadmin_result = await db.execute(
        select(User).where(User.id == superadmin.id)
    )
    superadmin = superadmin_result.scalar_one_or_none()
    if not superadmin:
        raise HTTPException(status_code=401, detail="Superadmin not found")

    # Get organization from request or auto-detect first available
    org_id = request_body.org_id if request_body else None

    if org_id:
        org_result = await db.execute(
            select(Organization).where(Organization.id == org_id)
        )
        org = org_result.scalar_one_or_none()
        if not org:
            raise HTTPException(
                status_code=404,
                detail=f"Organization with id {org_id} not found"
            )
    else:
        # Auto-detect first organization
        org_result = await db.execute(
            select(Organization).order_by(Organization.id).limit(1)
        )
        org = org_result.scalar_one_or_none()
        if not org:
            raise HTTPException(
                status_code=404,
                detail="No organizations found. Create an organization first."
            )

    # Check if sandbox already exists in this organization
    result = await db.execute(
        select(Department)
        .where(Department.org_id == org.id)
        .where(Department.name == "Sandbox Test Department")
    )
    existing_dept = result.scalar_one_or_none()

    if existing_dept:
        raise HTTPException(
            status_code=409,
            detail="Sandbox already exists. Delete it first using DELETE /api/admin/sandbox"
        )

    # Check if sandbox users already exist (could be leftover from failed creation)
    sandbox_emails = [
        "sandbox_owner@test.local",
        "sandbox_admin@test.local",
        "sandbox_subadmin@test.local",
        "sandbox_member@test.local"
    ]
    existing_users_result = await db.execute(
        select(User).where(User.email.in_(sandbox_emails))
    )
    existing_users = existing_users_result.scalars().all()

    if existing_users:
        existing_emails = [u.email for u in existing_users]
        raise HTTPException(
            status_code=409,
            detail=f"Sandbox users already exist: {', '.join(existing_emails)}. "
                   f"Delete them first or run DELETE /api/admin/sandbox to clean up."
        )

    # 1. Create Sandbox Test Department
    sandbox_dept = Department(
        org_id=org.id,
        name="Sandbox Test Department",
        description="Automated test environment for QA and development",
        color="#FF6B35",
        is_active=True
    )
    db.add(sandbox_dept)
    await db.flush()

    # 2. Create 4 test users
    password_hash_value = hash_password("sandbox123")

    sandbox_users = [
        {
            "email": "sandbox_owner@test.local",
            "name": "Sandbox Owner",
            "role": UserRole.admin,
            "org_role": OrgRole.owner,
            "dept_role": DeptRole.lead
        },
        {
            "email": "sandbox_admin@test.local",
            "name": "Sandbox Admin",
            "role": UserRole.admin,
            "org_role": OrgRole.admin,
            "dept_role": DeptRole.lead
        },
        {
            "email": "sandbox_subadmin@test.local",
            "name": "Sandbox SubAdmin",
            "role": UserRole.sub_admin,
            "org_role": OrgRole.member,
            "dept_role": DeptRole.sub_admin
        },
        {
            "email": "sandbox_member@test.local",
            "name": "Sandbox Member",
            "role": UserRole.admin,
            "org_role": OrgRole.member,
            "dept_role": DeptRole.member
        }
    ]

    created_users = []
    user_objects = []

    for user_data in sandbox_users:
        # Create user
        user = User(
            email=user_data["email"],
            name=user_data["name"],
            password_hash=password_hash_value,
            role=user_data["role"],
            is_active=True
        )
        db.add(user)
        await db.flush()

        # Add to organization
        org_member = OrgMember(
            org_id=org.id,
            user_id=user.id,
            role=user_data["org_role"],
            invited_by=superadmin.id
        )
        db.add(org_member)

        # Add to sandbox department
        dept_member = DepartmentMember(
            department_id=sandbox_dept.id,
            user_id=user.id,
            role=user_data["dept_role"]
        )
        db.add(dept_member)

        created_users.append(SandboxUserInfo(
            id=user.id,
            email=user.email,
            name=user.name,
            password="sandbox123",
            role=user.role.value,
            org_role=user_data["org_role"].value,
            dept_role=user_data["dept_role"].value
        ))
        user_objects.append(user)

    await db.flush()

    # 3. Create 5 test entities (contacts)
    entity_data = [
        {
            "name": "John Candidate",
            "type": EntityType.candidate,
            "status": EntityStatus.interview,
            "email": "john.candidate@example.com",
            "phone": "+1234567890",
            "position": "Senior Developer",
            "company": "Tech Corp",
            "owner_idx": 0
        },
        {
            "name": "Sarah Client",
            "type": EntityType.client,
            "status": EntityStatus.active,
            "email": "sarah.client@example.com",
            "phone": "+1234567891",
            "company": "Client Corp",
            "owner_idx": 1
        },
        {
            "name": "Mike Contractor",
            "type": EntityType.contractor,
            "status": EntityStatus.negotiation,
            "email": "mike.contractor@example.com",
            "phone": "+1234567892",
            "position": "QA Engineer",
            "owner_idx": 1
        },
        {
            "name": "Lisa Lead",
            "type": EntityType.lead,
            "status": EntityStatus.new,
            "email": "lisa.lead@example.com",
            "phone": "+1234567893",
            "company": "Startup Inc",
            "owner_idx": 2
        },
        {
            "name": "Alex Partner",
            "type": EntityType.partner,
            "status": EntityStatus.active,
            "email": "alex.partner@example.com",
            "phone": "+1234567894",
            "company": "Partner LLC",
            "owner_idx": 3
        }
    ]

    entity_ids = []
    entity_objects = []

    for entity_info in entity_data:
        entity = Entity(
            org_id=org.id,
            department_id=sandbox_dept.id,
            type=entity_info["type"],
            name=entity_info["name"],
            status=entity_info["status"],
            email=entity_info["email"],
            phone=entity_info["phone"],
            position=entity_info.get("position"),
            company=entity_info.get("company"),
            tags=["sandbox"],
            created_by=user_objects[entity_info["owner_idx"]].id
        )
        db.add(entity)
        await db.flush()
        entity_ids.append(entity.id)
        entity_objects.append(entity)

    # 4. Create test chats linked to entities (more variety)
    chat_data = [
        {
            "title": "Interview with John Candidate",
            "chat_type": ChatType.hr,
            "entity_idx": 0,
            "owner_idx": 0  # Owner
        },
        {
            "title": "Client Meeting - Sarah",
            "chat_type": ChatType.client,
            "entity_idx": 1,
            "owner_idx": 1  # Admin
        },
        {
            "title": "Contractor Negotiation - Mike",
            "chat_type": ChatType.contractor,
            "entity_idx": 2,
            "owner_idx": 1  # Admin
        },
        {
            "title": "Lead Discussion - Lisa",
            "chat_type": ChatType.sales,
            "entity_idx": 3,
            "owner_idx": 2  # SubAdmin
        },
        {
            "title": "Partner Onboarding - Alex",
            "chat_type": ChatType.work,
            "entity_idx": 4,
            "owner_idx": 3  # Member
        },
        {
            "title": "Technical Support Chat",
            "chat_type": ChatType.support,
            "entity_idx": None,
            "owner_idx": 0  # Owner - no entity linked
        },
        {
            "title": "Project Alpha Discussion",
            "chat_type": ChatType.project,
            "entity_idx": None,
            "owner_idx": 1  # Admin - no entity linked
        }
    ]

    chat_ids = []
    chat_objects = []

    for idx, chat_info in enumerate(chat_data):
        # Handle optional entity linking
        entity_id = None
        if chat_info["entity_idx"] is not None:
            entity_id = entity_objects[chat_info["entity_idx"]].id

        chat = Chat(
            org_id=org.id,
            telegram_chat_id=1000000 + idx,  # Fake telegram chat IDs
            title=chat_info["title"],
            custom_name=chat_info["title"],
            chat_type=chat_info["chat_type"],
            owner_id=user_objects[chat_info["owner_idx"]].id,
            entity_id=entity_id,
            is_active=True
        )
        db.add(chat)
        await db.flush()
        chat_ids.append(chat.id)
        chat_objects.append(chat)

        # Add some sample messages
        for msg_idx in range(3):
            message = Message(
                chat_id=chat.id,
                telegram_message_id=1000 + idx * 10 + msg_idx,
                telegram_user_id=12345678 + idx,
                username=f"test_user_{idx}",
                first_name=user_objects[chat_info["owner_idx"]].name.split()[0],
                last_name=user_objects[chat_info["owner_idx"]].name.split()[1] if len(user_objects[chat_info["owner_idx"]].name.split()) > 1 else "",
                content=f"Test message {msg_idx + 1} in {chat_info['title']}",
                content_type="text",
                is_imported=False
            )
            db.add(message)

    # 5. Create test call recordings (more variety)
    call_data = [
        {
            "title": "Technical Interview Call",
            "entity_idx": 0,
            "owner_idx": 0,  # Owner
            "source_type": CallSource.meet,
            "status": CallStatus.done,
            "duration_seconds": 3600
        },
        {
            "title": "Client Discovery Call",
            "entity_idx": 1,
            "owner_idx": 1,  # Admin
            "source_type": CallSource.zoom,
            "status": CallStatus.done,
            "duration_seconds": 2400
        },
        {
            "title": "Contractor Onboarding",
            "entity_idx": 2,
            "owner_idx": 1,  # Admin
            "source_type": CallSource.fireflies,
            "status": CallStatus.done,
            "duration_seconds": 1800
        },
        {
            "title": "Sales Demo Call",
            "entity_idx": 3,
            "owner_idx": 2,  # SubAdmin
            "source_type": CallSource.meet,
            "status": CallStatus.done,
            "duration_seconds": 2700
        },
        {
            "title": "Partner Strategy Session",
            "entity_idx": 4,
            "owner_idx": 3,  # Member
            "source_type": CallSource.zoom,
            "status": CallStatus.done,
            "duration_seconds": 3300
        },
        {
            "title": "Team Standup Recording",
            "entity_idx": None,
            "owner_idx": 0,  # Owner - no entity linked
            "source_type": CallSource.meet,
            "status": CallStatus.done,
            "duration_seconds": 900
        }
    ]

    call_ids = []
    call_objects = []

    for call_info in call_data:
        # Handle optional entity linking
        call_entity_id = None
        if call_info["entity_idx"] is not None:
            call_entity_id = entity_objects[call_info["entity_idx"]].id

        call = CallRecording(
            org_id=org.id,
            title=call_info["title"],
            entity_id=call_entity_id,
            owner_id=user_objects[call_info["owner_idx"]].id,
            source_type=call_info["source_type"],
            status=call_info["status"],
            duration_seconds=call_info["duration_seconds"],
            transcript=f"Sample transcript for {call_info['title']}",
            summary=f"This is a test call recording for sandbox environment.",
            started_at=datetime.utcnow() - timedelta(hours=2),
            ended_at=datetime.utcnow() - timedelta(hours=1),
            processed_at=datetime.utcnow()
        )
        db.add(call)
        await db.flush()
        call_ids.append(call.id)
        call_objects.append(call)

    # 6. Create sharing relationships (comprehensive cross-user sharing)
    sharing_data = [
        # Owner shares with others
        {
            "resource_type": ResourceType.entity,
            "resource": entity_objects[0],  # John Candidate
            "from_idx": 0,  # Owner
            "to_idx": 1,    # Admin
            "access_level": AccessLevel.edit,
            "note": "Admin has edit access to candidate"
        },
        {
            "resource_type": ResourceType.chat,
            "resource": chat_objects[0],  # Interview with John
            "from_idx": 0,  # Owner
            "to_idx": 2,    # SubAdmin
            "access_level": AccessLevel.view,
            "note": "SubAdmin can view interview chat"
        },
        {
            "resource_type": ResourceType.call,
            "resource": call_objects[0],  # Technical Interview Call
            "from_idx": 0,  # Owner
            "to_idx": 3,    # Member
            "access_level": AccessLevel.view,
            "note": "Member can view call recording"
        },
        # Admin shares with others
        {
            "resource_type": ResourceType.entity,
            "resource": entity_objects[1],  # Sarah Client
            "from_idx": 1,  # Admin
            "to_idx": 2,    # SubAdmin
            "access_level": AccessLevel.view,
            "note": "SubAdmin can view client info"
        },
        {
            "resource_type": ResourceType.chat,
            "resource": chat_objects[1],  # Client Meeting - Sarah
            "from_idx": 1,  # Admin
            "to_idx": 3,    # Member
            "access_level": AccessLevel.view,
            "note": "Member can view client meeting"
        },
        {
            "resource_type": ResourceType.call,
            "resource": call_objects[1],  # Client Discovery Call
            "from_idx": 1,  # Admin
            "to_idx": 0,    # Owner
            "access_level": AccessLevel.full,
            "note": "Owner has full access"
        },
        # SubAdmin shares with member
        {
            "resource_type": ResourceType.entity,
            "resource": entity_objects[3],  # Lisa Lead
            "from_idx": 2,  # SubAdmin
            "to_idx": 3,    # Member
            "access_level": AccessLevel.view,
            "note": "Member can view lead info"
        },
        {
            "resource_type": ResourceType.call,
            "resource": call_objects[3],  # Sales Demo Call
            "from_idx": 2,  # SubAdmin
            "to_idx": 0,    # Owner
            "access_level": AccessLevel.edit,
            "note": "Owner can edit sales demo"
        },
        # Cross-sharing for member
        {
            "resource_type": ResourceType.call,
            "resource": call_objects[4],  # Partner Strategy Session
            "from_idx": 3,  # Member
            "to_idx": 1,    # Admin
            "access_level": AccessLevel.view,
            "note": "Admin can review partner session"
        },
    ]

    for share_info in sharing_data:
        resource = share_info["resource"]
        share = SharedAccess(
            resource_type=share_info["resource_type"],
            resource_id=resource.id,
            shared_by_id=user_objects[share_info["from_idx"]].id,
            shared_with_id=user_objects[share_info["to_idx"]].id,
            access_level=share_info["access_level"],
            note=share_info["note"]
        )
        # Set the appropriate foreign key based on resource type
        if share_info["resource_type"] == ResourceType.entity:
            share.entity_id = resource.id
        elif share_info["resource_type"] == ResourceType.chat:
            share.chat_id = resource.id
        elif share_info["resource_type"] == ResourceType.call:
            share.call_id = resource.id
        db.add(share)

    # Commit with error handling
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        error_detail = str(e.orig) if hasattr(e, 'orig') else str(e)
        raise HTTPException(
            status_code=409,
            detail=f"Database integrity error during sandbox creation. "
                   f"This usually means some sandbox data already exists. "
                   f"Try running DELETE /api/admin/sandbox first. Error: {error_detail}"
        )
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create sandbox: {str(e)}"
        )

    # Build response with full objects
    entities_response = [
        SandboxEntityInfo(
            id=entity.id,
            created_by=entity.created_by,
            name=entity.name,
            email=entity.email or "",
            tags=entity.tags or []
        )
        for entity in entity_objects
    ]

    chats_response = [
        SandboxChatInfo(
            id=chat.id,
            owner_id=chat.owner_id,
            title=chat.title or ""
        )
        for chat in chat_objects
    ]

    calls_response = [
        SandboxCallInfo(
            id=call.id,
            owner_id=call.owner_id,
            title=call.title or ""
        )
        for call in call_objects
    ]

    return SandboxCreateResponse(
        department_id=sandbox_dept.id,
        users=created_users,
        entities=entities_response,
        chats=chats_response,
        calls=calls_response
    )


@router.delete("/sandbox")
async def delete_sandbox(
    org_id: Optional[int] = Query(None, description="Organization ID (optional, auto-detects if not provided)"),
    superadmin: User = Depends(get_superadmin),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete all sandbox test data.

    Removes:
    - All sandbox users (sandbox_*@test.local)
    - Sandbox Test Department
    - All associated entities, chats, calls
    - All shared access records
    - Cascade cleanup of all related data

    **Only SUPERADMIN can access this endpoint.**
    """
    # Re-fetch superadmin to avoid detached instance issues
    superadmin_result = await db.execute(
        select(User).where(User.id == superadmin.id)
    )
    superadmin = superadmin_result.scalar_one_or_none()
    if not superadmin:
        raise HTTPException(status_code=401, detail="Superadmin not found")

    # Get organization from request or auto-detect
    if org_id:
        org_result = await db.execute(
            select(Organization).where(Organization.id == org_id)
        )
        org = org_result.scalar_one_or_none()
        if not org:
            raise HTTPException(
                status_code=404,
                detail=f"Organization with id {org_id} not found"
            )
    else:
        # Auto-detect organization that has sandbox
        org_result = await db.execute(
            select(Organization)
            .join(Department, Department.org_id == Organization.id)
            .where(Department.name == "Sandbox Test Department")
            .limit(1)
        )
        org = org_result.scalar_one_or_none()
        if not org:
            raise HTTPException(
                status_code=404,
                detail="No sandbox found in any organization"
            )

    # Find sandbox department
    result = await db.execute(
        select(Department)
        .where(Department.org_id == org.id)
        .where(Department.name == "Sandbox Test Department")
    )
    sandbox_dept = result.scalar_one_or_none()

    if not sandbox_dept:
        raise HTTPException(
            status_code=404,
            detail="Sandbox does not exist"
        )

    # Find all sandbox users
    sandbox_emails = [
        "sandbox_owner@test.local",
        "sandbox_admin@test.local",
        "sandbox_subadmin@test.local",
        "sandbox_member@test.local"
    ]

    sandbox_users_result = await db.execute(
        select(User).where(User.email.in_(sandbox_emails))
    )
    sandbox_users = sandbox_users_result.scalars().all()

    # Count items before deletion
    deleted_count = {
        "users": len(sandbox_users),
        "entities": 0,
        "chats": 0,
        "calls": 0,
        "messages": 0,
        "shared_access": 0
    }

    # Count entities
    entities_result = await db.execute(
        select(Entity).where(Entity.department_id == sandbox_dept.id)
    )
    entities = entities_result.scalars().all()
    deleted_count["entities"] = len(entities)

    # Count chats and messages
    for user in sandbox_users:
        chats_result = await db.execute(
            select(Chat).where(Chat.owner_id == user.id)
        )
        chats = chats_result.scalars().all()
        deleted_count["chats"] += len(chats)

        for chat in chats:
            messages_result = await db.execute(
                select(Message).where(Message.chat_id == chat.id)
            )
            messages = messages_result.scalars().all()
            deleted_count["messages"] += len(messages)

    # Count calls
    for user in sandbox_users:
        calls_result = await db.execute(
            select(CallRecording).where(CallRecording.owner_id == user.id)
        )
        calls = calls_result.scalars().all()
        deleted_count["calls"] += len(calls)

    # Count shared access
    for user in sandbox_users:
        shared_result = await db.execute(
            select(SharedAccess).where(
                (SharedAccess.shared_by_id == user.id) | (SharedAccess.shared_with_id == user.id)
            )
        )
        shared = shared_result.scalars().all()
        deleted_count["shared_access"] += len(shared)

    # Delete in proper order to avoid FK constraints
    # 1. Delete shared access records first
    await db.execute(
        delete(SharedAccess).where(
            SharedAccess.shared_by_id.in_([u.id for u in sandbox_users])
        )
    )
    await db.execute(
        delete(SharedAccess).where(
            SharedAccess.shared_with_id.in_([u.id for u in sandbox_users])
        )
    )

    # 2. Delete messages
    for user in sandbox_users:
        chats_result = await db.execute(
            select(Chat).where(Chat.owner_id == user.id)
        )
        chats = chats_result.scalars().all()
        for chat in chats:
            await db.execute(delete(Message).where(Message.chat_id == chat.id))

    # 3. Delete chats
    for user in sandbox_users:
        await db.execute(delete(Chat).where(Chat.owner_id == user.id))

    # 4. Delete call recordings
    for user in sandbox_users:
        await db.execute(delete(CallRecording).where(CallRecording.owner_id == user.id))

    # 5. Delete entities
    await db.execute(delete(Entity).where(Entity.department_id == sandbox_dept.id))

    # 6. Delete department members
    await db.execute(delete(DepartmentMember).where(DepartmentMember.department_id == sandbox_dept.id))

    # 7. Delete org members for sandbox users
    for user in sandbox_users:
        await db.execute(delete(OrgMember).where(OrgMember.user_id == user.id))

    # 8. Delete sandbox users
    for user in sandbox_users:
        await db.execute(delete(User).where(User.id == user.id))

    # 9. Delete sandbox department
    await db.execute(delete(Department).where(Department.id == sandbox_dept.id))

    # Commit with error handling
    try:
        await db.commit()
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete sandbox: {str(e)}"
        )

    return {
        "message": "Sandbox environment deleted successfully",
        "deleted": deleted_count
    }


@router.get("/sandbox/status", response_model=SandboxStatusResponse)
async def get_sandbox_status(
    org_id: Optional[int] = Query(None, description="Organization ID (optional, auto-detects if not provided)"),
    superadmin: User = Depends(get_superadmin),
    db: AsyncSession = Depends(get_db)
):
    """
    Check if sandbox test environment exists.

    Returns:
    - Whether sandbox exists
    - Department ID and name if exists
    - List of sandbox users with roles
    - Stats: count of entities, chats, and calls

    **Only SUPERADMIN can access this endpoint.**
    """
    # Re-fetch superadmin to avoid detached instance issues
    superadmin_result = await db.execute(
        select(User).where(User.id == superadmin.id)
    )
    superadmin = superadmin_result.scalar_one_or_none()
    if not superadmin:
        raise HTTPException(status_code=401, detail="Superadmin not found")

    # Get organization from request or auto-detect
    if org_id:
        org_result = await db.execute(
            select(Organization).where(Organization.id == org_id)
        )
        org = org_result.scalar_one_or_none()
        if not org:
            raise HTTPException(
                status_code=404,
                detail=f"Organization with id {org_id} not found"
            )
    else:
        # Try to find organization with sandbox first, otherwise use first org
        org_result = await db.execute(
            select(Organization)
            .join(Department, Department.org_id == Organization.id)
            .where(Department.name == "Sandbox Test Department")
            .limit(1)
        )
        org = org_result.scalar_one_or_none()

        if not org:
            # Fallback to first organization
            org_result = await db.execute(
                select(Organization).order_by(Organization.id).limit(1)
            )
            org = org_result.scalar_one_or_none()

        if not org:
            # No organizations at all - return empty status
            return {
                "exists": False,
                "department_id": None,
                "department_name": None,
                "users": [],
                "stats": {"contacts": 0, "chats": 0, "calls": 0}
            }

    # Find sandbox department
    result = await db.execute(
        select(Department)
        .where(Department.org_id == org.id)
        .where(Department.name == "Sandbox Test Department")
    )
    sandbox_dept = result.scalar_one_or_none()

    if not sandbox_dept:
        return {
            "exists": False,
            "department_id": None,
            "department_name": None,
            "users": [],
            "stats": {"contacts": 0, "chats": 0, "calls": 0}
        }

    # Find sandbox users
    sandbox_emails = [
        "sandbox_owner@test.local",
        "sandbox_admin@test.local",
        "sandbox_subadmin@test.local",
        "sandbox_member@test.local"
    ]

    sandbox_users_result = await db.execute(
        select(User).where(User.email.in_(sandbox_emails))
    )
    sandbox_users = sandbox_users_result.scalars().all()

    users_info = []
    for user in sandbox_users:
        # Get org role
        org_member_result = await db.execute(
            select(OrgMember)
            .where(OrgMember.user_id == user.id)
            .where(OrgMember.org_id == org.id)
        )
        org_member = org_member_result.scalar_one_or_none()

        # Get dept role
        dept_member_result = await db.execute(
            select(DepartmentMember)
            .where(DepartmentMember.user_id == user.id)
            .where(DepartmentMember.department_id == sandbox_dept.id)
        )
        dept_member = dept_member_result.scalar_one_or_none()

        # Determine display role and label
        if org_member and org_member.role.value == "owner":
            role = "owner"
            role_label = "Владелец"
        elif dept_member:
            role = dept_member.role.value
            role_labels = {
                "lead": "Админ (Лид)",
                "sub_admin": "Саб-Админ",
                "member": "Сотрудник"
            }
            role_label = role_labels.get(role, role)
        else:
            role = user.role.value
            role_label = role

        users_info.append({
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "role": role,
            "role_label": role_label,
            "is_active": user.is_active
        })

    # Count entities
    entities_result = await db.execute(
        select(Entity).where(Entity.department_id == sandbox_dept.id)
    )
    entity_count = len(entities_result.scalars().all())

    # Count chats
    chat_count = 0
    for user in sandbox_users:
        chats_result = await db.execute(
            select(Chat).where(Chat.owner_id == user.id)
        )
        chat_count += len(chats_result.scalars().all())

    # Count calls
    call_count = 0
    for user in sandbox_users:
        calls_result = await db.execute(
            select(CallRecording).where(CallRecording.owner_id == user.id)
        )
        call_count += len(calls_result.scalars().all())

    return {
        "exists": True,
        "department_id": sandbox_dept.id,
        "department_name": sandbox_dept.name,
        "users": users_info,
        "stats": {
            "contacts": entity_count,
            "chats": chat_count,
            "calls": call_count
        }
    }


@router.post("/sandbox/switch/{email:path}")
async def switch_to_sandbox_user_by_email(
    email: str,
    request: Request,
    superadmin: User = Depends(get_superadmin),
    db: AsyncSession = Depends(get_db)
):
    """
    Quick switch to a sandbox user account by email.

    Creates an impersonation token and sets it as httpOnly cookie.
    Only works for sandbox_*@test.local users.

    This is a convenience endpoint for quickly testing different roles
    without manually logging in with credentials.

    **Only SUPERADMIN can access this endpoint.**
    """
    # Re-fetch superadmin to avoid detached instance issues
    superadmin_result = await db.execute(
        select(User).where(User.id == superadmin.id)
    )
    superadmin = superadmin_result.scalar_one_or_none()
    if not superadmin:
        raise HTTPException(status_code=401, detail="Superadmin not found")

    # Get target user by email
    result = await db.execute(select(User).where(User.email == email))
    target_user = result.scalar_one_or_none()

    if not target_user:
        raise HTTPException(
            status_code=404,
            detail=f"User with email {email} not found"
        )

    # Verify this is a sandbox user email
    if not target_user.email.endswith("@test.local"):
        raise HTTPException(
            status_code=400,
            detail="Only sandbox users (@test.local) can be switched to via this endpoint"
        )

    # Cannot impersonate inactive users
    if not target_user.is_active:
        raise HTTPException(status_code=400, detail="Cannot impersonate inactive user")

    # Create impersonation token (expires in 1 hour)
    token = create_impersonation_token(
        impersonated_user_id=target_user.id,
        original_user_id=superadmin.id,
        token_version=target_user.token_version
    )

    # Log impersonation session for audit
    impersonation_log = ImpersonationLog(
        superadmin_id=superadmin.id,
        impersonated_user_id=target_user.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent")
    )
    db.add(impersonation_log)
    await db.commit()

    # Create response with user data
    response = JSONResponse(content={
        "user": {
            "id": target_user.id,
            "email": target_user.email,
            "name": target_user.name,
            "role": target_user.role.value,
            "telegram_id": target_user.telegram_id,
            "telegram_username": target_user.telegram_username,
            "is_active": target_user.is_active,
            "created_at": target_user.created_at.isoformat(),
        },
        "message": f"Switched to {target_user.email}"
    })

    # Set httpOnly cookie (like login does)
    use_secure = is_secure_context(request)
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=use_secure,
        samesite="lax",
        max_age=3600,  # 1 hour for impersonation
        path="/"  # Must match login cookie path for cookie to work site-wide
    )

    return response
