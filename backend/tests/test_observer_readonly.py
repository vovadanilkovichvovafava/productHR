"""«Наблюдатель» (OrgMember.is_readonly) — что ему режут, а что нет.

Ментор видит ВЕСЬ HR и ничего в нём не меняет (запрос владельца 01.10.2026:
«Ты должен видеть кандидатов, но просто не исправлять»). Проверка одна на все
роуты — поэтому её поведение описано тестом, а не только кнопками на фронте.

Второй смысл теста — не дать спискам разъехаться: такой же белый список лежит на
клиенте (OBSERVER_WRITABLE_PREFIXES в frontend/src/services/api/client.ts), и его
сужение незаметно отняло бы у практик-лида его собственный раздел.
"""
import pytest

from api.services.auth import OBSERVER_WRITABLE_PREFIXES, observer_check_needed


@pytest.mark.parametrize(
    "method,path",
    [
        ("PUT", "/api/vacancies/applications/42"),
        ("PATCH", "/api/vacancies/applications/42/history/7"),
        ("DELETE", "/api/vacancies/applications/42/history/7"),
        ("POST", "/api/entities/9/notes"),
        ("PATCH", "/api/candidates/9267/status"),
        ("POST", "/api/vacancies"),
        ("DELETE", "/api/forms/3"),
        ("POST", "/api/users/invite"),
    ],
)
def test_hr_writes_are_checked(method, path):
    assert observer_check_needed(method, path) is True


@pytest.mark.parametrize(
    "path",
    [
        "/api/entities/9",
        "/api/vacancies/1/candidates",
        "/api/candidates/kanban",
    ],
)
def test_reads_are_never_checked(path):
    # Наблюдатель именно СМОТРИТ — на чтении лишнего запроса в базу быть не должно.
    for method in ("GET", "HEAD", "OPTIONS"):
        assert observer_check_needed(method, path) is False


@pytest.mark.parametrize(
    "path",
    [
        "/api/auth/logout",
        "/api/chats/5/messages",
        "/api/calls/3",
        "/api/interns/8",
        "/api/criteria",
        "/api/projects/2/tasks",
        "/api/project-statuses",
        "/api/timeoff/1",
        "/api/blockers",
        "/api/notifications/read",
    ],
)
def test_own_domain_stays_writable(path):
    # Практик-лид с флагом наблюдателя работает в своём отделе как обычно.
    assert observer_check_needed("POST", path) is False


def test_whitelist_contents():
    # Сторож против «тихого» сужения/расширения списка (и расхождения с фронтом).
    assert set(OBSERVER_WRITABLE_PREFIXES) == {
        "/api/auth/",
        "/api/chats",
        "/api/calls",
        "/api/interns",
        "/api/criteria",
        "/api/projects",
        "/api/project-statuses",
        "/api/timeoff",
        "/api/blockers",
        "/api/notifications",
    }
