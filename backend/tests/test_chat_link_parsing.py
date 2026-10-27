"""
Tests for parsing external links in chat messages.
Tests the _parse_link_to_chat_message function that saves document content to chat.
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime

from api.services.external_links import LinkType
from api.services.documents import DocumentParseResult


# ============================================================================
# TEST: process_external_links_in_message
# ============================================================================

class TestProcessExternalLinksInMessage:
    """Tests for process_external_links_in_message function."""

    @pytest.mark.asyncio
    async def test_no_urls_in_message(self):
        """Should not process when no URLs in message."""
        from api.bot import process_external_links_in_message

        # No URLs in text - should return early
        with patch('api.bot._parse_link_to_chat_message') as mock_parse:
            await process_external_links_in_message("Hello, this is a test", 1, 1, 1)
            mock_parse.assert_not_called()

    @pytest.mark.asyncio
    async def test_regular_url_not_processed(self):
        """Should not process regular URLs."""
        from api.bot import process_external_links_in_message

        with patch('api.bot._parse_link_to_chat_message') as mock_parse:
            await process_external_links_in_message("Check this: https://example.com", 1, 1, 1)
            mock_parse.assert_not_called()

    @pytest.mark.asyncio
    async def test_google_doc_url_detected(self):
        """Should detect and process Google Doc URLs."""
        from api.bot import process_external_links_in_message

        with patch('api.bot._parse_link_to_chat_message', new_callable=AsyncMock) as mock_parse:
            with patch('asyncio.create_task') as mock_task:
                await process_external_links_in_message(
                    "Check this doc: https://docs.google.com/document/d/1ABC123xyz/edit",
                    org_id=1,
                    owner_id=1,
                    chat_id=123
                )
                # Should have created a task to parse the link
                mock_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_google_sheet_url_detected(self):
        """Should detect and process Google Sheet URLs."""
        from api.bot import process_external_links_in_message

        with patch('api.bot._parse_link_to_chat_message', new_callable=AsyncMock) as mock_parse:
            with patch('asyncio.create_task') as mock_task:
                await process_external_links_in_message(
                    "Check this sheet: https://docs.google.com/spreadsheets/d/1ABC123xyz/edit",
                    org_id=1,
                    owner_id=1,
                    chat_id=123
                )
                mock_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_fireflies_url_not_processed_to_chat(self):
        """Fireflies links should NOT be processed to chat (they are call recordings)."""
        from api.bot import process_external_links_in_message

        with patch('api.bot._parse_link_to_chat_message', new_callable=AsyncMock) as mock_parse:
            with patch('asyncio.create_task') as mock_task:
                await process_external_links_in_message(
                    "Check this call: https://app.fireflies.ai/view/ABC123",
                    org_id=1,
                    owner_id=1,
                    chat_id=123
                )
                # Fireflies should NOT create a chat message task
                mock_task.assert_not_called()


# ============================================================================
# TEST: _parse_link_to_chat_message
# ============================================================================

class TestParseLinkToChatMessage:
    """Tests for _parse_link_to_chat_message function."""

    @pytest.mark.asyncio
    async def test_parse_google_doc_success(self):
        """Should parse Google Doc and save as message."""
        from api.bot import _parse_link_to_chat_message

        mock_result = Mock()
        mock_result.content = "This is the document content"
        mock_result.metadata = {"title": "Test Document"}
        mock_result.error = None

        mock_message = Mock()
        mock_session = AsyncMock()
        mock_session.add = Mock()
        mock_session.commit = AsyncMock()

        with patch('api.services.google_docs.google_docs_service') as mock_docs_service:
            mock_docs_service.parse_from_url = AsyncMock(return_value=mock_result)

            with patch('api.bot.async_session') as mock_async_session:
                mock_async_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
                mock_async_session.return_value.__aexit__ = AsyncMock()

                await _parse_link_to_chat_message(
                    "https://docs.google.com/document/d/1ABC/edit",
                    LinkType.GOOGLE_DOC,
                    chat_id=123
                )

                # Should have added a message
                mock_session.add.assert_called_once()
                mock_session.commit.assert_called_once()

                # Check the message content
                saved_message = mock_session.add.call_args[0][0]
                assert "Test Document" in saved_message.content
                assert saved_message.content_type == "parsed_link"
                assert saved_message.chat_id == 123

    @pytest.mark.asyncio
    async def test_parse_google_doc_failure(self):
        """Should handle Google Doc parse failure gracefully."""
        from api.bot import _parse_link_to_chat_message

        mock_result = Mock()
        mock_result.content = None
        mock_result.error = "Document not accessible"

        mock_session = AsyncMock()
        mock_session.add = Mock()
        mock_session.commit = AsyncMock()

        with patch('api.services.google_docs.google_docs_service') as mock_docs_service:
            mock_docs_service.parse_from_url = AsyncMock(return_value=mock_result)

            with patch('api.bot.async_session') as mock_async_session:
                mock_async_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
                mock_async_session.return_value.__aexit__ = AsyncMock()

                await _parse_link_to_chat_message(
                    "https://docs.google.com/document/d/1ABC/edit",
                    LinkType.GOOGLE_DOC,
                    chat_id=123
                )

                # Should NOT add a message when parsing failed
                mock_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_parse_google_sheet_success(self):
        """Should parse Google Sheet and save as message."""
        from api.bot import _parse_link_to_chat_message

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value="col1,col2\nval1,val2")

        mock_session_http = MagicMock()
        mock_session_http.__aenter__ = AsyncMock(return_value=mock_session_http)
        mock_session_http.__aexit__ = AsyncMock()
        mock_session_http.get = MagicMock(return_value=MagicMock(
            __aenter__=AsyncMock(return_value=mock_response),
            __aexit__=AsyncMock()
        ))

        mock_db_session = AsyncMock()
        mock_db_session.add = Mock()
        mock_db_session.commit = AsyncMock()

        with patch('aiohttp.ClientSession', return_value=mock_session_http):
            with patch('api.bot.async_session') as mock_async_session:
                mock_async_session.return_value.__aenter__ = AsyncMock(return_value=mock_db_session)
                mock_async_session.return_value.__aexit__ = AsyncMock()

                await _parse_link_to_chat_message(
                    "https://docs.google.com/spreadsheets/d/1ABC123/edit",
                    LinkType.GOOGLE_SHEET,
                    chat_id=123
                )

                mock_db_session.add.assert_called_once()
                saved_message = mock_db_session.add.call_args[0][0]
                assert saved_message.content_type == "parsed_link"
                assert "col1,col2" in saved_message.content

    @pytest.mark.asyncio
    async def test_parse_google_form(self):
        """Should save Google Form link as partial content."""
        from api.bot import _parse_link_to_chat_message

        mock_db_session = AsyncMock()
        mock_db_session.add = Mock()
        mock_db_session.commit = AsyncMock()

        with patch('api.bot.async_session') as mock_async_session:
            mock_async_session.return_value.__aenter__ = AsyncMock(return_value=mock_db_session)
            mock_async_session.return_value.__aexit__ = AsyncMock()

            await _parse_link_to_chat_message(
                "https://docs.google.com/forms/d/e/1ABC123/viewform",
                LinkType.GOOGLE_FORM,
                chat_id=123
            )

            mock_db_session.add.assert_called_once()
            saved_message = mock_db_session.add.call_args[0][0]
            assert saved_message.content_type == "parsed_link"
            assert "Google Form" in saved_message.content

    @pytest.mark.asyncio
    async def test_long_content_truncated(self):
        """Should truncate very long content."""
        from api.bot import _parse_link_to_chat_message

        # Create content longer than 10000 chars
        long_content = "A" * 15000

        mock_result = Mock()
        mock_result.content = long_content
        mock_result.metadata = {"title": "Long Doc"}
        mock_result.error = None

        mock_db_session = AsyncMock()
        mock_db_session.add = Mock()
        mock_db_session.commit = AsyncMock()

        with patch('api.services.google_docs.google_docs_service') as mock_docs_service:
            mock_docs_service.parse_from_url = AsyncMock(return_value=mock_result)

            with patch('api.bot.async_session') as mock_async_session:
                mock_async_session.return_value.__aenter__ = AsyncMock(return_value=mock_db_session)
                mock_async_session.return_value.__aexit__ = AsyncMock()

                await _parse_link_to_chat_message(
                    "https://docs.google.com/document/d/1ABC/edit",
                    LinkType.GOOGLE_DOC,
                    chat_id=123
                )

                saved_message = mock_db_session.add.call_args[0][0]
                # Content should be truncated
                assert len(saved_message.content) < 15000
                assert "Обрезано" in saved_message.content
                # Full content should be in metadata
                assert saved_message.document_metadata.get("truncated") == True

    @pytest.mark.asyncio
    async def test_message_metadata_includes_source_url(self):
        """Should include source URL in message metadata."""
        from api.bot import _parse_link_to_chat_message

        mock_result = Mock()
        mock_result.content = "Test content"
        mock_result.metadata = {"title": "Test"}
        mock_result.error = None

        mock_db_session = AsyncMock()
        mock_db_session.add = Mock()
        mock_db_session.commit = AsyncMock()

        test_url = "https://docs.google.com/document/d/1ABC/edit"

        with patch('api.services.google_docs.google_docs_service') as mock_docs_service:
            mock_docs_service.parse_from_url = AsyncMock(return_value=mock_result)

            with patch('api.bot.async_session') as mock_async_session:
                mock_async_session.return_value.__aenter__ = AsyncMock(return_value=mock_db_session)
                mock_async_session.return_value.__aexit__ = AsyncMock()

                await _parse_link_to_chat_message(test_url, LinkType.GOOGLE_DOC, chat_id=123)

                saved_message = mock_db_session.add.call_args[0][0]
                assert saved_message.document_metadata.get("source_url") == test_url
                assert saved_message.document_metadata.get("link_type") == LinkType.GOOGLE_DOC


# ============================================================================
# TEST: extract_urls_from_text (URL extraction with punctuation cleanup)
# ============================================================================

class TestExtractUrlsFromText:
    """Tests for extract_urls_from_text function - handles mixed text+link messages."""

    def test_url_only(self):
        """Should extract URL when it's the only content."""
        from api.bot import extract_urls_from_text
        urls = extract_urls_from_text("https://docs.google.com/document/d/1ABC/edit")
        assert urls == ["https://docs.google.com/document/d/1ABC/edit"]

    def test_url_at_end_with_period(self):
        """Should strip trailing period from URL."""
        from api.bot import extract_urls_from_text
        urls = extract_urls_from_text("Посмотри: https://docs.google.com/document/d/1ABC/edit.")
        assert urls == ["https://docs.google.com/document/d/1ABC/edit"]

    def test_url_at_end_with_comma(self):
        """Should strip trailing comma from URL."""
        from api.bot import extract_urls_from_text
        urls = extract_urls_from_text("Ссылка https://docs.google.com/document/d/1ABC/edit, посмотри")
        assert urls == ["https://docs.google.com/document/d/1ABC/edit"]

    def test_url_in_parentheses(self):
        """Should strip trailing parenthesis when URL is wrapped."""
        from api.bot import extract_urls_from_text
        urls = extract_urls_from_text("Тут (https://docs.google.com/document/d/1ABC/edit) документ")
        assert urls == ["https://docs.google.com/document/d/1ABC/edit"]

    def test_url_with_exclamation(self):
        """Should strip trailing exclamation mark from URL."""
        from api.bot import extract_urls_from_text
        urls = extract_urls_from_text("Файл: https://example.com/file.mp3!")
        assert urls == ["https://example.com/file.mp3"]

    def test_wikipedia_url_with_parentheses(self):
        """Should keep parentheses that are part of URL (Wikipedia style)."""
        from api.bot import extract_urls_from_text
        urls = extract_urls_from_text("https://en.wikipedia.org/wiki/URL_(computing)")
        assert urls == ["https://en.wikipedia.org/wiki/URL_(computing)"]

    def test_wikipedia_url_with_trailing_period(self):
        """Should strip trailing period but keep internal parentheses."""
        from api.bot import extract_urls_from_text
        urls = extract_urls_from_text("Посмотри: https://en.wikipedia.org/wiki/URL_(computing).")
        assert urls == ["https://en.wikipedia.org/wiki/URL_(computing)"]

    def test_google_drive_link_in_message(self):
        """Should correctly extract Google Drive links from mixed text."""
        from api.bot import extract_urls_from_text
        text = "Привет! Вот резюме https://drive.google.com/file/d/1BCD_test/view?usp=drive_link спасибо"
        urls = extract_urls_from_text(text)
        assert urls == ["https://drive.google.com/file/d/1BCD_test/view?usp=drive_link"]

    def test_fireflies_link(self):
        """Should correctly extract Fireflies links."""
        from api.bot import extract_urls_from_text
        urls = extract_urls_from_text("Вот запись: https://app.fireflies.ai/view/ABC123::def456")
        assert urls == ["https://app.fireflies.ai/view/ABC123::def456"]

    def test_multiple_urls(self):
        """Should extract multiple URLs from text."""
        from api.bot import extract_urls_from_text
        text = "Первая https://example.com/1, вторая https://example.com/2."
        urls = extract_urls_from_text(text)
        assert urls == ["https://example.com/1", "https://example.com/2"]

    def test_no_urls(self):
        """Should return empty list when no URLs."""
        from api.bot import extract_urls_from_text
        urls = extract_urls_from_text("Привет, как дела?")
        assert urls == []

    def test_multiple_trailing_punctuation(self):
        """Should strip multiple trailing punctuation marks."""
        from api.bot import extract_urls_from_text
        urls = extract_urls_from_text("Check this out: https://example.com/path?q=1).")
        assert urls == ["https://example.com/path?q=1"]
