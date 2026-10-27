"""
Document Signing routes — templates, generation, canvas signature.

Endpoints:
- CRUD for document templates (admin/HRD)
- Generate document from template for employee
- Sign document with canvas signature (base64 PNG)
- List documents for employee
"""
import logging
import re
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.database import get_db
from api.models.database import (
    DocumentTemplate, SignedDocument, Employee, User,
    OrgMember, OrgRole,
)
from api.services.auth import get_current_user, get_user_org

logger = logging.getLogger("hr-analyzer.documents")

router = APIRouter()


# ─── Pydantic schemas ───────────────────────────────────────

class TemplateCreate(BaseModel):
    name: str
    content: str
    variables: Optional[List[str]] = None

class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    content: Optional[str] = None
    variables: Optional[List[str]] = None
    is_active: Optional[bool] = None

class TemplateResponse(BaseModel):
    id: int
    org_id: int
    name: str
    content: str
    variables: Optional[List[str]] = None
    is_active: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}

class GenerateDocRequest(BaseModel):
    template_id: int
    employee_id: int

class SignDocRequest(BaseModel):
    signature_data: str  # "data:image/png;base64,..."

class SignedDocResponse(BaseModel):
    id: int
    template_id: Optional[int] = None
    employee_id: int
    title: str
    content_rendered: str
    signature_data: Optional[str] = None
    signed_at: Optional[datetime] = None
    signer_ip: Optional[str] = None
    status: str
    created_at: Optional[datetime] = None
    employee_name: Optional[str] = None

    model_config = {"from_attributes": True}


# ─── Helpers ─────────────────────────────────────────────────

async def _is_admin_or_owner(user: User, org_id: int, db: AsyncSession) -> bool:
    if user.role and user.role.value == "superadmin":
        return True
    result = await db.execute(
        select(OrgMember).where(
            OrgMember.user_id == user.id,
            OrgMember.org_id == org_id,
            OrgMember.role.in_([OrgRole.owner, OrgRole.admin]),
        )
    )
    return result.scalar_one_or_none() is not None


def _render_template(content: str, employee: Employee, user: User) -> str:
    """Replace {{variables}} in template with employee data."""
    now = datetime.utcnow()
    replacements = {
        "name": user.name or "",
        "email": user.email or "",
        "position": employee.position or "",
        "department": employee.department.name if employee.department else "",
        "date": now.strftime("%d.%m.%Y"),
        "phone": employee.phone or "",
        "telegram": employee.telegram_username or "",
    }
    # Personal data from the employee profile (extra_data JSON) — for NDA/contract auto-fill
    extra = getattr(employee, "extra_data", None) or {}
    for key in (
        "first_name", "last_name", "middle_name", "full_name", "birth_date",
        "passport_number", "passport_issued", "passport_issued_by", "address", "inn", "snils",
    ):
        replacements[key] = str(extra.get(key, "") or "")
    # ФИО с фолбэком, чтобы не выходило пустое «Исполнитель: ,»:
    # extra.full_name → склейка фамилия/имя/отчество → имя пользователя.
    fio = (
        replacements["full_name"].strip()
        or " ".join(
            p for p in (replacements["last_name"], replacements["first_name"], replacements["middle_name"]) if p.strip()
        ).strip()
        or (user.name or "")
    )
    replacements["full_name"] = fio
    if not replacements["name"].strip():
        replacements["name"] = fio
    result = content
    for key, value in replacements.items():
        result = result.replace("{{" + key + "}}", str(value))
    return result


# ─── Template CRUD (admin only) ─────────────────────────────

@router.get("/templates", response_model=List[TemplateResponse])
async def list_templates(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    org = await get_user_org(user, db)
    if not org:
        raise HTTPException(404, "Организация не найдена")

    result = await db.execute(
        select(DocumentTemplate)
        .where(DocumentTemplate.org_id == org.id)
        .order_by(DocumentTemplate.created_at.desc())
    )
    return [TemplateResponse.model_validate(t) for t in result.scalars().all()]


@router.post("/templates", response_model=TemplateResponse)
async def create_template(
    payload: TemplateCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    org = await get_user_org(user, db)
    if not org:
        raise HTTPException(404, "Организация не найдена")
    if not await _is_admin_or_owner(user, org.id, db):
        raise HTTPException(403, "Только администраторы могут создавать шаблоны")

    # Auto-detect variables from content
    variables = payload.variables
    if variables is None:
        variables = list(set(re.findall(r"\{\{(\w+)\}\}", payload.content)))

    template = DocumentTemplate(
        org_id=org.id,
        name=payload.name,
        content=payload.content,
        variables=variables,
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return TemplateResponse.model_validate(template)


@router.put("/templates/{template_id}", response_model=TemplateResponse)
async def update_template(
    template_id: int,
    payload: TemplateUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    org = await get_user_org(user, db)
    if not org:
        raise HTTPException(404, "Организация не найдена")
    if not await _is_admin_or_owner(user, org.id, db):
        raise HTTPException(403, "Нет прав")

    result = await db.execute(
        select(DocumentTemplate).where(
            DocumentTemplate.id == template_id,
            DocumentTemplate.org_id == org.id,
        )
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(404, "Шаблон не найден")

    if payload.name is not None:
        template.name = payload.name
    if payload.content is not None:
        template.content = payload.content
        # Re-detect variables
        if payload.variables is None:
            template.variables = list(set(re.findall(r"\{\{(\w+)\}\}", payload.content)))
    if payload.variables is not None:
        template.variables = payload.variables
    if payload.is_active is not None:
        template.is_active = payload.is_active

    await db.commit()
    await db.refresh(template)
    return TemplateResponse.model_validate(template)


@router.delete("/templates/{template_id}")
async def delete_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    org = await get_user_org(user, db)
    if not org:
        raise HTTPException(404, "Организация не найдена")
    if not await _is_admin_or_owner(user, org.id, db):
        raise HTTPException(403, "Нет прав")

    result = await db.execute(
        select(DocumentTemplate).where(
            DocumentTemplate.id == template_id,
            DocumentTemplate.org_id == org.id,
        )
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(404, "Шаблон не найден")

    await db.delete(template)
    await db.commit()
    return {"ok": True}


# ─── Document generation ─────────────────────────────────────

@router.post("/generate", response_model=SignedDocResponse)
async def generate_document(
    payload: GenerateDocRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    org = await get_user_org(user, db)
    if not org:
        raise HTTPException(404, "Организация не найдена")
    if not await _is_admin_or_owner(user, org.id, db):
        raise HTTPException(403, "Только администраторы могут генерировать документы")

    # Get template
    result = await db.execute(
        select(DocumentTemplate).where(
            DocumentTemplate.id == payload.template_id,
            DocumentTemplate.org_id == org.id,
        )
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(404, "Шаблон не найден")

    # Get employee with relationships
    result = await db.execute(
        select(Employee)
        .options(selectinload(Employee.user), selectinload(Employee.department))
        .where(Employee.id == payload.employee_id, Employee.org_id == org.id)
    )
    employee = result.scalar_one_or_none()
    if not employee:
        raise HTTPException(404, "Сотрудник не найден")

    # Render content
    rendered = _render_template(template.content, employee, employee.user)

    doc = SignedDocument(
        template_id=template.id,
        employee_id=employee.id,
        title=template.name,
        content_rendered=rendered,
        status="pending",
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    return SignedDocResponse(
        id=doc.id,
        template_id=doc.template_id,
        employee_id=doc.employee_id,
        title=doc.title,
        content_rendered=doc.content_rendered,
        signature_data=doc.signature_data,
        signed_at=doc.signed_at,
        signer_ip=doc.signer_ip,
        status=doc.status,
        created_at=doc.created_at,
        employee_name=employee.user.name if employee.user else None,
    )


# ─── My documents (employee self-service) ────────────────────

@router.get("/my", response_model=List[SignedDocResponse])
async def my_documents(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Find employee record for current user
    result = await db.execute(
        select(Employee).where(Employee.user_id == user.id)
    )
    employee = result.scalar_one_or_none()
    if not employee:
        return []

    result = await db.execute(
        select(SignedDocument)
        .where(SignedDocument.employee_id == employee.id)
        .order_by(SignedDocument.created_at.desc())
    )
    docs = result.scalars().all()
    return [
        SignedDocResponse(
            id=d.id,
            template_id=d.template_id,
            employee_id=d.employee_id,
            title=d.title,
            content_rendered=d.content_rendered,
            signature_data=d.signature_data,
            signed_at=d.signed_at,
            signer_ip=d.signer_ip,
            status=d.status,
            created_at=d.created_at,
            employee_name=user.name,
        )
        for d in docs
    ]


# ─── Get single document ─────────────────────────────────────

@router.get("/{doc_id}", response_model=SignedDocResponse)
async def get_document(
    doc_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(SignedDocument)
        .options(selectinload(SignedDocument.employee).selectinload(Employee.user))
        .where(SignedDocument.id == doc_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "Документ не найден")

    # Check access: employee themselves or admin
    is_own = doc.employee and doc.employee.user_id == user.id
    if not is_own:
        org = await get_user_org(user, db)
        if not org or not await _is_admin_or_owner(user, org.id, db):
            raise HTTPException(403, "Нет доступа к этому документу")

    return SignedDocResponse(
        id=doc.id,
        template_id=doc.template_id,
        employee_id=doc.employee_id,
        title=doc.title,
        content_rendered=doc.content_rendered,
        signature_data=doc.signature_data,
        signed_at=doc.signed_at,
        signer_ip=doc.signer_ip,
        status=doc.status,
        created_at=doc.created_at,
        employee_name=doc.employee.user.name if doc.employee and doc.employee.user else None,
    )


# ─── Sign document ───────────────────────────────────────────

@router.post("/{doc_id}/sign", response_model=SignedDocResponse)
async def sign_document(
    doc_id: int,
    payload: SignDocRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(SignedDocument)
        .options(selectinload(SignedDocument.employee).selectinload(Employee.user))
        .where(SignedDocument.id == doc_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "Документ не найден")

    # Only the employee themselves can sign
    if not doc.employee or doc.employee.user_id != user.id:
        raise HTTPException(403, "Только сотрудник может подписать свой документ")

    if doc.status == "signed":
        raise HTTPException(400, "Документ уже подписан")

    # Validate signature data
    if not payload.signature_data or not payload.signature_data.startswith("data:image/"):
        raise HTTPException(400, "Некорректные данные подписи")

    # Get client IP
    client_ip = request.client.host if request.client else None
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        client_ip = forwarded_for.split(",")[0].strip()

    doc.signature_data = payload.signature_data
    doc.signed_at = datetime.utcnow()
    doc.signer_ip = client_ip
    doc.status = "signed"

    # If this is an NDA template, update employee.nda_signed
    if doc.template_id:
        tmpl_result = await db.execute(
            select(DocumentTemplate).where(DocumentTemplate.id == doc.template_id)
        )
        tmpl = tmpl_result.scalar_one_or_none()
        if tmpl and "nda" in tmpl.name.lower():
            doc.employee.nda_signed = True
            doc.employee.nda_signed_at = datetime.utcnow()
        if tmpl and ("договор" in tmpl.name.lower() or "contract" in tmpl.name.lower()):
            doc.employee.contract_signed = True
            doc.employee.contract_signed_at = datetime.utcnow()

    await db.commit()
    await db.refresh(doc)

    return SignedDocResponse(
        id=doc.id,
        template_id=doc.template_id,
        employee_id=doc.employee_id,
        title=doc.title,
        content_rendered=doc.content_rendered,
        signature_data=doc.signature_data,
        signed_at=doc.signed_at,
        signer_ip=doc.signer_ip,
        status=doc.status,
        created_at=doc.created_at,
        employee_name=doc.employee.user.name if doc.employee and doc.employee.user else None,
    )


# ─── Employee documents (admin view) ─────────────────────────

@router.get("/employee/{employee_id}", response_model=List[SignedDocResponse])
async def get_employee_documents(
    employee_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    org = await get_user_org(user, db)
    if not org:
        raise HTTPException(404, "Организация не найдена")
    if not await _is_admin_or_owner(user, org.id, db):
        raise HTTPException(403, "Нет прав")

    # Verify employee belongs to org
    result = await db.execute(
        select(Employee)
        .options(selectinload(Employee.user))
        .where(Employee.id == employee_id, Employee.org_id == org.id)
    )
    employee = result.scalar_one_or_none()
    if not employee:
        raise HTTPException(404, "Сотрудник не найден")

    result = await db.execute(
        select(SignedDocument)
        .where(SignedDocument.employee_id == employee_id)
        .order_by(SignedDocument.created_at.desc())
    )
    docs = result.scalars().all()
    return [
        SignedDocResponse(
            id=d.id,
            template_id=d.template_id,
            employee_id=d.employee_id,
            title=d.title,
            content_rendered=d.content_rendered,
            signature_data=d.signature_data,
            signed_at=d.signed_at,
            signer_ip=d.signer_ip,
            status=d.status,
            created_at=d.created_at,
            employee_name=employee.user.name if employee.user else None,
        )
        for d in docs
    ]
