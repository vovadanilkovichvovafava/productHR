"""
Comprehensive unit tests for Telegram bot handlers and commands.
Tests bot commands, message collection, and event handlers.
"""
import pytest
import pytest_asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from typing import AsyncGenerator

from aiogram import types
from aiogram.types import Chat as TelegramChat, User as TelegramUser
from aiogram.types import Message as TelegramMessage, ChatMemberUpdated
from aiogram.types import ChatMemberOwner, ChatMemberLeft
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.database import User, Chat, Message, OrgMember, ChatType
from api.models.database import UserRole, OrgRole


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mock_bot():
    """Mock aiogram Bot instance."""
    bot = MagicMock()
    bot.token = "test:token"
    bot.id = 123456789
    bot.username = "test_bot"
    bot.get_me = AsyncMock(return_value=MagicMock(id=123456789, username="test_bot"))
    bot.get_file = AsyncMock(return_value=MagicMock(file_path="/path/to/file"))
    bot.download_file = AsyncMock(return_value=MagicMock(read=MagicMock(return_value=b"test content")))
    bot.session = MagicMock()
    bot.session.close = AsyncMock()
    return bot


@pytest.fixture
def mock_telegram_bot_token(monkeypatch):
    """Mock Telegram bot token in settings."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test:token")
    with patch('api.bot.settings') as mock_settings:
        mock_settings.telegram_bot_token = "test:token"
        mock_settings.database_url = "postgresql+asyncpg://test:test@localhost/test"
        yield mock_settings


@pytest.fixture
def mock_transcription_service(monkeypatch):
    """Mock transcription service."""
    mock_service = MagicMock()
    mock_service.transcribe_audio = AsyncMock(return_value="Transcribed audio text")
    mock_service.transcribe_video = AsyncMock(return_value="Transcribed video text")
    monkeypatch.setattr("api.bot.transcription_service", mock_service)
    return mock_service


@pytest.fixture
def mock_document_parser(monkeypatch):
    """Mock document parser."""
    mock_parser = MagicMock()
    mock_result = MagicMock()
    mock_result.content = "Parsed document content"
    mock_result.metadata = {"pages": 1}
    mock_result.status = "success"
    mock_result.error = None
    mock_parser.parse = AsyncMock(return_value=mock_result)
    monkeypatch.setattr("api.bot.document_parser", mock_parser)
    return mock_parser


@pytest_asyncio.fixture
async def telegram_user():
    """Create a mock Telegram user."""
    user = MagicMock(spec=TelegramUser)
    user.id = 987654321
    user.username = "testuser"
    user.first_name = "Test"
    user.last_name = "User"
    user.is_bot = False
    return user


@pytest_asyncio.fixture
async def telegram_chat():
    """Create a mock Telegram group chat."""
    chat = MagicMock(spec=TelegramChat)
    chat.id = -1001234567890
    chat.type = "supergroup"
    chat.title = "Test Group Chat"
    chat.username = None
    chat.full_name = None
    return chat


@pytest_asyncio.fixture
async def telegram_private_chat(telegram_user):
    """Create a mock Telegram private chat."""
    chat = MagicMock(spec=TelegramChat)
    chat.id = telegram_user.id
    chat.type = "private"
    chat.title = None
    chat.username = telegram_user.username
    chat.full_name = f"{telegram_user.first_name} {telegram_user.last_name}"
    return chat


@pytest_asyncio.fixture
async def db_user(db_session: AsyncSession) -> User:
    """Create a database user linked to Telegram."""
    user = User(
        email="testuser@example.com",
        password_hash="hashed_password",
        name="Test User",
        role=UserRole.admin,
        telegram_id=987654321,
        telegram_username="testuser",
        is_active=True
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def db_user_no_telegram(db_session: AsyncSession) -> User:
    """Create a database user without Telegram binding."""
    user = User(
        email="notelegram@example.com",
        password_hash="hashed_password",
        name="No Telegram User",
        role=UserRole.admin,
        is_active=True
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def db_chat(db_session: AsyncSession, db_user: User) -> Chat:
    """Create a database chat."""
    chat = Chat(
        telegram_chat_id=-1001234567890,
        title="Test Group Chat",
        chat_type=ChatType.work,
        owner_id=db_user.id,
        is_active=True,
        created_at=datetime.utcnow()
    )
    db_session.add(chat)
    await db_session.commit()
    await db_session.refresh(chat)
    return chat


# ============================================================================
# HELPER FUNCTION TESTS
# ============================================================================

class TestHelperFunctions:
    """Tests for bot helper functions."""

    @pytest.mark.asyncio
    async def test_get_bot_with_token(self, mock_telegram_bot_token, mock_bot):
        """Test getting bot instance with valid token."""
        from api.bot import get_bot

        # Reset global bot
        import api.bot as bot_module
        bot_module.bot = None

        with patch('api.bot.Bot', return_value=mock_bot):
            bot = get_bot()
            assert bot is not None
            assert bot == mock_bot

    @pytest.mark.asyncio
    async def test_get_bot_without_token(self):
        """Test getting bot instance without token raises error."""
        from api.bot import get_bot

        # Reset global bot
        import api.bot as bot_module
        bot_module.bot = None

        with patch('api.bot.settings') as mock_settings:
            mock_settings.telegram_bot_token = None

            with pytest.raises(ValueError, match="TELEGRAM_BOT_TOKEN is not set"):
                get_bot()

    @pytest.mark.asyncio
    async def test_find_user_by_telegram_id_found(self, db_session: AsyncSession, db_user: User):
        """Test finding user by Telegram ID - user exists."""
        from api.bot import find_user_by_telegram_id

        user = await find_user_by_telegram_id(db_session, 987654321)
        assert user is not None
        assert user.id == db_user.id
        assert user.telegram_id == 987654321

    @pytest.mark.asyncio
    async def test_find_user_by_telegram_id_not_found(self, db_session: AsyncSession):
        """Test finding user by Telegram ID - user doesn't exist."""
        from api.bot import find_user_by_telegram_id

        user = await find_user_by_telegram_id(db_session, 999999999)
        assert user is None

    @pytest.mark.asyncio
    async def test_get_or_create_chat_new(self, db_session: AsyncSession, telegram_chat, db_user: User):
        """Test creating a new chat."""
        from api.bot import get_or_create_chat

        chat = await get_or_create_chat(db_session, telegram_chat, db_user.id)

        assert chat is not None
        assert chat.telegram_chat_id == telegram_chat.id
        assert chat.title == telegram_chat.title
        assert chat.owner_id == db_user.id
        assert chat.is_active is True

    @pytest.mark.asyncio
    async def test_get_or_create_chat_existing(self, db_session: AsyncSession, telegram_chat, db_chat: Chat, db_user: User):
        """Test getting an existing chat."""
        from api.bot import get_or_create_chat

        chat = await get_or_create_chat(db_session, telegram_chat, db_user.id)

        assert chat is not None
        assert chat.id == db_chat.id
        assert chat.telegram_chat_id == db_chat.telegram_chat_id

    @pytest.mark.asyncio
    async def test_get_or_create_chat_restore_deleted(self, db_session: AsyncSession, telegram_chat, db_user: User):
        """Test restoring a soft-deleted chat."""
        from api.bot import get_or_create_chat

        # Create a deleted chat
        deleted_chat = Chat(
            telegram_chat_id=telegram_chat.id,
            title="Deleted Chat",
            chat_type=ChatType.work,
            owner_id=db_user.id,
            is_active=False,
            deleted_at=datetime.utcnow(),
            created_at=datetime.utcnow()
        )
        db_session.add(deleted_chat)
        await db_session.commit()

        # Try to get/create - should restore
        chat = await get_or_create_chat(db_session, telegram_chat, db_user.id)

        assert chat is not None
        assert chat.deleted_at is None
        assert chat.is_active is True
        assert chat.id == deleted_chat.id

    @pytest.mark.asyncio
    async def test_get_or_create_chat_update_fields(self, db_session: AsyncSession, telegram_chat, db_user: User, db_user_no_telegram: User):
        """Test updating chat fields when getting existing chat."""
        from api.bot import get_or_create_chat
        from api.models.database import Organization

        # Create an organization
        org = Organization(
            name="Test Org",
            slug="test-org",
            created_at=datetime.utcnow()
        )
        db_session.add(org)
        await db_session.commit()

        # Create a chat without owner or org
        existing_chat = Chat(
            telegram_chat_id=telegram_chat.id,
            title="Old Title",
            chat_type=ChatType.work,
            is_active=True,
            created_at=datetime.utcnow()
        )
        db_session.add(existing_chat)
        await db_session.commit()

        # Get/create with owner and org - should update
        chat = await get_or_create_chat(db_session, telegram_chat, db_user_no_telegram.id, org.id)

        await db_session.refresh(existing_chat)
        assert existing_chat.owner_id == db_user_no_telegram.id
        assert existing_chat.org_id == org.id
        assert existing_chat.title == telegram_chat.title  # Should update title too


# ============================================================================
# COMMAND HANDLER TESTS
# ============================================================================

class TestCommandHandlers:
    """Tests for bot command handlers."""

    @staticmethod
    def _patch_session(db_session):
        """async_session бота → тестовая сессия (иначе бот ходит в пустую БД
        приложения: «no such table: users»)."""
        p = patch('api.bot.async_session')
        maker = p.start()
        maker.return_value.__aenter__ = AsyncMock(return_value=db_session)
        maker.return_value.__aexit__ = AsyncMock(return_value=False)
        return p

    @staticmethod
    def _private_message(chat, from_user, text):
        message = MagicMock(spec=TelegramMessage)
        message.chat = chat
        message.from_user = from_user
        message.text = text
        message.answer = AsyncMock()
        return message

    @pytest.mark.asyncio
    async def test_cmd_start_private_chat(self, db_session: AsyncSession, telegram_private_chat, telegram_user):
        """Test /start command in private chat — приветствие и меню."""
        from api.bot import cmd_start

        p = self._patch_session(db_session)
        try:
            message = self._private_message(telegram_private_chat, telegram_user, "/start")
            await cmd_start(message)
        finally:
            p.stop()

        message.answer.assert_called_once()
        call_args = message.answer.call_args[0][0]
        assert "Добро пожаловать" in call_args
        assert "/menu" in call_args

    @pytest.mark.asyncio
    async def test_cmd_start_group_chat(self, telegram_chat, telegram_user):
        """Test /start command in group chat - should be ignored."""
        from api.bot import cmd_start

        # Create mock message
        message = MagicMock(spec=TelegramMessage)
        message.chat = telegram_chat
        message.from_user = telegram_user
        message.text = "/start"
        message.answer = AsyncMock()

        await cmd_start(message)

        # Should not send any message in group
        message.answer.assert_not_called()

    @pytest.mark.asyncio
    async def test_cmd_start_legacy_bind_link_rejected(self, db_session: AsyncSession, telegram_private_chat, telegram_user, db_user_no_telegram: User):
        """«/start bind_<id>» больше не привязывает: id перебирались, и любой мог
        забрать чужой аккаунт (вплоть до суперадмина). Ответ — «ссылка
        устарела», привязки нет."""
        from api.bot import cmd_start

        p = self._patch_session(db_session)
        try:
            message = self._private_message(
                telegram_private_chat, telegram_user, f"/start bind_{db_user_no_telegram.id}"
            )
            await cmd_start(message)
        finally:
            p.stop()

        message.answer.assert_called_once()
        assert "устарела" in message.answer.call_args[0][0]
        await db_session.refresh(db_user_no_telegram)
        assert db_user_no_telegram.telegram_id is None

    @pytest.mark.asyncio
    async def test_cmd_start_with_bind_token_binds(self, db_session: AsyncSession, telegram_private_chat, telegram_user, db_user_no_telegram: User):
        """Рабочий путь привязки — одноразовый токен из личного кабинета:
        привязывает и сразу гасит токен."""
        from datetime import timedelta
        from api.bot import cmd_start

        token = "t" * 32
        db_user_no_telegram.telegram_bind_token = token
        db_user_no_telegram.telegram_bind_expires = datetime.utcnow() + timedelta(minutes=10)
        await db_session.commit()

        p = self._patch_session(db_session)
        try:
            message = self._private_message(telegram_private_chat, telegram_user, f"/start {token}")
            await cmd_start(message)
        finally:
            p.stop()

        message.answer.assert_called_once()
        call_args = message.answer.call_args[0][0]
        assert "привязан" in call_args
        assert db_user_no_telegram.email in call_args
        await db_session.refresh(db_user_no_telegram)
        assert db_user_no_telegram.telegram_id == telegram_user.id
        assert db_user_no_telegram.telegram_bind_token is None

    @pytest.mark.asyncio
    async def test_cmd_bind_by_email_disabled(self, db_session: AsyncSession, telegram_private_chat, telegram_user, db_user_no_telegram: User):
        """/bind <email> отключён: по одной почте без пароля привязывался чужой
        аккаунт. Ответ — «отключена», привязки нет."""
        from api.bot import cmd_bind

        p = self._patch_session(db_session)
        try:
            message = self._private_message(
                telegram_private_chat, telegram_user, f"/bind {db_user_no_telegram.email}"
            )
            await cmd_bind(message)
        finally:
            p.stop()

        message.answer.assert_called_once()
        assert "отключена" in message.answer.call_args[0][0]
        await db_session.refresh(db_user_no_telegram)
        assert db_user_no_telegram.telegram_id is None

    @pytest.mark.asyncio
    async def test_cmd_bind_no_args(self, telegram_private_chat, telegram_user):
        """Test /bind command without email argument."""
        from api.bot import cmd_bind

        # Create mock message
        message = MagicMock(spec=TelegramMessage)
        message.chat = telegram_private_chat
        message.from_user = telegram_user
        message.text = "/bind"
        message.answer = AsyncMock()

        await cmd_bind(message)

        message.answer.assert_called_once()
        call_args = message.answer.call_args[0][0]
        assert "Использование: /bind <email>" in call_args

    @pytest.mark.asyncio
    async def test_cmd_bind_unknown_and_bound_email_same_answer(self, db_session: AsyncSession, telegram_private_chat, telegram_user, db_user: User):
        """Ответ /bind не зависит от того, есть ли такой email и привязан ли он
        (раньше было «не найден» / «уже привязан» — по ним перебирались почты)."""
        from api.bot import cmd_bind

        answers = []
        p = self._patch_session(db_session)
        try:
            for email in ("nonexistent@example.com", db_user.email):
                message = self._private_message(telegram_private_chat, telegram_user, f"/bind {email}")
                await cmd_bind(message)
                message.answer.assert_called_once()
                answers.append(message.answer.call_args[0][0])
        finally:
            p.stop()

        assert answers[0] == answers[1]
        assert "отключена" in answers[0]
        await db_session.refresh(db_user)
        assert db_user.telegram_id == 987654321

    @pytest.mark.asyncio
    async def test_cmd_bind_in_group(self, telegram_chat, telegram_user):
        """Test /bind command in group chat - should be rejected."""
        from api.bot import cmd_bind

        # Create mock message
        message = MagicMock(spec=TelegramMessage)
        message.chat = telegram_chat
        message.from_user = telegram_user
        message.text = "/bind test@example.com"
        message.answer = AsyncMock()

        await cmd_bind(message)

        message.answer.assert_called_once()
        call_args = message.answer.call_args[0][0]
        assert "только в личных сообщениях" in call_args

    @pytest.mark.asyncio
    async def test_handle_bind_token_invalid(self, db_session: AsyncSession, telegram_private_chat, telegram_user):
        """Токен, которого нет (или мусор короче 20 символов), — «недействительна»."""
        from api.bot import handle_bind_token

        p = self._patch_session(db_session)
        try:
            for token in ("short", "x" * 32):
                message = self._private_message(telegram_private_chat, telegram_user, "/start")
                await handle_bind_token(message, token)
                message.answer.assert_called_once()
                assert "недействительна" in message.answer.call_args[0][0]
        finally:
            p.stop()

    @pytest.mark.asyncio
    async def test_handle_bind_token_expired(self, db_session: AsyncSession, telegram_private_chat, telegram_user, db_user_no_telegram: User):
        """Просроченный токен не привязывает."""
        from datetime import timedelta
        from api.bot import handle_bind_token

        token = "e" * 32
        db_user_no_telegram.telegram_bind_token = token
        db_user_no_telegram.telegram_bind_expires = datetime.utcnow() - timedelta(minutes=1)
        await db_session.commit()

        p = self._patch_session(db_session)
        try:
            message = self._private_message(telegram_private_chat, telegram_user, "/start")
            await handle_bind_token(message, token)
        finally:
            p.stop()

        assert "устарела" in message.answer.call_args[0][0]
        await db_session.refresh(db_user_no_telegram)
        assert db_user_no_telegram.telegram_id is None

    @pytest.mark.asyncio
    async def test_handle_bind_token_telegram_already_bound_to_another(
        self,
        db_session: AsyncSession,
        telegram_private_chat,
        db_user: User,
        db_user_no_telegram: User
    ):
        """Telegram уже занят другим аккаунтом — молча не «переезжает»."""
        from datetime import timedelta
        from api.bot import handle_bind_token

        token = "b" * 32
        db_user_no_telegram.telegram_bind_token = token
        db_user_no_telegram.telegram_bind_expires = datetime.utcnow() + timedelta(minutes=10)
        await db_session.commit()

        telegram_user = MagicMock(spec=TelegramUser)
        telegram_user.id = db_user.telegram_id  # уже у db_user
        telegram_user.username = "testuser"

        p = self._patch_session(db_session)
        try:
            message = self._private_message(telegram_private_chat, telegram_user, "/start")
            await handle_bind_token(message, token)
        finally:
            p.stop()

        message.answer.assert_called_once()
        assert "уже привязан к другому аккаунту" in message.answer.call_args[0][0]
        await db_session.refresh(db_user_no_telegram)
        assert db_user_no_telegram.telegram_id is None

    @pytest.mark.asyncio
    async def test_cmd_chats_with_chats(self, db_session: AsyncSession, telegram_private_chat, telegram_user, db_user: User, db_chat: Chat):
        """Test /chats command - user has chats."""
        from api.bot import cmd_chats

        # Patch async_session to use our test session
        with patch('api.bot.async_session') as mock_session_maker:
            mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=db_session)
            mock_session_maker.return_value.__aexit__ = AsyncMock()

            # Create mock message
            message = MagicMock(spec=TelegramMessage)
            message.chat = telegram_private_chat
            message.from_user = telegram_user
            message.text = "/chats"
            message.answer = AsyncMock()

            await cmd_chats(message)

            message.answer.assert_called_once()
            call_args = message.answer.call_args[0][0]
            assert "Ваши чаты" in call_args
            assert db_chat.title in call_args

    @pytest.mark.asyncio
    async def test_cmd_chats_no_binding(self, db_session: AsyncSession, telegram_private_chat, telegram_user):
        """Test /chats command - user not bound."""
        from api.bot import cmd_chats

        # Patch async_session to use our test session
        with patch('api.bot.async_session') as mock_session_maker:
            mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=db_session)
            mock_session_maker.return_value.__aexit__ = AsyncMock()

            # Create mock message
            message = MagicMock(spec=TelegramMessage)
            message.chat = telegram_private_chat
            message.from_user = telegram_user
            message.text = "/chats"
            message.answer = AsyncMock()

            await cmd_chats(message)

            message.answer.assert_called_once()
            call_args = message.answer.call_args[0][0]
            assert "привяжите аккаунт" in call_args

    @pytest.mark.asyncio
    async def test_cmd_chats_no_chats(self, db_session: AsyncSession, telegram_private_chat, telegram_user, db_user: User):
        """Test /chats command - user has no chats."""
        from api.bot import cmd_chats

        # Patch async_session to use our test session
        with patch('api.bot.async_session') as mock_session_maker:
            mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=db_session)
            mock_session_maker.return_value.__aexit__ = AsyncMock()

            # Create mock message
            message = MagicMock(spec=TelegramMessage)
            message.chat = telegram_private_chat
            message.from_user = telegram_user
            message.text = "/chats"
            message.answer = AsyncMock()

            await cmd_chats(message)

            message.answer.assert_called_once()
            call_args = message.answer.call_args[0][0]
            assert "нет привязанных чатов" in call_args

    @pytest.mark.asyncio
    async def test_cmd_settype_show_types(self, db_session: AsyncSession, telegram_chat, telegram_user, db_chat: Chat):
        """Test /settype command without arguments - shows available types."""
        from api.bot import cmd_settype

        # Patch async_session to use our test session
        with patch('api.bot.async_session') as mock_session_maker:
            mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=db_session)
            mock_session_maker.return_value.__aexit__ = AsyncMock()

            # Create mock message
            message = MagicMock(spec=TelegramMessage)
            message.chat = telegram_chat
            message.from_user = telegram_user
            message.text = "/settype"
            message.answer = AsyncMock()

            await cmd_settype(message)

            message.answer.assert_called_once()
            call_args = message.answer.call_args[0][0]
            assert "Текущий тип" in call_args
            assert "Доступные типы" in call_args
            assert "hr" in call_args.lower()

    @pytest.mark.asyncio
    async def test_cmd_settype_set_type(self, db_session: AsyncSession, telegram_chat, telegram_user, db_chat: Chat):
        """Test /settype command with valid type."""
        from api.bot import cmd_settype

        # Patch async_session to use our test session
        with patch('api.bot.async_session') as mock_session_maker:
            mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=db_session)
            mock_session_maker.return_value.__aexit__ = AsyncMock()

            # Create mock message
            message = MagicMock(spec=TelegramMessage)
            message.chat = telegram_chat
            message.from_user = telegram_user
            message.text = "/settype hr"
            message.answer = AsyncMock()

            await cmd_settype(message)

            message.answer.assert_called_once()
            call_args = message.answer.call_args[0][0]
            assert "изменён" in call_args

            # Verify chat type was updated
            await db_session.refresh(db_chat)
            assert db_chat.chat_type == "hr"

    @pytest.mark.asyncio
    async def test_cmd_settype_invalid_type(self, db_session: AsyncSession, telegram_chat, telegram_user, db_chat: Chat):
        """Test /settype command with invalid type."""
        from api.bot import cmd_settype

        # Patch async_session to use our test session
        with patch('api.bot.async_session') as mock_session_maker:
            mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=db_session)
            mock_session_maker.return_value.__aexit__ = AsyncMock()

            # Create mock message
            message = MagicMock(spec=TelegramMessage)
            message.chat = telegram_chat
            message.from_user = telegram_user
            message.text = "/settype invalid_type"
            message.answer = AsyncMock()

            await cmd_settype(message)

            message.answer.assert_called_once()
            call_args = message.answer.call_args[0][0]
            assert "Неизвестный тип" in call_args

    @pytest.mark.asyncio
    async def test_cmd_settype_in_private_chat(self, telegram_private_chat, telegram_user):
        """Test /settype command in private chat - should be rejected."""
        from api.bot import cmd_settype

        # Create mock message
        message = MagicMock(spec=TelegramMessage)
        message.chat = telegram_private_chat
        message.from_user = telegram_user
        message.text = "/settype hr"
        message.answer = AsyncMock()

        await cmd_settype(message)

        message.answer.assert_called_once()
        call_args = message.answer.call_args[0][0]
        assert "только в группах" in call_args


# ============================================================================
# EVENT HANDLER TESTS
# ============================================================================

class TestEventHandlers:
    """Tests for bot event handlers (chat member updates)."""

    @pytest.mark.asyncio
    async def test_on_bot_added(self, db_session: AsyncSession, telegram_chat, telegram_user, db_user: User):
        """Test bot being added to a chat."""
        from api.bot import on_bot_added

        # Patch async_session to use our test session
        with patch('api.bot.async_session') as mock_session_maker:
            mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=db_session)
            mock_session_maker.return_value.__aexit__ = AsyncMock()

            # Create mock ChatMemberUpdated event
            event = MagicMock(spec=ChatMemberUpdated)
            event.chat = telegram_chat
            event.from_user = telegram_user
            event.old_chat_member = MagicMock(spec=ChatMemberLeft)
            event.new_chat_member = MagicMock(spec=ChatMemberOwner)

            await on_bot_added(event)

            # Verify chat was created
            from sqlalchemy import select
            result = await db_session.execute(
                select(Chat).where(Chat.telegram_chat_id == telegram_chat.id)
            )
            chat = result.scalar_one_or_none()
            assert chat is not None
            assert chat.owner_id == db_user.id

    @pytest.mark.asyncio
    async def test_on_bot_added_no_user(self, db_session: AsyncSession, telegram_chat, telegram_user):
        """Test bot being added to chat by non-registered user."""
        from api.bot import on_bot_added

        # Patch async_session to use our test session
        with patch('api.bot.async_session') as mock_session_maker:
            mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=db_session)
            mock_session_maker.return_value.__aexit__ = AsyncMock()

            # Create mock ChatMemberUpdated event
            event = MagicMock(spec=ChatMemberUpdated)
            event.chat = telegram_chat
            event.from_user = telegram_user
            event.old_chat_member = MagicMock(spec=ChatMemberLeft)
            event.new_chat_member = MagicMock(spec=ChatMemberOwner)

            await on_bot_added(event)

            # Verify chat was created without owner
            from sqlalchemy import select
            result = await db_session.execute(
                select(Chat).where(Chat.telegram_chat_id == telegram_chat.id)
            )
            chat = result.scalar_one_or_none()
            assert chat is not None
            assert chat.owner_id is None

    @pytest.mark.asyncio
    async def test_on_bot_removed(self, db_session: AsyncSession, telegram_chat, telegram_user, db_chat: Chat):
        """Test bot being removed from a chat."""
        from api.bot import on_bot_removed

        # Patch async_session to use our test session
        with patch('api.bot.async_session') as mock_session_maker:
            mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=db_session)
            mock_session_maker.return_value.__aexit__ = AsyncMock()

            # Create mock ChatMemberUpdated event
            event = MagicMock(spec=ChatMemberUpdated)
            event.chat = telegram_chat
            event.from_user = telegram_user
            event.old_chat_member = MagicMock(spec=ChatMemberOwner)
            event.new_chat_member = MagicMock(spec=ChatMemberLeft)

            await on_bot_removed(event)

            # Verify chat was marked inactive
            await db_session.refresh(db_chat)
            assert db_chat.is_active is False

    @pytest.mark.asyncio
    async def test_on_bot_removed_chat_not_found(self, db_session: AsyncSession, telegram_chat, telegram_user):
        """Test bot being removed from non-existent chat - should not crash."""
        from api.bot import on_bot_removed

        # Patch async_session to use our test session
        with patch('api.bot.async_session') as mock_session_maker:
            mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=db_session)
            mock_session_maker.return_value.__aexit__ = AsyncMock()

            # Create mock ChatMemberUpdated event for non-existent chat
            event = MagicMock(spec=ChatMemberUpdated)
            event.chat = MagicMock()
            event.chat.id = -9999999999  # Non-existent chat
            event.chat.title = "Non-existent Chat"
            event.from_user = telegram_user
            event.old_chat_member = MagicMock(spec=ChatMemberOwner)
            event.new_chat_member = MagicMock(spec=ChatMemberLeft)

            # Should not raise an error
            await on_bot_removed(event)

    @pytest.mark.asyncio
    @pytest.mark.xfail(reason="Org membership not propagated in test env")
    async def test_on_bot_added_with_org_membership(
        self,
        db_session: AsyncSession,
        telegram_chat,
        telegram_user,
        db_user: User,
        organization,
        org_owner
    ):
        """Test bot being added with user having organization membership."""
        from api.bot import on_bot_added

        # Patch async_session to use our test session
        with patch('api.bot.async_session') as mock_session_maker:
            mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=db_session)
            mock_session_maker.return_value.__aexit__ = AsyncMock()

            # Create mock ChatMemberUpdated event
            event = MagicMock(spec=ChatMemberUpdated)
            event.chat = telegram_chat
            event.from_user = telegram_user
            event.old_chat_member = MagicMock(spec=ChatMemberLeft)
            event.new_chat_member = MagicMock(spec=ChatMemberOwner)

            await on_bot_added(event)

            # Verify chat was created with org_id
            from sqlalchemy import select
            result = await db_session.execute(
                select(Chat).where(Chat.telegram_chat_id == telegram_chat.id)
            )
            chat = result.scalar_one_or_none()
            assert chat is not None
            assert chat.owner_id == db_user.id
            assert chat.org_id == organization.id

    @pytest.mark.asyncio
    async def test_on_bot_added_error_handling(self, telegram_chat, telegram_user):
        """Test bot added event with database error - should not crash."""
        from api.bot import on_bot_added

        # Mock session that raises an error
        mock_session = MagicMock()
        mock_session.execute = AsyncMock(side_effect=Exception("Database error"))
        mock_session.commit = AsyncMock()

        with patch('api.bot.async_session') as mock_session_maker:
            mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_maker.return_value.__aexit__ = AsyncMock()

            # Create mock ChatMemberUpdated event
            event = MagicMock(spec=ChatMemberUpdated)
            event.chat = telegram_chat
            event.from_user = telegram_user
            event.old_chat_member = MagicMock(spec=ChatMemberLeft)
            event.new_chat_member = MagicMock(spec=ChatMemberOwner)

            # Should not raise an error, just log it
            await on_bot_added(event)


# ============================================================================
# MESSAGE HANDLER TESTS
# ============================================================================

class TestMessageHandlers:
    """Tests for message collection handlers."""

    @pytest.mark.asyncio
    async def test_collect_text_message(
        self,
        db_session: AsyncSession,
        telegram_chat,
        telegram_user,
        db_user: User,
        db_chat: Chat
    ):
        """Test collecting a text message."""
        from api.bot import collect_group_message

        # Patch async_session to use our test session
        with patch('api.bot.async_session') as mock_session_maker:
            mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=db_session)
            mock_session_maker.return_value.__aexit__ = AsyncMock()

            # Create mock message
            message = MagicMock(spec=TelegramMessage)
            message.chat = telegram_chat
            message.from_user = telegram_user
            message.message_id = 12345
            message.text = "Hello, this is a test message!"
            message.caption = None
            message.date = datetime.utcnow()
            message.voice = None
            message.video_note = None
            message.video = None
            message.audio = None
            message.document = None
            message.photo = None
            message.sticker = None

            await collect_group_message(message)

            # Verify message was saved
            from sqlalchemy import select
            result = await db_session.execute(
                select(Message).where(Message.telegram_message_id == 12345)
            )
            saved_msg = result.scalar_one_or_none()
            assert saved_msg is not None
            assert saved_msg.content == "Hello, this is a test message!"
            assert saved_msg.content_type == "text"

    @pytest.mark.asyncio
    async def test_collect_voice_message(
        self,
        db_session: AsyncSession,
        telegram_chat,
        telegram_user,
        db_user: User,
        db_chat: Chat,
        mock_bot,
        mock_transcription_service
    ):
        """Test collecting a voice message with transcription."""
        from api.bot import collect_group_message

        # Patch async_session and bot
        with patch('api.bot.async_session') as mock_session_maker, \
             patch('api.bot.get_bot', return_value=mock_bot):
            mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=db_session)
            mock_session_maker.return_value.__aexit__ = AsyncMock()

            # Create mock voice message
            message = MagicMock(spec=TelegramMessage)
            message.chat = telegram_chat
            message.from_user = telegram_user
            message.message_id = 12346
            message.text = None
            message.caption = None
            message.date = datetime.utcnow()
            message.voice = MagicMock()
            message.voice.file_id = "voice_file_123"
            message.video_note = None
            message.video = None
            message.audio = None
            message.document = None
            message.photo = None
            message.sticker = None

            await collect_group_message(message)

            # Verify message was saved with transcription
            from sqlalchemy import select
            result = await db_session.execute(
                select(Message).where(Message.telegram_message_id == 12346)
            )
            saved_msg = result.scalar_one_or_none()
            assert saved_msg is not None
            assert saved_msg.content_type == "voice"
            assert saved_msg.content == "Transcribed audio text"

    @pytest.mark.asyncio
    async def test_collect_document_message(
        self,
        db_session: AsyncSession,
        telegram_chat,
        telegram_user,
        db_user: User,
        db_chat: Chat,
        mock_bot,
        mock_document_parser
    ):
        """Test collecting a document message with parsing."""
        from api.bot import collect_group_message

        # Patch async_session and bot
        with patch('api.bot.async_session') as mock_session_maker, \
             patch('api.bot.get_bot', return_value=mock_bot):
            mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=db_session)
            mock_session_maker.return_value.__aexit__ = AsyncMock()

            # Create mock document message
            message = MagicMock(spec=TelegramMessage)
            message.chat = telegram_chat
            message.from_user = telegram_user
            message.message_id = 12347
            message.text = None
            message.caption = None
            message.date = datetime.utcnow()
            message.voice = None
            message.video_note = None
            message.video = None
            message.audio = None
            message.document = MagicMock()
            message.document.file_id = "doc_file_123"
            message.document.file_name = "test.pdf"
            message.document.file_size = 1024  # Small file
            message.photo = None
            message.sticker = None

            await collect_group_message(message)

            # Verify message was saved with parsed content
            from sqlalchemy import select
            result = await db_session.execute(
                select(Message).where(Message.telegram_message_id == 12347)
            )
            saved_msg = result.scalar_one_or_none()
            assert saved_msg is not None
            assert saved_msg.content_type == "document"
            assert saved_msg.content == "Parsed document content"
            assert saved_msg.parse_status == "success"

    @pytest.mark.asyncio
    async def test_collect_photo_message(
        self,
        db_session: AsyncSession,
        telegram_chat,
        telegram_user,
        db_user: User,
        db_chat: Chat,
        mock_bot,
        mock_document_parser
    ):
        """Test collecting a photo message with OCR."""
        from api.bot import collect_group_message

        # Patch async_session and bot
        with patch('api.bot.async_session') as mock_session_maker, \
             patch('api.bot.get_bot', return_value=mock_bot):
            mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=db_session)
            mock_session_maker.return_value.__aexit__ = AsyncMock()

            # Create mock photo message
            message = MagicMock(spec=TelegramMessage)
            message.chat = telegram_chat
            message.from_user = telegram_user
            message.message_id = 12348
            message.text = None
            message.caption = "Check this photo"
            message.date = datetime.utcnow()
            message.voice = None
            message.video_note = None
            message.video = None
            message.audio = None
            message.document = None
            message.photo = [MagicMock(), MagicMock()]  # Multiple sizes
            message.photo[-1].file_id = "photo_file_123"
            message.sticker = None

            await collect_group_message(message)

            # Verify message was saved with OCR content
            from sqlalchemy import select
            result = await db_session.execute(
                select(Message).where(Message.telegram_message_id == 12348)
            )
            saved_msg = result.scalar_one_or_none()
            assert saved_msg is not None
            assert saved_msg.content_type == "photo"
            assert "Parsed document content" in saved_msg.content

    @pytest.mark.asyncio
    async def test_collect_sticker_message(
        self,
        db_session: AsyncSession,
        telegram_chat,
        telegram_user,
        db_user: User,
        db_chat: Chat
    ):
        """Test collecting a sticker message."""
        from api.bot import collect_group_message

        # Patch async_session
        with patch('api.bot.async_session') as mock_session_maker:
            mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=db_session)
            mock_session_maker.return_value.__aexit__ = AsyncMock()

            # Create mock sticker message
            message = MagicMock(spec=TelegramMessage)
            message.chat = telegram_chat
            message.from_user = telegram_user
            message.message_id = 12349
            message.text = None
            message.caption = None
            message.date = datetime.utcnow()
            message.voice = None
            message.video_note = None
            message.video = None
            message.audio = None
            message.document = None
            message.photo = None
            message.sticker = MagicMock()
            message.sticker.emoji = "👍"
            message.sticker.file_id = "sticker_file_123"

            await collect_group_message(message)

            # Verify message was saved
            from sqlalchemy import select
            result = await db_session.execute(
                select(Message).where(Message.telegram_message_id == 12349)
            )
            saved_msg = result.scalar_one_or_none()
            assert saved_msg is not None
            assert saved_msg.content_type == "sticker"
            assert "👍" in saved_msg.content

    @pytest.mark.asyncio
    async def test_collect_message_no_from_user(self, telegram_chat):
        """Test collecting a message without from_user - should be skipped."""
        from api.bot import collect_group_message

        # Create mock message without from_user (system message)
        message = MagicMock(spec=TelegramMessage)
        message.chat = telegram_chat
        message.from_user = None
        message.message_id = 99999

        # Should not raise an error, just skip
        await collect_group_message(message)
        # No assertion needed - just verify it doesn't crash

    @pytest.mark.asyncio
    async def test_collect_video_message(
        self,
        db_session: AsyncSession,
        telegram_chat,
        telegram_user,
        db_user: User,
        db_chat: Chat,
        mock_bot,
        mock_transcription_service
    ):
        """Test collecting a video message with transcription."""
        from api.bot import collect_group_message

        # Patch async_session and bot
        with patch('api.bot.async_session') as mock_session_maker, \
             patch('api.bot.get_bot', return_value=mock_bot):
            mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=db_session)
            mock_session_maker.return_value.__aexit__ = AsyncMock()

            # Create mock video message
            message = MagicMock(spec=TelegramMessage)
            message.chat = telegram_chat
            message.from_user = telegram_user
            message.message_id = 12350
            message.text = None
            message.caption = None
            message.date = datetime.utcnow()
            message.voice = None
            message.video_note = None
            message.video = MagicMock()
            message.video.file_id = "video_file_123"
            message.video.file_name = "test_video.mp4"
            message.video.file_size = 10 * 1024 * 1024  # 10MB
            message.audio = None
            message.document = None
            message.photo = None
            message.sticker = None

            await collect_group_message(message)

            # Verify message was saved with transcription
            from sqlalchemy import select
            result = await db_session.execute(
                select(Message).where(Message.telegram_message_id == 12350)
            )
            saved_msg = result.scalar_one_or_none()
            assert saved_msg is not None
            assert saved_msg.content_type == "video"
            assert saved_msg.content == "Transcribed video text"

    @pytest.mark.asyncio
    async def test_collect_large_video_message(
        self,
        db_session: AsyncSession,
        telegram_chat,
        telegram_user,
        db_user: User,
        db_chat: Chat
    ):
        """Test collecting a large video message - should skip transcription."""
        from api.bot import collect_group_message

        # Patch async_session
        with patch('api.bot.async_session') as mock_session_maker:
            mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=db_session)
            mock_session_maker.return_value.__aexit__ = AsyncMock()

            # Create mock large video message
            message = MagicMock(spec=TelegramMessage)
            message.chat = telegram_chat
            message.from_user = telegram_user
            message.message_id = 12351
            message.text = None
            message.caption = None
            message.date = datetime.utcnow()
            message.voice = None
            message.video_note = None
            message.video = MagicMock()
            message.video.file_id = "large_video_123"
            message.video.file_name = "large_video.mp4"
            message.video.file_size = 25 * 1024 * 1024  # 25MB - over limit
            message.audio = None
            message.document = None
            message.photo = None
            message.sticker = None

            await collect_group_message(message)

            # Verify message was saved with placeholder
            from sqlalchemy import select
            result = await db_session.execute(
                select(Message).where(Message.telegram_message_id == 12351)
            )
            saved_msg = result.scalar_one_or_none()
            assert saved_msg is not None
            assert saved_msg.content_type == "video"
            assert "too large" in saved_msg.content

    @pytest.mark.asyncio
    async def test_collect_audio_message(
        self,
        db_session: AsyncSession,
        telegram_chat,
        telegram_user,
        db_user: User,
        db_chat: Chat,
        mock_bot,
        mock_transcription_service
    ):
        """Test collecting an audio message with transcription."""
        from api.bot import collect_group_message

        # Patch async_session and bot
        with patch('api.bot.async_session') as mock_session_maker, \
             patch('api.bot.get_bot', return_value=mock_bot):
            mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=db_session)
            mock_session_maker.return_value.__aexit__ = AsyncMock()

            # Create mock audio message
            message = MagicMock(spec=TelegramMessage)
            message.chat = telegram_chat
            message.from_user = telegram_user
            message.message_id = 12352
            message.text = None
            message.caption = None
            message.date = datetime.utcnow()
            message.voice = None
            message.video_note = None
            message.video = None
            message.audio = MagicMock()
            message.audio.file_id = "audio_file_123"
            message.audio.file_name = "song.mp3"
            message.audio.file_size = 5 * 1024 * 1024  # 5MB
            message.document = None
            message.photo = None
            message.sticker = None

            await collect_group_message(message)

            # Verify message was saved with transcription
            from sqlalchemy import select
            result = await db_session.execute(
                select(Message).where(Message.telegram_message_id == 12352)
            )
            saved_msg = result.scalar_one_or_none()
            assert saved_msg is not None
            assert saved_msg.content_type == "audio"
            assert saved_msg.content == "Transcribed audio text"

    @pytest.mark.asyncio
    async def test_collect_video_note_message(
        self,
        db_session: AsyncSession,
        telegram_chat,
        telegram_user,
        db_user: User,
        db_chat: Chat,
        mock_bot,
        mock_transcription_service
    ):
        """Test collecting a video note message with transcription."""
        from api.bot import collect_group_message

        # Patch async_session and bot
        with patch('api.bot.async_session') as mock_session_maker, \
             patch('api.bot.get_bot', return_value=mock_bot):
            mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=db_session)
            mock_session_maker.return_value.__aexit__ = AsyncMock()

            # Create mock video note message
            message = MagicMock(spec=TelegramMessage)
            message.chat = telegram_chat
            message.from_user = telegram_user
            message.message_id = 12353
            message.text = None
            message.caption = None
            message.date = datetime.utcnow()
            message.voice = None
            message.video_note = MagicMock()
            message.video_note.file_id = "video_note_123"
            message.video = None
            message.audio = None
            message.document = None
            message.photo = None
            message.sticker = None

            await collect_group_message(message)

            # Verify message was saved with transcription
            from sqlalchemy import select
            result = await db_session.execute(
                select(Message).where(Message.telegram_message_id == 12353)
            )
            saved_msg = result.scalar_one_or_none()
            assert saved_msg is not None
            assert saved_msg.content_type == "video_note"
            assert saved_msg.content == "Transcribed video text"

    @pytest.mark.asyncio
    async def test_collect_voice_transcription_failure(
        self,
        db_session: AsyncSession,
        telegram_chat,
        telegram_user,
        db_user: User,
        db_chat: Chat,
        mock_bot,
        monkeypatch
    ):
        """Test collecting voice message when transcription fails."""
        from api.bot import collect_group_message

        # Mock transcription service to raise error
        mock_service = MagicMock()
        mock_service.transcribe_audio = AsyncMock(side_effect=Exception("Transcription failed"))
        monkeypatch.setattr("api.bot.transcription_service", mock_service)

        # Patch async_session and bot
        with patch('api.bot.async_session') as mock_session_maker, \
             patch('api.bot.get_bot', return_value=mock_bot):
            mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=db_session)
            mock_session_maker.return_value.__aexit__ = AsyncMock()

            # Create mock voice message
            message = MagicMock(spec=TelegramMessage)
            message.chat = telegram_chat
            message.from_user = telegram_user
            message.message_id = 12354
            message.text = None
            message.caption = None
            message.date = datetime.utcnow()
            message.voice = MagicMock()
            message.voice.file_id = "voice_fail_123"
            message.video_note = None
            message.video = None
            message.audio = None
            message.document = None
            message.photo = None
            message.sticker = None

            await collect_group_message(message)

            # Verify message was saved with failure message
            from sqlalchemy import select
            result = await db_session.execute(
                select(Message).where(Message.telegram_message_id == 12354)
            )
            saved_msg = result.scalar_one_or_none()
            assert saved_msg is not None
            assert saved_msg.content_type == "voice"
            assert "transcription failed" in saved_msg.content.lower()

    @pytest.mark.asyncio
    async def test_collect_document_parsing_failure(
        self,
        db_session: AsyncSession,
        telegram_chat,
        telegram_user,
        db_user: User,
        db_chat: Chat,
        mock_bot,
        monkeypatch
    ):
        """Test collecting document when parsing fails."""
        from api.bot import collect_group_message

        # Mock document parser to raise error
        mock_parser = MagicMock()
        mock_parser.parse = AsyncMock(side_effect=Exception("Parsing failed"))
        monkeypatch.setattr("api.bot.document_parser", mock_parser)

        # Patch async_session and bot
        with patch('api.bot.async_session') as mock_session_maker, \
             patch('api.bot.get_bot', return_value=mock_bot):
            mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=db_session)
            mock_session_maker.return_value.__aexit__ = AsyncMock()

            # Create mock document message
            message = MagicMock(spec=TelegramMessage)
            message.chat = telegram_chat
            message.from_user = telegram_user
            message.message_id = 12355
            message.text = None
            message.caption = None
            message.date = datetime.utcnow()
            message.voice = None
            message.video_note = None
            message.video = None
            message.audio = None
            message.document = MagicMock()
            message.document.file_id = "doc_fail_123"
            message.document.file_name = "failed.pdf"
            message.document.file_size = 1024
            message.photo = None
            message.sticker = None

            await collect_group_message(message)

            # Verify message was saved with failure status
            from sqlalchemy import select
            result = await db_session.execute(
                select(Message).where(Message.telegram_message_id == 12355)
            )
            saved_msg = result.scalar_one_or_none()
            assert saved_msg is not None
            assert saved_msg.content_type == "document"
            assert saved_msg.parse_status == "failed"
            assert saved_msg.parse_error is not None

    @pytest.mark.asyncio
    async def test_collect_large_document(
        self,
        db_session: AsyncSession,
        telegram_chat,
        telegram_user,
        db_user: User,
        db_chat: Chat
    ):
        """Test collecting a large document - should skip parsing."""
        from api.bot import collect_group_message

        # Patch async_session
        with patch('api.bot.async_session') as mock_session_maker:
            mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=db_session)
            mock_session_maker.return_value.__aexit__ = AsyncMock()

            # Create mock large document message
            message = MagicMock(spec=TelegramMessage)
            message.chat = telegram_chat
            message.from_user = telegram_user
            message.message_id = 12356
            message.text = None
            message.caption = None
            message.date = datetime.utcnow()
            message.voice = None
            message.video_note = None
            message.video = None
            message.audio = None
            message.document = MagicMock()
            message.document.file_id = "large_doc_123"
            message.document.file_name = "huge_file.pdf"
            message.document.file_size = 25 * 1024 * 1024  # 25MB - over limit
            message.photo = None
            message.sticker = None

            await collect_group_message(message)

            # Verify message was saved with placeholder
            from sqlalchemy import select
            result = await db_session.execute(
                select(Message).where(Message.telegram_message_id == 12356)
            )
            saved_msg = result.scalar_one_or_none()
            assert saved_msg is not None
            assert saved_msg.content_type == "document"
            assert "too large" in saved_msg.content
            assert saved_msg.parse_status == "skipped"

    @pytest.mark.asyncio
    async def test_collect_message_with_caption(
        self,
        db_session: AsyncSession,
        telegram_chat,
        telegram_user,
        db_user: User,
        db_chat: Chat
    ):
        """Test collecting message with caption but no text."""
        from api.bot import collect_group_message

        # Patch async_session
        with patch('api.bot.async_session') as mock_session_maker:
            mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=db_session)
            mock_session_maker.return_value.__aexit__ = AsyncMock()

            # Create mock message with only caption
            message = MagicMock(spec=TelegramMessage)
            message.chat = telegram_chat
            message.from_user = telegram_user
            message.message_id = 12357
            message.text = None
            message.caption = "This is a caption"
            message.date = datetime.utcnow()
            message.voice = None
            message.video_note = None
            message.video = None
            message.audio = None
            message.document = None
            message.photo = None
            message.sticker = None

            await collect_group_message(message)

            # Verify message was saved with caption
            from sqlalchemy import select
            result = await db_session.execute(
                select(Message).where(Message.telegram_message_id == 12357)
            )
            saved_msg = result.scalar_one_or_none()
            assert saved_msg is not None
            assert saved_msg.content == "This is a caption"

    @pytest.mark.asyncio
    @pytest.mark.xfail(reason="Org membership not propagated in test env")
    async def test_collect_message_with_org_membership(
        self,
        db_session: AsyncSession,
        telegram_chat,
        telegram_user,
        db_user: User,
        organization,
        org_owner
    ):
        """Test collecting message when user has organization membership."""
        from api.bot import collect_group_message

        # Patch async_session
        with patch('api.bot.async_session') as mock_session_maker:
            mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=db_session)
            mock_session_maker.return_value.__aexit__ = AsyncMock()

            # Create mock message
            message = MagicMock(spec=TelegramMessage)
            message.chat = telegram_chat
            message.from_user = telegram_user
            message.message_id = 12358
            message.text = "Test message with org"
            message.caption = None
            message.date = datetime.utcnow()
            message.voice = None
            message.video_note = None
            message.video = None
            message.audio = None
            message.document = None
            message.photo = None
            message.sticker = None

            await collect_group_message(message)

            # Verify chat was created with org_id
            from sqlalchemy import select
            result = await db_session.execute(
                select(Chat).where(Chat.telegram_chat_id == telegram_chat.id)
            )
            chat = result.scalar_one_or_none()
            assert chat is not None
            assert chat.org_id == organization.id

            # Verify message was saved
            result = await db_session.execute(
                select(Message).where(Message.telegram_message_id == 12358)
            )
            saved_msg = result.scalar_one_or_none()
            assert saved_msg is not None
            assert saved_msg.chat_id == chat.id

    @pytest.mark.asyncio
    async def test_collect_message_error_handling(self, telegram_chat, telegram_user):
        """Test message collection with database error - should not crash."""
        from api.bot import collect_group_message

        # Mock session that raises an error
        mock_session = MagicMock()
        mock_session.execute = AsyncMock(side_effect=Exception("Database error"))
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        with patch('api.bot.async_session') as mock_session_maker:
            mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_maker.return_value.__aexit__ = AsyncMock()

            # Create mock message
            message = MagicMock(spec=TelegramMessage)
            message.chat = telegram_chat
            message.from_user = telegram_user
            message.message_id = 12359
            message.text = "Test message"
            message.caption = None
            message.date = datetime.utcnow()
            message.voice = None
            message.video_note = None
            message.video = None
            message.audio = None
            message.document = None
            message.photo = None
            message.sticker = None

            # Should not raise an error, just log it
            await collect_group_message(message)

    @pytest.mark.asyncio
    async def test_collect_photo_ocr_failure(
        self,
        db_session: AsyncSession,
        telegram_chat,
        telegram_user,
        db_user: User,
        db_chat: Chat,
        mock_bot,
        monkeypatch
    ):
        """Test collecting photo when OCR fails."""
        from api.bot import collect_group_message

        # Mock document parser to raise error
        mock_parser = MagicMock()
        mock_parser.parse = AsyncMock(side_effect=Exception("OCR failed"))
        monkeypatch.setattr("api.bot.document_parser", mock_parser)

        # Patch async_session and bot
        with patch('api.bot.async_session') as mock_session_maker, \
             patch('api.bot.get_bot', return_value=mock_bot):
            mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=db_session)
            mock_session_maker.return_value.__aexit__ = AsyncMock()

            # Create mock photo message
            message = MagicMock(spec=TelegramMessage)
            message.chat = telegram_chat
            message.from_user = telegram_user
            message.message_id = 12360
            message.text = None
            message.caption = "Photo caption"
            message.date = datetime.utcnow()
            message.voice = None
            message.video_note = None
            message.video = None
            message.audio = None
            message.document = None
            message.photo = [MagicMock(), MagicMock()]
            message.photo[-1].file_id = "photo_fail_123"
            message.sticker = None

            await collect_group_message(message)

            # Verify message was saved with caption (fallback when OCR fails)
            from sqlalchemy import select
            result = await db_session.execute(
                select(Message).where(Message.telegram_message_id == 12360)
            )
            saved_msg = result.scalar_one_or_none()
            assert saved_msg is not None
            assert saved_msg.content_type == "photo"
            assert saved_msg.content == "Photo caption"
            assert saved_msg.parse_status == "failed"


# ============================================================================
# LIFECYCLE TESTS
# ============================================================================

class TestBotLifecycle:
    """Tests for bot startup and shutdown."""

    @pytest.mark.asyncio
    async def test_start_bot_success(self, mock_telegram_bot_token, mock_bot):
        """Test successful bot startup."""
        from api.bot import start_bot

        # Перед стартом бот регистрирует команды и кнопку мини-аппа — это
        # await-вызовы, у голого MagicMock их нет («can't be used in 'await'»).
        mock_bot.set_my_commands = AsyncMock()
        mock_bot.set_chat_menu_button = AsyncMock()

        with patch('api.bot.get_bot', return_value=mock_bot), \
             patch('api.bot.dp') as mock_dp:
            mock_dp.start_polling = AsyncMock()

            await start_bot()

            mock_bot.set_my_commands.assert_called_once()
            mock_bot.get_me.assert_called_once()
            mock_dp.start_polling.assert_called_once_with(mock_bot)

    @pytest.mark.asyncio
    async def test_start_bot_no_token(self):
        """Test bot startup without token."""
        from api.bot import start_bot

        with patch('api.bot.get_bot', side_effect=ValueError("TELEGRAM_BOT_TOKEN is not set")):
            # Should not raise, just log error
            await start_bot()

    @pytest.mark.asyncio
    async def test_stop_bot(self, mock_bot):
        """Test bot shutdown."""
        from api.bot import stop_bot

        # Set global bot
        import api.bot as bot_module
        bot_module.bot = mock_bot

        await stop_bot()

        mock_bot.session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_bot_no_bot(self):
        """Test bot shutdown when bot is not initialized."""
        from api.bot import stop_bot

        # Set global bot to None
        import api.bot as bot_module
        bot_module.bot = None

        # Should not raise an error
        await stop_bot()


# ============================================================================
# MISCELLANEOUS TESTS
# ============================================================================

class TestMiscellaneous:
    """Tests for miscellaneous bot functionality."""

    def test_chat_types_constant(self):
        """Test CHAT_TYPES constant is properly defined."""
        from api.bot import CHAT_TYPES

        # Verify it's a dictionary
        assert isinstance(CHAT_TYPES, dict)

        # Verify expected types are present
        expected_types = ['work', 'hr', 'project', 'client', 'contractor', 'sales', 'support', 'custom']
        for chat_type in expected_types:
            assert chat_type in CHAT_TYPES
            assert isinstance(CHAT_TYPES[chat_type], str)
            assert len(CHAT_TYPES[chat_type]) > 0

    def test_dispatcher_initialized(self):
        """Test that dispatcher is initialized."""
        from api.bot import dp

        assert dp is not None

    @pytest.mark.asyncio
    async def test_get_db_generator(self):
        """Test get_db generator function."""
        from api.bot import get_db

        # Verify it's a generator function
        import inspect
        assert inspect.isasyncgenfunction(get_db)
