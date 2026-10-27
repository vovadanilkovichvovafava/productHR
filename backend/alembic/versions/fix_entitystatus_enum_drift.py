"""Дрейф энумов: недостающие значения entitystatus в БД

Revision ID: fix_enum_drift
Revises: add_access_hub
Create Date: 2026-08-19

Проблема (техдолг №2 из ТЗ «Хаб доступов»): значения probation, transferred,
dismissed, quit существовали ТОЛЬКО за счёт ручных ALTER TYPE в start.sh.
Любой запуск мимо этого скрипта (локальный uvicorn, тесты против настоящего
PostgreSQL, контейнер с переопределённым entrypoint) оставлял БД без них — и
запись такого статуса падала с InvalidTextRepresentation. Доска «Статусы»
из-за этого читалась (там сравнение приведено к тексту), но не писалась.

Обратный дрейф (в applicationstage в БД лежат лишние new/practice/
tech_practice/is_interview, которых нет в Python-энуме) здесь НЕ трогаем:
PostgreSQL не умеет удалять значения из enum, а пересоздание типа потребовало
бы переписать все ссылающиеся колонки. Значения безвредны, пока их никто не
пишет; код их не использует (см. deprecated-блок в database.py).
"""
from alembic import op

revision = 'fix_enum_drift'
down_revision = 'add_access_hub'
branch_labels = None
depends_on = None

# Полный набор значений EntityStatus, которые должны быть в БД.
# IF NOT EXISTS делает шаг идемпотентным — прод, где start.sh их уже добавил,
# просто пройдёт мимо.
_ENTITY_STATUS_VALUES = [
    "new", "screening", "practice", "tech_practice", "is_interview",
    "offer", "hired", "probation", "transferred", "dismissed", "quit",
    "rejected", "withdrawn", "reserve",
    "interview", "active", "paused", "churned", "converted", "ended", "negotiation",
]


def upgrade():
    # ALTER TYPE ... ADD VALUE нельзя выполнять внутри транзакционного блока,
    # поэтому берём autocommit_block.
    with op.get_context().autocommit_block():
        for value in _ENTITY_STATUS_VALUES:
            op.execute(f"ALTER TYPE entitystatus ADD VALUE IF NOT EXISTS '{value}'")


def downgrade():
    # PostgreSQL не поддерживает удаление значений из enum-типа.
    pass
