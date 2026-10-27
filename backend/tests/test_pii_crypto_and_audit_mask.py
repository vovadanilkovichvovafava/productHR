"""Сторож: шифрование персональных файлов и маскирование их в журнале действий.

До 27.10.2026 ключ шифрования сканов паспортов и документов был
sha256(SECRET_KEY): смена секрета JWT делала все файлы нечитаемыми (500), а
перенос базы на сервер с другим SECRET_KEY — тоже. Реквизиты, адрес и
экстренный контакт лежали в журнале действий открытым текстом (хранится год).
"""
import base64

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException

from api.config import settings
from api.routes.employees import _decrypt_pii, _passport_fernet
from api.services.audit import clean_body


def _legacy_fernet(secret: str) -> Fernet:
    import hashlib
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest()))


def test_new_key_reads_old_files_and_encrypts_with_new(monkeypatch):
    old_blob = _legacy_fernet(settings.jwt_secret).encrypt(b"old-scan")
    new_key = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "pii_encryption_key", new_key)

    assert _decrypt_pii(old_blob) == b"old-scan"
    fresh = _passport_fernet().encrypt(b"new-scan")
    assert Fernet(new_key.encode()).decrypt(fresh) == b"new-scan"


def test_legacy_secret_reads_migrated_files(monkeypatch):
    # Файл зашифрован на другом сервере его SECRET_KEY (перенос базы MST).
    blob = _legacy_fernet("enceladus-old-secret").encrypt(b"migrated")
    monkeypatch.setattr(settings, "pii_legacy_secrets", "x, enceladus-old-secret")

    assert _decrypt_pii(blob) == b"migrated"


def test_unknown_key_is_409_not_500():
    blob = Fernet(Fernet.generate_key()).encrypt(b"lost")

    with pytest.raises(HTTPException) as e:
        _decrypt_pii(blob)
    assert e.value.status_code == 409


def test_audit_masks_employee_pii():
    body = clean_body(
        b'{"phone": "+7 999", "extra_data": {"payment_details": "2200 1234 5678 9010", '
        b'"address": "Minsk", "emergency_contact_phone": "+375", "passport_number": "AB123", '
        b'"birth_date": "1990-01-01", "first_name": "Ivan"}}',
        "application/json", None, "",
    )

    extra = body["extra_data"]
    for key in ("payment_details", "address", "emergency_contact_phone", "passport_number", "birth_date"):
        assert extra[key] == "***", key
    assert extra["first_name"] == "Ivan"
    assert body["phone"] == "+7 999"


def test_audit_masks_bulk_import_rows():
    body = clean_body(b'[{"email": "a@b.c", "payment_details": "card"}]', "application/json", None, "")

    assert body[0]["payment_details"] == "***"
    assert body[0]["email"] == "a@b.c"
