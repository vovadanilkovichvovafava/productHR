"""
Тесты для API парсинга резюме.

Тестирует:
- POST /api/entities/parse-resume - парсинг резюме и извлечение данных
- POST /api/entities/from-resume - создание Entity из резюме
- Сервис ResumeParserService
"""
import pytest
import io
import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy import select

from api.models.database import (
    Entity, EntityType, EntityStatus, EntityFile, EntityFileType,
    Department
)
from api.services.resume_parser import (
    ResumeParserService, ParsedResume, resume_parser_service
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def sample_resume_text():
    """Пример текста резюме для тестирования."""
    return """
    Иванов Иван Петрович

    Контакты:
    Телефон: +7 (999) 123-45-67
    Email: ivan.ivanov@email.com
    Telegram: @ivan_developer

    Желаемая должность: Senior Python Developer
    Ожидаемая зарплата: от 250 000 до 350 000 рублей
    Город: Москва

    О себе:
    Опытный Python разработчик с 5-летним стажем. Специализируюсь на backend разработке.

    Навыки:
    - Python, FastAPI, Django
    - PostgreSQL, Redis, MongoDB
    - Docker, Kubernetes
    - Git, CI/CD

    Опыт работы:

    2021 - настоящее время: ООО "TechCorp"
    Должность: Senior Python Developer
    Описание: Разработка микросервисной архитектуры, оптимизация производительности.

    2019 - 2021: ООО "StartupXYZ"
    Должность: Python Developer
    Описание: Разработка REST API, интеграция с внешними сервисами.

    Образование:
    2015 - 2019: МГУ им. Ломоносова
    Специальность: Прикладная математика и информатика

    Языки:
    - Русский - родной
    - Английский - B2

    Ссылки:
    - GitHub: https://github.com/ivanivanov
    - LinkedIn: https://linkedin.com/in/ivanivanov
    """


@pytest.fixture
def mock_ai_response():
    """Мок ответа AI API."""
    return {
        "name": "Иванов Иван Петрович",
        "phone": "+7 (999) 123-45-67",
        "email": "ivan.ivanov@email.com",
        "telegram": "@ivan_developer",
        "position": "Senior Python Developer",
        "company": "ООО \"TechCorp\"",
        "experience_years": 5,
        "expected_salary_min": 250000,
        "expected_salary_max": 350000,
        "expected_salary_currency": "RUB",
        "skills": ["Python", "FastAPI", "Django", "PostgreSQL", "Redis", "MongoDB", "Docker", "Kubernetes", "Git", "CI/CD"],
        "education": [
            {"institution": "МГУ им. Ломоносова", "degree": "Прикладная математика и информатика", "year": "2019"}
        ],
        "experience": [
            {"company": "ООО \"TechCorp\"", "position": "Senior Python Developer", "period": "2021 - настоящее время", "description": "Разработка микросервисной архитектуры"},
            {"company": "ООО \"StartupXYZ\"", "position": "Python Developer", "period": "2019 - 2021", "description": "Разработка REST API"}
        ],
        "languages": [
            {"language": "Русский", "level": "родной"},
            {"language": "Английский", "level": "B2"}
        ],
        "location": "Москва",
        "about": "Опытный Python разработчик с 5-летним стажем",
        "links": ["https://github.com/ivanivanov", "https://linkedin.com/in/ivanivanov"],
        "parse_confidence": 0.95,
        "parse_warnings": []
    }


@pytest.fixture
def mock_pdf_content():
    """Мок содержимого PDF файла."""
    # Минимальный валидный PDF
    return b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n>>\nendobj\ntrailer\n<<\n/Root 1 0 R\n>>\n%%EOF"


@pytest.fixture
def mock_docx_content():
    """Мок содержимого DOCX файла."""
    # Минимальный ZIP с DOCX структурой (для тестов достаточно любых байтов)
    return b"PK\x03\x04" + b"\x00" * 100


# ============================================================================
# UNIT TESTS: ResumeParserService
# ============================================================================

class TestResumeParserService:
    """Юнит-тесты для ResumeParserService."""

    def test_parsed_resume_to_dict(self):
        """Тест конвертации ParsedResume в словарь."""
        resume = ParsedResume(
            name="Тест Тестов",
            phone="+7999123456",
            email="test@test.com",
            skills=["Python", "FastAPI"],
            parse_confidence=0.9
        )
        result = resume.to_dict()

        assert result["name"] == "Тест Тестов"
        assert result["phone"] == "+7999123456"
        assert result["email"] == "test@test.com"
        assert result["skills"] == ["Python", "FastAPI"]
        assert result["parse_confidence"] == 0.9

    def test_parsed_resume_to_entity_data(self):
        """Тест конвертации ParsedResume в данные для Entity."""
        resume = ParsedResume(
            name="Тест Тестов",
            phone="+7999123456",
            email="test@test.com",
            telegram="@testuser",
            position="Developer",
            company="TestCorp",
            expected_salary_min=100000,
            expected_salary_max=150000,
            expected_salary_currency="RUB",
            skills=["Python", "FastAPI", "Django", "PostgreSQL", "Redis", "MongoDB"],
            experience_years=3
        )
        result = resume.to_entity_data()

        assert result["name"] == "Тест Тестов"
        assert result["phone"] == "+7999123456"
        assert result["email"] == "test@test.com"
        assert result["telegram_usernames"] == ["testuser"]
        assert result["position"] == "Developer"
        assert result["company"] == "TestCorp"
        assert result["expected_salary_min"] == 100000
        assert result["expected_salary_max"] == 150000
        assert "resume_parsed" in result["tags"]
        assert result["extra_data"]["experience_years"] == 3
        assert result["extra_data"]["skills"] == ["Python", "FastAPI", "Django", "PostgreSQL", "Redis", "MongoDB"]

    def test_parsed_resume_default_values(self):
        """Тест значений по умолчанию ParsedResume."""
        resume = ParsedResume()

        assert resume.skills == []
        assert resume.education == []
        assert resume.experience == []
        assert resume.languages == []
        assert resume.links == []
        assert resume.parse_warnings == []
        assert resume.parse_confidence == 0.0
        assert resume.expected_salary_currency == "RUB"

    def test_parsed_resume_telegram_normalization(self):
        """Тест нормализации telegram username."""
        # С @
        resume1 = ParsedResume(telegram="@username")
        data1 = resume1.to_entity_data()
        assert data1["telegram_usernames"] == ["username"]

        # С ссылкой
        resume2 = ParsedResume(telegram="https://t.me/username")
        data2 = resume2.to_entity_data()
        assert data2["telegram_usernames"] == ["username"]

        # Без @
        resume3 = ParsedResume(telegram="username")
        data3 = resume3.to_entity_data()
        assert data3["telegram_usernames"] == ["username"]


class TestResumeParserServiceExtractJson:
    """Тесты извлечения JSON из ответа AI."""

    def test_extract_json_direct(self):
        """Тест прямого парсинга JSON."""
        service = ResumeParserService()
        text = '{"name": "Тест", "phone": "+7999"}'
        result = service._extract_json(text)

        assert result is not None
        assert result["name"] == "Тест"
        assert result["phone"] == "+7999"

    def test_extract_json_from_markdown(self):
        """Тест извлечения JSON из markdown блока."""
        service = ResumeParserService()
        text = """Вот результат:
        ```json
        {"name": "Тест", "phone": "+7999"}
        ```
        """
        result = service._extract_json(text)

        assert result is not None
        assert result["name"] == "Тест"

    def test_extract_json_from_braces(self):
        """Тест извлечения JSON по фигурным скобкам."""
        service = ResumeParserService()
        text = """Данные кандидата: {"name": "Тест"} - успешно распарсены."""
        result = service._extract_json(text)

        assert result is not None
        assert result["name"] == "Тест"

    def test_extract_json_invalid(self):
        """Тест обработки невалидного JSON."""
        service = ResumeParserService()
        text = "Это не JSON вообще"
        result = service._extract_json(text)

        assert result is None


class TestResumeParserServiceDictConversion:
    """Тесты конвертации словаря в ParsedResume."""

    def test_dict_to_parsed_resume_full(self, mock_ai_response):
        """Тест полной конвертации словаря."""
        service = ResumeParserService()
        result = service._dict_to_parsed_resume(mock_ai_response)

        assert result.name == "Иванов Иван Петрович"
        assert result.phone == "+7 (999) 123-45-67"
        assert result.email == "ivan.ivanov@email.com"
        assert result.telegram == "@ivan_developer"
        assert result.position == "Senior Python Developer"
        assert result.experience_years == 5
        assert result.expected_salary_min == 250000
        assert result.expected_salary_max == 350000
        assert len(result.skills) == 10
        assert len(result.education) == 1
        assert len(result.experience) == 2
        assert result.parse_confidence == 0.95

    def test_dict_to_parsed_resume_with_nulls(self):
        """Тест конвертации с null значениями."""
        service = ResumeParserService()
        data = {
            "name": "Тест",
            "phone": None,
            "email": None,
            "skills": None,
            "experience_years": None,
            "parse_confidence": None
        }
        result = service._dict_to_parsed_resume(data)

        assert result.name == "Тест"
        assert result.phone is None
        assert result.email is None
        assert result.skills == []
        assert result.experience_years is None
        assert result.parse_confidence == 0.5  # default

    def test_dict_to_parsed_resume_salary_string(self):
        """Тест парсинга зарплаты из строки."""
        service = ResumeParserService()
        data = {
            "expected_salary_min": "100 000",
            "expected_salary_max": "150000 руб"
        }
        result = service._dict_to_parsed_resume(data)

        assert result.expected_salary_min == 100000
        assert result.expected_salary_max == 150000


# ============================================================================
# INTEGRATION TESTS: API Endpoints
# ============================================================================

class TestParseResumeEndpoint:
    """Интеграционные тесты для POST /api/entities/parse-resume."""

    @pytest.mark.asyncio
    async def test_parse_resume_success(
        self, client, admin_user, admin_token, organization, org_owner,
        get_auth_headers, mock_ai_response, sample_resume_text, monkeypatch
    ):
        """Тест успешного парсинга резюме."""
        # Мокаем сервис парсинга
        mock_parsed = ParsedResume(**{
            k: v for k, v in mock_ai_response.items()
            if k in ParsedResume.__dataclass_fields__
        })

        async def mock_parse_resume(content, filename):
            return mock_parsed

        monkeypatch.setattr(
            "api.services.resume_parser.resume_parser_service.parse_resume",
            mock_parse_resume
        )

        # Создаём файл для загрузки
        file_content = sample_resume_text.encode('utf-8')
        files = {
            "file": ("resume.txt", io.BytesIO(file_content), "text/plain")
        }

        response = await client.post(
            "/api/entities/parse-resume",
            files=files,
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()

        assert data["name"] == "Иванов Иван Петрович"
        assert data["phone"] == "+7 (999) 123-45-67"
        assert data["email"] == "ivan.ivanov@email.com"
        assert data["position"] == "Senior Python Developer"
        assert data["expected_salary_min"] == 250000
        assert data["expected_salary_max"] == 350000
        assert len(data["skills"]) > 0
        assert data["parse_confidence"] == 0.95

    @pytest.mark.asyncio
    async def test_parse_resume_unsupported_format(
        self, client, admin_user, admin_token, organization, org_owner, get_auth_headers
    ):
        """Тест ошибки при неподдерживаемом формате файла."""
        files = {
            "file": ("resume.exe", io.BytesIO(b"binary content"), "application/octet-stream")
        }

        response = await client.post(
            "/api/entities/parse-resume",
            files=files,
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 400
        assert "Unsupported file format" in response.json()["detail"]  # текст ручки — по-английски

    @pytest.mark.asyncio
    async def test_parse_resume_file_too_large(
        self, client, admin_user, admin_token, organization, org_owner, get_auth_headers
    ):
        """Тест ошибки при слишком большом файле."""
        # Создаём файл > 20MB
        large_content = b"x" * (21 * 1024 * 1024)
        files = {
            "file": ("resume.txt", io.BytesIO(large_content), "text/plain")
        }

        response = await client.post(
            "/api/entities/parse-resume",
            files=files,
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 413

    @pytest.mark.asyncio
    async def test_parse_resume_unauthorized(self, client):
        """Тест ошибки без авторизации."""
        files = {
            "file": ("resume.txt", io.BytesIO(b"content"), "text/plain")
        }

        response = await client.post(
            "/api/entities/parse-resume",
            files=files
        )

        assert response.status_code == 401


class TestCreateEntityFromResumeEndpoint:
    """Интеграционные тесты для POST /api/entities/from-resume."""

    @pytest.mark.asyncio
    async def test_create_entity_from_resume_success(
        self, client, db_session, admin_user, admin_token, organization, org_owner,
        get_auth_headers, mock_ai_response, sample_resume_text, monkeypatch, tmp_path
    ):
        """Тест успешного создания Entity из резюме."""
        # Мокаем директорию для файлов
        monkeypatch.setattr(
            "api.routes.entities.ENTITY_FILES_DIR",
            tmp_path / "entity_files"
        )

        # Мокаем сервис парсинга
        mock_parsed = ParsedResume(**{
            k: v for k, v in mock_ai_response.items()
            if k in ParsedResume.__dataclass_fields__
        })

        async def mock_parse_resume(content, filename):
            return mock_parsed

        monkeypatch.setattr(
            "api.services.resume_parser.resume_parser_service.parse_resume",
            mock_parse_resume
        )

        # Создаём файл для загрузки
        file_content = sample_resume_text.encode('utf-8')
        files = {
            "file": ("resume.txt", io.BytesIO(file_content), "text/plain")
        }

        response = await client.post(
            "/api/entities/from-resume",
            files=files,
            data={"auto_attach_file": "true"},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()

        # Проверяем entity
        assert "entity" in data
        entity = data["entity"]
        assert entity["name"] == "Иванов Иван Петрович"
        assert entity["type"] == "candidate"
        assert entity["status"] == "new"
        assert entity["email"] == "ivan.ivanov@email.com"
        assert entity["expected_salary_min"] == 250000
        assert entity["expected_salary_max"] == 350000

        # Проверяем parsed_data
        assert "parsed_data" in data
        assert data["parsed_data"]["parse_confidence"] == 0.95

        # Проверяем file_id (должен быть создан)
        assert data["file_id"] is not None

        # Проверяем что Entity создан в БД
        result = await db_session.execute(
            select(Entity).where(Entity.id == entity["id"])
        )
        db_entity = result.scalar_one_or_none()
        assert db_entity is not None
        assert db_entity.name == "Иванов Иван Петрович"

    @pytest.mark.asyncio
    async def test_create_entity_from_resume_without_file_attach(
        self, client, db_session, admin_user, admin_token, organization, org_owner,
        get_auth_headers, mock_ai_response, sample_resume_text, monkeypatch
    ):
        """Тест создания Entity без прикрепления файла."""
        # Мокаем сервис парсинга
        mock_parsed = ParsedResume(**{
            k: v for k, v in mock_ai_response.items()
            if k in ParsedResume.__dataclass_fields__
        })

        async def mock_parse_resume(content, filename):
            return mock_parsed

        monkeypatch.setattr(
            "api.services.resume_parser.resume_parser_service.parse_resume",
            mock_parse_resume
        )

        file_content = sample_resume_text.encode('utf-8')
        files = {
            "file": ("resume.txt", io.BytesIO(file_content), "text/plain")
        }

        response = await client.post(
            "/api/entities/from-resume",
            files=files,
            data={"auto_attach_file": "false"},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()

        # file_id должен быть None
        assert data["file_id"] is None

    @pytest.mark.asyncio
    async def test_create_entity_from_resume_with_department(
        self, client, db_session, admin_user, admin_token, organization, org_owner,
        department, get_auth_headers, mock_ai_response, sample_resume_text, monkeypatch
    ):
        """Тест создания Entity с указанием отдела."""
        mock_parsed = ParsedResume(**{
            k: v for k, v in mock_ai_response.items()
            if k in ParsedResume.__dataclass_fields__
        })

        async def mock_parse_resume(content, filename):
            return mock_parsed

        monkeypatch.setattr(
            "api.services.resume_parser.resume_parser_service.parse_resume",
            mock_parse_resume
        )

        file_content = sample_resume_text.encode('utf-8')
        files = {
            "file": ("resume.txt", io.BytesIO(file_content), "text/plain")
        }

        response = await client.post(
            "/api/entities/from-resume",
            files=files,
            data={
                "department_id": str(department.id),
                "auto_attach_file": "false"
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()

        assert data["entity"]["department_id"] == department.id
        assert data["entity"]["department_name"] == department.name

    @pytest.mark.asyncio
    async def test_create_entity_from_resume_invalid_department(
        self, client, admin_user, admin_token, organization, org_owner,
        get_auth_headers, monkeypatch
    ):
        """Тест ошибки при неверном ID отдела."""
        mock_parsed = ParsedResume(name="Test")

        async def mock_parse_resume(content, filename):
            return mock_parsed

        monkeypatch.setattr(
            "api.services.resume_parser.resume_parser_service.parse_resume",
            mock_parse_resume
        )

        files = {
            "file": ("resume.txt", io.BytesIO(b"content"), "text/plain")
        }

        response = await client.post(
            "/api/entities/from-resume",
            files=files,
            data={
                "department_id": "99999",
                "auto_attach_file": "false"
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 400
        assert "invalid department" in response.json()["detail"].lower()  # текст ручки — по-английски

    @pytest.mark.asyncio
    async def test_create_entity_from_resume_parse_error(
        self, client, admin_user, admin_token, organization, org_owner,
        get_auth_headers, monkeypatch
    ):
        """Тест обработки ошибки парсинга."""
        async def mock_parse_resume(content, filename):
            raise ValueError("Не удалось извлечь текст из файла")

        monkeypatch.setattr(
            "api.services.resume_parser.resume_parser_service.parse_resume",
            mock_parse_resume
        )

        files = {
            "file": ("resume.pdf", io.BytesIO(b"invalid pdf"), "application/pdf")
        }

        response = await client.post(
            "/api/entities/from-resume",
            files=files,
            data={"auto_attach_file": "false"},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 400


class TestParseResumeServiceIntegration:
    """Интеграционные тесты для сервиса парсинга."""

    @pytest.mark.asyncio
    async def test_parse_resume_with_mocked_ai(
        self, mock_ai_response, sample_resume_text, monkeypatch
    ):
        """Тест полного цикла парсинга с моком AI."""
        # Мокаем document_parser
        async def mock_parse(file_bytes, filename):
            class MockResult:
                status = "parsed"
                content = sample_resume_text
                error = None
            return MockResult()

        monkeypatch.setattr(
            "api.services.resume_parser.document_parser.parse",
            mock_parse
        )

        # Мокаем AI клиент
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps(mock_ai_response))]

        mock_client = MagicMock()
        mock_client.messages = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        service = ResumeParserService()
        service._client = mock_client

        result = await service.parse_resume(b"fake pdf content", "resume.pdf")

        assert result.name == "Иванов Иван Петрович"
        assert result.email == "ivan.ivanov@email.com"
        assert result.parse_confidence == 0.95

    @pytest.mark.asyncio
    async def test_extract_text_unsupported_format(self):
        """Тест ошибки при неподдерживаемом формате."""
        service = ResumeParserService()

        with pytest.raises(ValueError) as exc_info:
            await service.extract_text_from_file(b"content", "file.exe")

        assert "Неподдерживаемый формат" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_parse_ai_short_text(self):
        """Тест AI парсинга слишком короткого текста."""
        service = ResumeParserService()

        result = await service.parse_resume_with_ai("short")

        assert result.parse_confidence == 0.0
        assert len(result.parse_warnings) > 0
        assert "короткий" in result.parse_warnings[0].lower()


# ============================================================================
# EDGE CASES
# ============================================================================

class TestResumeParserEdgeCases:
    """Тесты граничных случаев."""

    def test_parsed_resume_empty_entity_data(self):
        """Тест to_entity_data для пустого резюме."""
        resume = ParsedResume()
        data = resume.to_entity_data()

        assert data["name"] == "Неизвестный кандидат"
        assert data["phone"] is None
        assert data["email"] is None
        assert data["telegram_usernames"] == []
        assert "resume_parsed" in data["tags"]

    def test_parsed_resume_tags_limit(self):
        """Тест ограничения количества тегов из skills."""
        resume = ParsedResume(
            name="Test",
            skills=["skill1", "skill2", "skill3", "skill4", "skill5", "skill6", "skill7"]
        )
        data = resume.to_entity_data()

        # Должно быть resume_parsed + первые 5 навыков
        assert len(data["tags"]) == 6  # 1 + 5

    def test_dict_conversion_with_float_salary(self):
        """Тест конвертации зарплаты из float."""
        service = ResumeParserService()
        data = {
            "expected_salary_min": 100000.50,
            "expected_salary_max": 150000.99
        }
        result = service._dict_to_parsed_resume(data)

        assert result.expected_salary_min == 100000
        assert result.expected_salary_max == 150000

    def test_dict_conversion_empty_strings(self):
        """Тест обработки пустых строк."""
        service = ResumeParserService()
        data = {
            "name": "",
            "phone": "   ",
            "email": ""
        }
        result = service._dict_to_parsed_resume(data)

        assert result.name is None
        assert result.phone is None
        assert result.email is None
