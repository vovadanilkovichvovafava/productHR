"""Unit tests for the resume-text near-duplicate ('copy-paste') detector."""
from api.services.resume_text_twin import (
    normalize_resume_text,
    resume_text_blob,
    text_shingles,
    jaccard_similarity,
)


class TestNormalize:
    def test_lowercases_and_collapses_ws(self):
        assert normalize_resume_text("Разрабатывал   API\n\nна Python") == \
            "разрабатывал api на python"

    def test_strips_punctuation_and_digits(self):
        assert normalize_resume_text("2019-2021: Python, C++!") == "python c"


class TestBlob:
    def test_blob_joins_about_and_experience(self):
        extra = {
            "about": "Опытный разработчик",
            "experience": [
                {"description": "Писал сервисы", "achievements": ["ускорил сборку"]},
                {"description": "Вёл команду"},
            ],
        }
        blob = resume_text_blob(extra)
        assert "опытный разработчик" in blob
        assert "писал сервисы" in blob
        assert "ускорил сборку" in blob
        assert "вёл команду" in blob

    def test_blob_reads_extension_format(self):
        # magic_button (расширение) хранит summary + experience_descriptions.
        extra = {
            "summary": "Senior бэкенд разработчик",
            "experience_descriptions": ["Проектировал API", "Наставлял джунов"],
        }
        blob = resume_text_blob(extra)
        assert "senior бэкенд разработчик" in blob
        assert "проектировал api" in blob
        assert "наставлял джунов" in blob


class TestSimilarity:
    def test_identical_text_is_1(self):
        t = normalize_resume_text("писал сервисы на python и вёл команду разработки")
        s = text_shingles(t, n=3)
        assert jaccard_similarity(s, s) == 1.0

    def test_disjoint_text_is_0(self):
        a = text_shingles(normalize_resume_text("один два три четыре пять"), n=3)
        b = text_shingles(normalize_resume_text("шесть семь восемь девять десять"), n=3)
        assert jaccard_similarity(a, b) == 0.0

    def test_near_duplicate_above_threshold(self):
        base = "разрабатывал микросервисы на python внедрял ci cd вёл код ревью команды"
        copy = "разрабатывал микросервисы на python внедрял ci cd вёл ревью кода команды"
        a = text_shingles(normalize_resume_text(base), n=3)
        b = text_shingles(normalize_resume_text(copy), n=3)
        assert jaccard_similarity(a, b) >= 0.5

    def test_empty_shingles_is_0(self):
        assert jaccard_similarity(set(), set()) == 0.0


import pytest
from api.models.database import Entity, EntityType, Organization


class TestDetectResumeTextTwin:
    @pytest.mark.asyncio
    async def test_flags_near_identical_resume(self, db_session):
        from api.services.resume_text_twin import detect_resume_text_twin
        org = Organization(name="TwinOrg", slug="twin-org")
        db_session.add(org)
        await db_session.flush()
        text = {"about": "Разрабатывал микросервисы на python внедрял ci cd вёл код ревью команды разработки продукта"}
        a = Entity(org_id=org.id, type=EntityType.candidate, name="Иван Иванов", extra_data=text)
        db_session.add(a)
        await db_session.flush()
        b = Entity(org_id=org.id, type=EntityType.candidate, name="Пётр Петров",
                   extra_data={"about": text["about"]})
        db_session.add(b)
        await db_session.flush()

        twin_id, sim = await detect_resume_text_twin(db_session, b)
        assert twin_id == a.id
        assert sim >= 0.8
        meta = (b.extra_data or {}).get("text_twin")
        assert meta and meta["twin_id"] == a.id

    @pytest.mark.asyncio
    async def test_no_flag_for_unique_text(self, db_session):
        from api.services.resume_text_twin import detect_resume_text_twin
        org = Organization(name="UniqOrg", slug="uniq-org")
        db_session.add(org)
        await db_session.flush()
        a = Entity(org_id=org.id, type=EntityType.candidate, name="A A",
                   extra_data={"about": "совершенно уникальный текст про дизайн интерфейсов и типографику"})
        db_session.add(a)
        await db_session.flush()
        b = Entity(org_id=org.id, type=EntityType.candidate, name="B B",
                   extra_data={"about": "другой опыт в бухгалтерии налоговой отчётности и аудите предприятий"})
        db_session.add(b)
        await db_session.flush()
        twin_id, sim = await detect_resume_text_twin(db_session, b)
        assert twin_id is None

    @pytest.mark.asyncio
    async def test_text_twin_does_not_raise_merge_banner(self, db_session):
        """Похожий текст резюме — только мягкая пометка text_twin, БЕЗ плашки
        дубля (hidden_duplicate_id/meta). Решение ec2d0dd2: у разных людей
        анкеты по одному шаблону дают высокий Жаккар, и баннер предлагал
        слить трёх разных «Никит». Дубли ловит identity-детектор."""
        from api.services.resume_text_twin import detect_resume_text_twin
        org = Organization(name="BannerOrg", slug="banner-org")
        db_session.add(org)
        await db_session.flush()
        text = {"about": "Разрабатывал микросервисы на python внедрял ci cd вёл код ревью команды разработки продукта"}
        a = Entity(org_id=org.id, type=EntityType.candidate, name="Иван Иванов", extra_data=text)
        db_session.add(a)
        await db_session.flush()
        b = Entity(org_id=org.id, type=EntityType.candidate, name="Пётр Петров",
                   extra_data={"about": text["about"]})
        db_session.add(b)
        await db_session.flush()

        twin_id, sim = await detect_resume_text_twin(db_session, b)
        assert twin_id == a.id
        be = b.extra_data or {}
        assert be.get("text_twin", {}).get("twin_id") == a.id
        assert "hidden_duplicate_id" not in be
        assert "hidden_duplicate_meta" not in be

    @pytest.mark.asyncio
    async def test_does_not_clobber_existing_identity_match(self, db_session):
        """If an identity match (detect_archived_duplicate) already flagged the
        entity, the text-twin detector must NOT overwrite hidden_duplicate_id/meta —
        identity always wins the banner slot; the twin still surfaces via the
        /duplicates endpoint list, not by hijacking the banner."""
        from api.services.resume_text_twin import detect_resume_text_twin
        org = Organization(name="NoClobberOrg", slug="no-clobber-org")
        db_session.add(org)
        await db_session.flush()
        text = {"about": "Разрабатывал микросервисы на python внедрял ci cd вёл код ревью команды разработки продукта"}
        a = Entity(org_id=org.id, type=EntityType.candidate, name="Иван Иванов", extra_data=text)
        db_session.add(a)
        await db_session.flush()
        # Seed a pre-existing identity match on b, as detect_archived_duplicate
        # would have already done (it runs first on every intake path).
        seeded_meta = {
            "strength": "email", "confidence": 100,
            "reasons": ["Совпадает email"], "matched_id": 999999,
        }
        b = Entity(org_id=org.id, type=EntityType.candidate, name="Пётр Петров",
                   extra_data={
                       "about": text["about"],
                       "hidden_duplicate_id": 999999,
                       "hidden_duplicate_meta": seeded_meta,
                   })
        db_session.add(b)
        await db_session.flush()

        twin_id, sim = await detect_resume_text_twin(db_session, b)
        # Text-twin is still detected/returned...
        assert twin_id == a.id
        be = b.extra_data or {}
        assert be.get("text_twin", {}).get("twin_id") == a.id
        # ...but the identity flag on b is left untouched.
        assert be.get("hidden_duplicate_id") == 999999
        assert be.get("hidden_duplicate_meta") == seeded_meta

    @pytest.mark.asyncio
    async def test_no_backreference_on_twin(self, db_session):
        """Обратной плашки дубля на найденном двойнике (a) тоже нет: текстовое
        сходство merge не предлагает ни с одной стороны (ec2d0dd2)."""
        from api.services.resume_text_twin import detect_resume_text_twin
        org = Organization(name="BackrefOrg", slug="backref-org")
        db_session.add(org)
        await db_session.flush()
        text = {"about": "Разрабатывал микросервисы на python внедрял ci cd вёл код ревью команды разработки продукта"}
        a = Entity(org_id=org.id, type=EntityType.candidate, name="Иван Иванов", extra_data=text)
        db_session.add(a)
        await db_session.flush()
        b = Entity(org_id=org.id, type=EntityType.candidate, name="Пётр Петров",
                   extra_data={"about": text["about"]})
        db_session.add(b)
        await db_session.flush()

        await detect_resume_text_twin(db_session, b)
        ae = a.extra_data or {}
        assert "hidden_duplicate_id" not in ae
        assert "hidden_duplicate_meta" not in ae

    @pytest.mark.asyncio
    async def test_backreference_does_not_clobber_twins_identity_match(self, db_session):
        """If the twin (a) already carries its OWN identity-match flag, the
        backreference must not overwrite it."""
        from api.services.resume_text_twin import detect_resume_text_twin
        org = Organization(name="BackrefNoClobberOrg", slug="backref-no-clobber-org")
        db_session.add(org)
        await db_session.flush()
        text = {"about": "Разрабатывал микросервисы на python внедрял ci cd вёл код ревью команды разработки продукта"}
        seeded_meta = {
            "strength": "phone", "confidence": 100,
            "reasons": ["Совпадает телефон"], "matched_id": 555555,
        }
        a = Entity(org_id=org.id, type=EntityType.candidate, name="Иван Иванов",
                   extra_data={**text, "hidden_duplicate_id": 555555, "hidden_duplicate_meta": seeded_meta})
        db_session.add(a)
        await db_session.flush()
        b = Entity(org_id=org.id, type=EntityType.candidate, name="Пётр Петров",
                   extra_data={"about": text["about"]})
        db_session.add(b)
        await db_session.flush()

        await detect_resume_text_twin(db_session, b)
        ae = a.extra_data or {}
        assert ae.get("hidden_duplicate_id") == 555555
        assert ae.get("hidden_duplicate_meta") == seeded_meta
