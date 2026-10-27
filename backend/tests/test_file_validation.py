"""
Tests for file upload validation.

This module tests:
1. File extension whitelist validation
2. Magic bytes content validation
3. Dangerous patterns in filenames
"""
import pytest
import pytest_asyncio
from datetime import datetime
from pathlib import Path
from io import BytesIO
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.database import (
    Entity, EntityType, EntityStatus, User, Organization, Department
)
from api.services.auth import create_access_token
from api.routes.entities import (
    validate_file_upload, ALLOWED_EXTENSIONS, DANGEROUS_PATTERNS, ALLOWED_MIME_TYPES
)


@pytest.fixture(autouse=True)
def no_upload_background(monkeypatch):
    """Фоновые шаги после загрузки файла в тестах не запускаем.

    1. AI-профиль: files.py ставит `add_task(asyncio.create_task, coro)` —
       Starlette зовёт синхронный create_task в пуле потоков, где нет event
       loop, → «no running event loop». На проде ответ к этому моменту уже
       ушёл (загрузка работает, падает только профиль — владелец 19.10.2026
       решил это не чинить). В тестах ASGITransport пробрасывает ошибку фоновой
       задачи в сам запрос, поэтому create_task в модуле ручек — «выбросить
       корутину», остальной asyncio — настоящий.
    2. «PDF → вкладка Резюме» и OCR открывают своё соединение с базой
       (AsyncSessionLocal — другая in-memory SQLite, «no such table»).

    Константы загрузки (ENTITY_FILES_DIR, MAX_FILE_SIZE…) тесты подменяют в
    модуле `api.routes.entities.files`, где их читает ручка: подмена в пакете
    `api.routes.entities` (как было) не действовала, и файлы ложились в
    настоящий backend/uploads.
    """
    import asyncio as _asyncio
    import importlib
    files_routes = importlib.import_module("api.routes.entities.files")
    import api.services.resume_autopromote as ra
    import api.services.resume_text_extract as rte

    class _AsyncioNoTasks:
        def __getattr__(self, name):
            return getattr(_asyncio, name)

        @staticmethod
        def create_task(coro, *a, **k):
            coro.close()

    async def _noop(*a, **k):
        return None

    monkeypatch.setattr(files_routes, "asyncio", _AsyncioNoTasks())
    monkeypatch.setattr(ra, "promote_pdf_to_resume_if_needed", _noop)
    monkeypatch.setattr(rte, "ocr_and_store", _noop)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest_asyncio.fixture
async def file_test_entity(
    db_session: AsyncSession,
    organization: Organization,
    department: Department,
    admin_user: User
) -> Entity:
    """Create an entity for file validation tests."""
    entity = Entity(
        org_id=organization.id,
        department_id=department.id,
        created_by=admin_user.id,
        name="File Test Entity",
        email="filetest@example.com",
        type=EntityType.candidate,
        status=EntityStatus.active,
        created_at=datetime.utcnow()
    )
    db_session.add(entity)
    await db_session.commit()
    await db_session.refresh(entity)
    return entity


def auth_headers(token: str) -> dict:
    """Create authorization headers with token."""
    return {"Authorization": f"Bearer {token}"}


# ============================================================================
# EXTENSION WHITELIST TESTS
# ============================================================================

class TestExtensionWhitelist:
    """Tests for file extension whitelist validation."""

    def test_allowed_extensions_not_empty(self):
        """Test that allowed extensions set is not empty."""
        assert len(ALLOWED_EXTENSIONS) > 0

    @pytest.mark.parametrize("extension", [
        ".pdf", ".doc", ".docx", ".txt",  # Documents
        ".jpg", ".jpeg", ".png", ".gif",  # Images
        ".xls", ".xlsx", ".csv",  # Spreadsheets
        ".zip", ".rar", ".7z",  # Archives
        ".ppt", ".pptx",  # Presentations
    ])
    def test_valid_extension_allowed(self, extension):
        """Test that valid extensions are allowed."""
        filename = f"document{extension}"
        is_valid, error = validate_file_upload(filename, "application/octet-stream")
        assert is_valid, f"Extension {extension} should be allowed: {error}"

    @pytest.mark.parametrize("extension", [
        ".exe", ".bat", ".cmd", ".sh", ".ps1",  # Executables
        ".dll", ".msi", ".scr", ".com",  # Windows executables
        ".js", ".vbs", ".jar",  # Script files
        ".hta", ".cpl", ".msc", ".wsf",  # Windows script files
    ])
    def test_dangerous_extension_rejected(self, extension):
        """Test that dangerous extensions are rejected."""
        filename = f"malware{extension}"
        is_valid, error = validate_file_upload(filename, "application/octet-stream")
        assert not is_valid, f"Extension {extension} should be rejected"
        assert "not allowed" in error.lower() or "file type" in error.lower()

    def test_file_without_extension_rejected(self):
        """Test that files without extension are rejected."""
        is_valid, error = validate_file_upload("filename", "application/octet-stream")
        assert not is_valid
        assert "extension" in error.lower()

    def test_extension_case_insensitive(self):
        """Test that extension validation is case insensitive."""
        # All these should be valid
        valid_variants = ["document.PDF", "document.Pdf", "document.pDf"]
        for filename in valid_variants:
            is_valid, error = validate_file_upload(filename, "application/pdf")
            assert is_valid, f"Extension {filename} should be allowed: {error}"

    def test_empty_filename_rejected(self):
        """Test that empty filename is rejected."""
        is_valid, error = validate_file_upload("", "application/octet-stream")
        assert not is_valid
        assert "filename" in error.lower() or "required" in error.lower()

    def test_none_filename_rejected(self):
        """Test that None filename is rejected."""
        is_valid, error = validate_file_upload(None, "application/octet-stream")
        assert not is_valid

    async def test_upload_valid_extension(
        self,
        client: AsyncClient,
        admin_user: User,
        file_test_entity: Entity,
        org_owner,
        tmp_path: Path,
        monkeypatch
    ):
        """Test uploading file with valid extension via API."""
        upload_dir = tmp_path / "uploads" / "entity_files"
        upload_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr("api.routes.entities.files.ENTITY_FILES_DIR", upload_dir)

        token = create_access_token(data={"sub": str(admin_user.id)})
        file_content = b"%PDF-1.4 test content"

        response = await client.post(
            f"/api/entities/{file_test_entity.id}/files",
            files={"file": ("resume.pdf", BytesIO(file_content), "application/pdf")},
            data={"file_type": "resume"},
            headers=auth_headers(token)
        )

        assert response.status_code == 200

    async def test_upload_invalid_extension(
        self,
        client: AsyncClient,
        admin_user: User,
        file_test_entity: Entity,
        org_owner,
        tmp_path: Path,
        monkeypatch
    ):
        """Test uploading file with invalid extension via API."""
        upload_dir = tmp_path / "uploads" / "entity_files"
        upload_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr("api.routes.entities.files.ENTITY_FILES_DIR", upload_dir)

        token = create_access_token(data={"sub": str(admin_user.id)})
        file_content = b"malicious content"

        response = await client.post(
            f"/api/entities/{file_test_entity.id}/files",
            files={"file": ("malware.exe", BytesIO(file_content), "application/x-executable")},
            data={"file_type": "other"},
            headers=auth_headers(token)
        )

        assert response.status_code == 400
        assert "not allowed" in response.json()["detail"].lower()


# ============================================================================
# MAGIC BYTES VALIDATION TESTS
# ============================================================================

class TestMagicBytesValidation:
    """Tests for magic bytes (file content) validation."""

    async def test_valid_pdf_magic_bytes(
        self,
        client: AsyncClient,
        admin_user: User,
        file_test_entity: Entity,
        org_owner,
        tmp_path: Path,
        monkeypatch
    ):
        """Test that valid PDF with correct magic bytes is accepted."""
        upload_dir = tmp_path / "uploads" / "entity_files"
        upload_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr("api.routes.entities.files.ENTITY_FILES_DIR", upload_dir)

        token = create_access_token(data={"sub": str(admin_user.id)})
        # Valid PDF magic bytes: %PDF
        file_content = b"%PDF-1.4 test pdf content"

        response = await client.post(
            f"/api/entities/{file_test_entity.id}/files",
            files={"file": ("document.pdf", BytesIO(file_content), "application/pdf")},
            data={"file_type": "resume"},
            headers=auth_headers(token)
        )

        assert response.status_code == 200

    async def test_invalid_pdf_magic_bytes(
        self,
        client: AsyncClient,
        admin_user: User,
        file_test_entity: Entity,
        org_owner,
        tmp_path: Path,
        monkeypatch
    ):
        """Test that PDF with incorrect magic bytes is rejected."""
        upload_dir = tmp_path / "uploads" / "entity_files"
        upload_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr("api.routes.entities.files.ENTITY_FILES_DIR", upload_dir)

        token = create_access_token(data={"sub": str(admin_user.id)})
        # Invalid: not starting with %PDF
        file_content = b"This is not a PDF file"

        response = await client.post(
            f"/api/entities/{file_test_entity.id}/files",
            files={"file": ("document.pdf", BytesIO(file_content), "application/pdf")},
            data={"file_type": "resume"},
            headers=auth_headers(token)
        )

        assert response.status_code == 400
        assert "invalid pdf" in response.json()["detail"].lower()

    async def test_valid_jpeg_magic_bytes(
        self,
        client: AsyncClient,
        admin_user: User,
        file_test_entity: Entity,
        org_owner,
        tmp_path: Path,
        monkeypatch
    ):
        """Test that valid JPEG with correct magic bytes is accepted."""
        upload_dir = tmp_path / "uploads" / "entity_files"
        upload_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr("api.routes.entities.files.ENTITY_FILES_DIR", upload_dir)

        token = create_access_token(data={"sub": str(admin_user.id)})
        # Valid JPEG magic bytes: FF D8 FF
        file_content = b'\xff\xd8\xff\xe0\x00\x10JFIF' + b'\x00' * 100

        response = await client.post(
            f"/api/entities/{file_test_entity.id}/files",
            files={"file": ("photo.jpg", BytesIO(file_content), "image/jpeg")},
            data={"file_type": "portfolio"},
            headers=auth_headers(token)
        )

        assert response.status_code == 200

    async def test_invalid_jpeg_magic_bytes(
        self,
        client: AsyncClient,
        admin_user: User,
        file_test_entity: Entity,
        org_owner,
        tmp_path: Path,
        monkeypatch
    ):
        """Test that JPEG with incorrect magic bytes is rejected."""
        upload_dir = tmp_path / "uploads" / "entity_files"
        upload_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr("api.routes.entities.files.ENTITY_FILES_DIR", upload_dir)

        token = create_access_token(data={"sub": str(admin_user.id)})
        # Invalid: not starting with JPEG magic bytes
        file_content = b"This is not a JPEG file"

        response = await client.post(
            f"/api/entities/{file_test_entity.id}/files",
            files={"file": ("photo.jpg", BytesIO(file_content), "image/jpeg")},
            data={"file_type": "portfolio"},
            headers=auth_headers(token)
        )

        assert response.status_code == 400
        assert "invalid jpeg" in response.json()["detail"].lower()

    async def test_valid_png_magic_bytes(
        self,
        client: AsyncClient,
        admin_user: User,
        file_test_entity: Entity,
        org_owner,
        tmp_path: Path,
        monkeypatch
    ):
        """Test that valid PNG with correct magic bytes is accepted."""
        upload_dir = tmp_path / "uploads" / "entity_files"
        upload_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr("api.routes.entities.files.ENTITY_FILES_DIR", upload_dir)

        token = create_access_token(data={"sub": str(admin_user.id)})
        # Valid PNG magic bytes: 89 50 4E 47 (89 PNG)
        file_content = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100

        response = await client.post(
            f"/api/entities/{file_test_entity.id}/files",
            files={"file": ("image.png", BytesIO(file_content), "image/png")},
            data={"file_type": "certificate"},
            headers=auth_headers(token)
        )

        assert response.status_code == 200

    async def test_invalid_png_magic_bytes(
        self,
        client: AsyncClient,
        admin_user: User,
        file_test_entity: Entity,
        org_owner,
        tmp_path: Path,
        monkeypatch
    ):
        """Test that PNG with incorrect magic bytes is rejected."""
        upload_dir = tmp_path / "uploads" / "entity_files"
        upload_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr("api.routes.entities.files.ENTITY_FILES_DIR", upload_dir)

        token = create_access_token(data={"sub": str(admin_user.id)})
        # Invalid: not starting with PNG magic bytes
        file_content = b"This is not a PNG file"

        response = await client.post(
            f"/api/entities/{file_test_entity.id}/files",
            files={"file": ("image.png", BytesIO(file_content), "image/png")},
            data={"file_type": "certificate"},
            headers=auth_headers(token)
        )

        assert response.status_code == 400
        assert "invalid png" in response.json()["detail"].lower()

    async def test_valid_zip_magic_bytes(
        self,
        client: AsyncClient,
        admin_user: User,
        file_test_entity: Entity,
        org_owner,
        tmp_path: Path,
        monkeypatch
    ):
        """Test that valid ZIP with correct magic bytes is accepted."""
        upload_dir = tmp_path / "uploads" / "entity_files"
        upload_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr("api.routes.entities.files.ENTITY_FILES_DIR", upload_dir)

        token = create_access_token(data={"sub": str(admin_user.id)})
        # Valid ZIP magic bytes: PK (50 4B)
        file_content = b'PK\x03\x04' + b'\x00' * 100

        response = await client.post(
            f"/api/entities/{file_test_entity.id}/files",
            files={"file": ("portfolio.zip", BytesIO(file_content), "application/zip")},
            data={"file_type": "portfolio"},
            headers=auth_headers(token)
        )

        assert response.status_code == 200

    async def test_invalid_zip_magic_bytes(
        self,
        client: AsyncClient,
        admin_user: User,
        file_test_entity: Entity,
        org_owner,
        tmp_path: Path,
        monkeypatch
    ):
        """Test that ZIP with incorrect magic bytes is rejected."""
        upload_dir = tmp_path / "uploads" / "entity_files"
        upload_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr("api.routes.entities.files.ENTITY_FILES_DIR", upload_dir)

        token = create_access_token(data={"sub": str(admin_user.id)})
        # Invalid: not starting with PK
        file_content = b"This is not a ZIP file"

        response = await client.post(
            f"/api/entities/{file_test_entity.id}/files",
            files={"file": ("archive.zip", BytesIO(file_content), "application/zip")},
            data={"file_type": "portfolio"},
            headers=auth_headers(token)
        )

        assert response.status_code == 400
        assert "invalid zip" in response.json()["detail"].lower()

    async def test_text_file_no_magic_bytes_check(
        self,
        client: AsyncClient,
        admin_user: User,
        file_test_entity: Entity,
        org_owner,
        tmp_path: Path,
        monkeypatch
    ):
        """Test that text files work without magic bytes validation."""
        upload_dir = tmp_path / "uploads" / "entity_files"
        upload_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr("api.routes.entities.files.ENTITY_FILES_DIR", upload_dir)

        token = create_access_token(data={"sub": str(admin_user.id)})
        # Plain text doesn't have magic bytes requirement
        file_content = b"This is a plain text file with any content"

        response = await client.post(
            f"/api/entities/{file_test_entity.id}/files",
            files={"file": ("notes.txt", BytesIO(file_content), "text/plain")},
            data={"file_type": "other"},
            headers=auth_headers(token)
        )

        assert response.status_code == 200


# ============================================================================
# DANGEROUS PATTERNS TESTS
# ============================================================================

class TestDangerousPatterns:
    """Tests for dangerous patterns in filenames."""

    def test_dangerous_patterns_defined(self):
        """Test that dangerous patterns list is defined."""
        assert len(DANGEROUS_PATTERNS) > 0

    @pytest.mark.parametrize("pattern", DANGEROUS_PATTERNS)
    def test_dangerous_pattern_detected(self, pattern):
        """Test that each dangerous pattern is detected."""
        # Test pattern as extension
        filename = f"document{pattern}"
        is_valid, error = validate_file_upload(filename, "application/octet-stream")
        assert not is_valid, f"Pattern {pattern} should be rejected"
        assert "not allowed" in error.lower()

    def test_double_extension_exe_rejected(self):
        """Test that double extension with .exe is rejected."""
        filename = "resume.pdf.exe"
        is_valid, error = validate_file_upload(filename, "application/octet-stream")
        assert not is_valid
        assert ".exe" in error.lower() or "not allowed" in error.lower()

    def test_double_extension_bat_rejected(self):
        """Test that double extension with .bat is rejected."""
        filename = "document.doc.bat"
        is_valid, error = validate_file_upload(filename, "application/octet-stream")
        assert not is_valid
        assert ".bat" in error.lower() or "not allowed" in error.lower()

    def test_double_extension_js_rejected(self):
        """Test that double extension with .js is rejected."""
        filename = "report.pdf.js"
        is_valid, error = validate_file_upload(filename, "application/octet-stream")
        assert not is_valid

    def test_double_extension_vbs_rejected(self):
        """Test that double extension with .vbs is rejected."""
        filename = "invoice.xls.vbs"
        is_valid, error = validate_file_upload(filename, "application/octet-stream")
        assert not is_valid

    def test_null_byte_injection_rejected(self):
        """Test that null byte injection is rejected."""
        filename = "document.pdf\x00.exe"
        is_valid, error = validate_file_upload(filename, "application/octet-stream")
        assert not is_valid
        assert "invalid filename" in error.lower()

    def test_path_traversal_rejected(self):
        """Test that path traversal attempts are rejected."""
        traversal_attempts = [
            "../../../etc/passwd",
            "..\\..\\windows\\system32\\config",
            "document/../../../secret.txt",
            "folder/./../../etc/passwd",
        ]
        for filename in traversal_attempts:
            is_valid, error = validate_file_upload(filename, "application/octet-stream")
            assert not is_valid, f"Path traversal {filename} should be rejected"
            assert "invalid filename" in error.lower()

    def test_backslash_in_filename_rejected(self):
        """Test that backslash in filename is rejected."""
        filename = "folder\\document.pdf"
        is_valid, error = validate_file_upload(filename, "application/octet-stream")
        assert not is_valid

    def test_forward_slash_in_filename_rejected(self):
        """Test that forward slash in filename is rejected."""
        filename = "folder/document.pdf"
        is_valid, error = validate_file_upload(filename, "application/octet-stream")
        assert not is_valid

    async def test_upload_double_extension_rejected(
        self,
        client: AsyncClient,
        admin_user: User,
        file_test_entity: Entity,
        org_owner,
        tmp_path: Path,
        monkeypatch
    ):
        """Test uploading file with dangerous double extension via API."""
        upload_dir = tmp_path / "uploads" / "entity_files"
        upload_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr("api.routes.entities.files.ENTITY_FILES_DIR", upload_dir)

        token = create_access_token(data={"sub": str(admin_user.id)})
        file_content = b"malicious content"

        response = await client.post(
            f"/api/entities/{file_test_entity.id}/files",
            files={"file": ("resume.pdf.exe", BytesIO(file_content), "application/pdf")},
            data={"file_type": "resume"},
            headers=auth_headers(token)
        )

        assert response.status_code == 400


# ============================================================================
# MIME TYPE TESTS
# ============================================================================

class TestMimeTypeValidation:
    """Tests for MIME type validation."""

    def test_allowed_mime_types_not_empty(self):
        """Test that allowed MIME types set is not empty."""
        assert len(ALLOWED_MIME_TYPES) > 0

    @pytest.mark.parametrize("mime_type", [
        "application/pdf",
        "image/jpeg",
        "image/png",
        "text/plain",
        "application/zip",
    ])
    def test_valid_mime_type_accepted(self, mime_type):
        """Test that valid MIME types are accepted."""
        assert mime_type in ALLOWED_MIME_TYPES

    def test_suspicious_mime_type_logged(self):
        """Test that suspicious MIME types don't block upload if extension is valid.

        This tests the security philosophy: extension is the primary control,
        MIME type is secondary (can be spoofed).
        """
        # Extension is valid (.pdf), but MIME type is unusual
        is_valid, error = validate_file_upload("document.pdf", "application/x-executable")
        # Should still be valid because extension is allowed
        assert is_valid


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestFileValidationIntegration:
    """Integration tests for file validation."""

    async def test_upload_and_validate_complete_flow(
        self,
        client: AsyncClient,
        admin_user: User,
        file_test_entity: Entity,
        org_owner,
        tmp_path: Path,
        monkeypatch
    ):
        """Test complete file upload flow with all validations."""
        upload_dir = tmp_path / "uploads" / "entity_files"
        upload_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr("api.routes.entities.files.ENTITY_FILES_DIR", upload_dir)

        token = create_access_token(data={"sub": str(admin_user.id)})

        # 1. Valid PDF upload
        pdf_content = b"%PDF-1.4 This is a valid PDF"
        response = await client.post(
            f"/api/entities/{file_test_entity.id}/files",
            files={"file": ("resume.pdf", BytesIO(pdf_content), "application/pdf")},
            data={"file_type": "resume", "description": "My resume"},
            headers=auth_headers(token)
        )
        assert response.status_code == 200
        data = response.json()
        assert data["file_name"] == "resume.pdf"
        assert data["file_type"] == "resume"

    async def test_multiple_validation_failures(
        self,
        client: AsyncClient,
        admin_user: User,
        file_test_entity: Entity,
        org_owner,
        tmp_path: Path,
        monkeypatch
    ):
        """Test that multiple validation issues are caught."""
        upload_dir = tmp_path / "uploads" / "entity_files"
        upload_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr("api.routes.entities.files.ENTITY_FILES_DIR", upload_dir)

        token = create_access_token(data={"sub": str(admin_user.id)})

        # Try various invalid uploads
        invalid_files = [
            ("malware.exe", b"executable content", "application/x-executable"),
            ("../../../etc/passwd", b"path traversal", "text/plain"),
            ("script.js", b"javascript code", "application/javascript"),
            ("virus.bat", b"batch script", "application/x-batch"),
        ]

        for filename, content, content_type in invalid_files:
            response = await client.post(
                f"/api/entities/{file_test_entity.id}/files",
                files={"file": (filename, BytesIO(content), content_type)},
                data={"file_type": "other"},
                headers=auth_headers(token)
            )
            assert response.status_code == 400, f"File {filename} should be rejected"
