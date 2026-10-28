"""Лимиты больничных и семейных дней сотрудника (27.10.2026).

Было два разных числа: личный кабинет показывал 7 больничных и 2 семейных дня
(зашито в ручке баланса), а в записи сотрудника лежали 10 и 3 (умолчание
модели, их же правит HR в карточке). Решение владельца: правда — поля записи
сотрудника, по умолчанию 7 и 2; одобрение сверх лимита — с предупреждением.

Разовый шаг выравнивает записи со старым умолчанием (10 / 3) на 7 / 2: именно
эти числа сотрудники и так видели в кабинете. Отметка в data_migration_marks.
"""
import logging
from typing import Optional

from sqlalchemy import or_, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.database import DataMigrationMark, Employee

logger = logging.getLogger("hr-analyzer.leave_limits")

SICK_DAYS_DEFAULT = 7
FAMILY_DAYS_DEFAULT = 2
ALIGN_MARK = "leave_limits_7_2_2026_10_27"


def sick_total(emp: Employee) -> int:
    return emp.sick_days_total if emp.sick_days_total is not None else SICK_DAYS_DEFAULT


def family_total(emp: Employee) -> int:
    return emp.family_leave_days_total if emp.family_leave_days_total is not None else FAMILY_DAYS_DEFAULT


def limit_for(emp: Employee, leave_type: str) -> Optional[int]:
    """Лимит дней в рабочем году по типу заявки; None — без лимита."""
    if leave_type == "sick":
        return sick_total(emp)
    if leave_type == "family_leave":
        return family_total(emp)
    return None


async def align_leave_limits_once(db: AsyncSession) -> None:
    """10/3 (старое умолчание) → 7/2. Коммитит."""
    if await db.get(DataMigrationMark, ALIGN_MARK) is not None:
        return
    sick = await db.execute(
        update(Employee)
        .where(or_(Employee.sick_days_total == 10, Employee.sick_days_total.is_(None)))
        .values(sick_days_total=SICK_DAYS_DEFAULT)
    )
    family = await db.execute(
        update(Employee)
        .where(or_(Employee.family_leave_days_total == 3, Employee.family_leave_days_total.is_(None)))
        .values(family_leave_days_total=FAMILY_DAYS_DEFAULT)
    )
    db.add(DataMigrationMark(key=ALIGN_MARK))
    await db.commit()
    logger.info(
        "LEAVE_LIMITS align: больничные 10→7 у %s, семейные 3→2 у %s",
        sick.rowcount, family.rowcount,
    )
