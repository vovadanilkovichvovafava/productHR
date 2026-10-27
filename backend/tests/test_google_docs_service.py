"""
Comprehensive unit tests for Google Docs parsing service.
Tests URL parsing, text extraction, HTML conversion, and error scenarios.
"""
import pytest
from unittest.mock import Mock, MagicMock, AsyncMock, patch
import aiohttp

from api.services.google_docs import GoogleDocsService, google_docs_service
from api.services.documents import DocumentParseResult


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def service():
    """Create a GoogleDocsService instance."""
    return GoogleDocsService()


@pytest.fixture
def sample_google_doc_urls():
    """Sample Google Docs URLs for testing."""
    return {
        "edit": "https://docs.google.com/document/d/1ABC123xyz-_def456/edit",
        "edit_with_tab": "https://docs.google.com/document/d/1ABC123xyz-_def456/edit?tab=t.0",
        "view": "https://docs.google.com/document/d/1ABC123xyz-_def456/view",
        "pub": "https://docs.google.com/document/d/1ABC123xyz-_def456/pub",
        "invalid": "https://google.com/not-a-doc",
        "drive": "https://drive.google.com/file/d/1ABC123/view"
    }


# ============================================================================
# TEST URL PARSING
# ============================================================================

class TestURLParsing:
    """Tests for URL parsing and document ID extraction."""

    def test_extract_doc_id_from_edit_url(self, service, sample_google_doc_urls):
        """Test extracting doc ID from edit URL."""
        doc_id = service.extract_doc_id(sample_google_doc_urls["edit"])
        assert doc_id == "1ABC123xyz-_def456"

    def test_extract_doc_id_from_edit_with_tab(self, service, sample_google_doc_urls):
        """Test extracting doc ID from edit URL with tab parameter."""
        doc_id = service.extract_doc_id(sample_google_doc_urls["edit_with_tab"])
        assert doc_id == "1ABC123xyz-_def456"

    def test_extract_doc_id_from_view_url(self, service, sample_google_doc_urls):
        """Test extracting doc ID from view URL."""
        doc_id = service.extract_doc_id(sample_google_doc_urls["view"])
        assert doc_id == "1ABC123xyz-_def456"

    def test_extract_doc_id_from_pub_url(self, service, sample_google_doc_urls):
        """Test extracting doc ID from published URL."""
        doc_id = service.extract_doc_id(sample_google_doc_urls["pub"])
        assert doc_id == "1ABC123xyz-_def456"

    def test_extract_doc_id_invalid_url(self, service, sample_google_doc_urls):
        """Test that invalid URLs return None."""
        doc_id = service.extract_doc_id(sample_google_doc_urls["invalid"])
        assert doc_id is None

    def test_extract_doc_id_drive_url(self, service, sample_google_doc_urls):
        """Test that Drive URLs return None (not Docs)."""
        doc_id = service.extract_doc_id(sample_google_doc_urls["drive"])
        assert doc_id is None

    def test_extract_doc_id_empty_string(self, service):
        """Test empty string returns None."""
        doc_id = service.extract_doc_id("")
        assert doc_id is None

    def test_is_google_docs_url_valid(self, service, sample_google_doc_urls):
        """Test detection of valid Google Docs URL."""
        assert service.is_google_docs_url(sample_google_doc_urls["edit"]) is True
        assert service.is_google_docs_url(sample_google_doc_urls["view"]) is True

    def test_is_google_docs_url_invalid(self, service, sample_google_doc_urls):
        """Test detection of invalid URLs."""
        assert service.is_google_docs_url(sample_google_doc_urls["invalid"]) is False
        assert service.is_google_docs_url(sample_google_doc_urls["drive"]) is False


# ============================================================================
# TEST TEXT EXPORT
# ============================================================================

class TestTextExport:
    """Tests for plain text export functionality."""

    @pytest.mark.asyncio
    async def test_export_as_text_success(self, service):
        """Test successful text export."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.headers = {'Content-Type': 'text/plain; charset=utf-8'}
        mock_response.text = AsyncMock(return_value="This is the document content.\nWith multiple lines.")
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)

        with patch.object(service, '_get_session', return_value=mock_session):
            result = await service._export_as_text("test_doc_id")

        assert result.status == "parsed"
        assert "document content" in result.content
        assert result.metadata["doc_id"] == "test_doc_id"
        assert result.metadata["format"] == "text"

    @pytest.mark.asyncio
    async def test_export_as_text_404(self, service):
        """Test text export with 404 response."""
        mock_response = AsyncMock()
        mock_response.status = 404
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)

        with patch.object(service, '_get_session', return_value=mock_session):
            result = await service._export_as_text("nonexistent_doc")

        assert result.status == "failed"
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_export_as_text_requires_auth(self, service):
        """Test text export when document requires authentication."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.headers = {'Content-Type': 'text/html'}  # HTML means login page
        mock_response.text = AsyncMock(return_value="<html>Login required</html>")
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)

        with patch.object(service, '_get_session', return_value=mock_session):
            result = await service._export_as_text("private_doc")

        assert result.status == "failed"
        assert "authentication" in result.error.lower()

    @pytest.mark.asyncio
    async def test_export_as_text_empty_content(self, service):
        """Test text export with empty document."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.headers = {'Content-Type': 'text/plain'}
        mock_response.text = AsyncMock(return_value="   \n\n   ")
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)

        with patch.object(service, '_get_session', return_value=mock_session):
            result = await service._export_as_text("empty_doc")

        # Empty content should fail or return partial status
        assert result.status == "failed"

    @pytest.mark.asyncio
    async def test_export_as_text_network_error(self, service):
        """Test text export with network error."""
        mock_session = AsyncMock()
        mock_session.get = MagicMock(side_effect=aiohttp.ClientError("Connection failed"))

        with patch.object(service, '_get_session', return_value=mock_session):
            result = await service._export_as_text("any_doc")

        assert result.status == "failed"
        assert "network" in result.error.lower()


# ============================================================================
# TEST HTML EXPORT
# ============================================================================

class TestHTMLExport:
    """Tests for HTML export and conversion functionality."""

    @pytest.mark.asyncio
    async def test_export_as_html_success(self, service):
        """Test successful HTML export and conversion."""
        html_content = """
        <html>
        <head><title>Test Doc</title></head>
        <body>
            <p>Paragraph 1</p>
            <p>Paragraph 2</p>
        </body>
        </html>
        """

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value=html_content)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)

        with patch.object(service, '_get_session', return_value=mock_session):
            result = await service._export_as_html("test_doc_id")

        assert result.status == "parsed"
        assert "Paragraph 1" in result.content
        assert "Paragraph 2" in result.content
        assert result.metadata["format"] == "html"

    @pytest.mark.asyncio
    async def test_export_as_html_removes_scripts(self, service):
        """Test that scripts are removed from HTML."""
        html_content = """
        <html>
        <head><script>alert('xss')</script></head>
        <body>
            <p>Content</p>
            <script>console.log('test')</script>
        </body>
        </html>
        """

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value=html_content)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)

        with patch.object(service, '_get_session', return_value=mock_session):
            result = await service._export_as_html("test_doc_id")

        assert result.status == "parsed"
        assert "alert" not in result.content
        assert "console.log" not in result.content
        assert "Content" in result.content

    @pytest.mark.asyncio
    async def test_export_as_html_removes_styles(self, service):
        """Test that styles are removed from HTML."""
        html_content = """
        <html>
        <head><style>.foo { color: red; }</style></head>
        <body><p>Content</p></body>
        </html>
        """

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value=html_content)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)

        with patch.object(service, '_get_session', return_value=mock_session):
            result = await service._export_as_html("test_doc_id")

        assert result.status == "parsed"
        assert "color: red" not in result.content

    @pytest.mark.asyncio
    async def test_export_as_html_login_page(self, service):
        """Test detection of login page in HTML response."""
        html_content = """
        <html>
        <body>
            <a href="https://accounts.google.com/signin">Sign in</a>
        </body>
        </html>
        """

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value=html_content)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)

        with patch.object(service, '_get_session', return_value=mock_session):
            result = await service._export_as_html("private_doc")

        # Should detect login redirect and fail
        assert result.status == "failed"


# ============================================================================
# TEST MAIN PARSE FUNCTION
# ============================================================================

class TestParseFromURL:
    """Tests for main parse_from_url function."""

    @pytest.mark.asyncio
    async def test_parse_invalid_url(self, service):
        """Test parsing with invalid Google Docs URL."""
        result = await service.parse_from_url("https://example.com/not-a-doc")

        assert result.status == "failed"
        assert "Invalid Google Docs URL" in result.error

    @pytest.mark.asyncio
    async def test_parse_tries_text_first(self, service):
        """Test that text export is tried before HTML."""
        # Text export succeeds
        text_result = DocumentParseResult(
            content="Document content",
            status="parsed",
            metadata={"format": "text"}
        )

        with patch.object(service, '_export_as_text', return_value=text_result) as mock_text, \
             patch.object(service, '_export_as_html') as mock_html:

            result = await service.parse_from_url(
                "https://docs.google.com/document/d/test123/edit"
            )

        assert result.status == "parsed"
        mock_text.assert_called_once_with("test123")
        mock_html.assert_not_called()

    @pytest.mark.asyncio
    async def test_parse_falls_back_to_html(self, service):
        """Test fallback to HTML when text export fails."""
        # Text export fails
        text_result = DocumentParseResult(status="failed", error="No text")

        # HTML export succeeds
        html_result = DocumentParseResult(
            content="HTML content",
            status="parsed",
            metadata={"format": "html"}
        )

        with patch.object(service, '_export_as_text', return_value=text_result), \
             patch.object(service, '_export_as_html', return_value=html_result):

            result = await service.parse_from_url(
                "https://docs.google.com/document/d/test123/edit"
            )

        assert result.status == "parsed"
        assert result.content == "HTML content"

    @pytest.mark.asyncio
    async def test_parse_both_fail(self, service):
        """Test when both text and HTML export fail."""
        text_result = DocumentParseResult(status="failed", error="No text")
        html_result = DocumentParseResult(status="failed", error="No HTML")

        with patch.object(service, '_export_as_text', return_value=text_result), \
             patch.object(service, '_export_as_html', return_value=html_result):

            result = await service.parse_from_url(
                "https://docs.google.com/document/d/test123/edit"
            )

        assert result.status == "failed"
        assert "Could not access" in result.error
        assert result.metadata["doc_id"] == "test123"


# ============================================================================
# TEST SESSION MANAGEMENT
# ============================================================================

class TestSessionManagement:
    """Tests for aiohttp session management."""

    @pytest.mark.asyncio
    async def test_session_created_on_first_use(self, service):
        """Test that session is created on first request."""
        assert service.session is None

        # Mock the session creation
        with patch('aiohttp.ClientSession') as mock_session_class:
            mock_session = MagicMock()
            mock_session.closed = False
            mock_session_class.return_value = mock_session

            session = await service._get_session()

            assert session is not None
            mock_session_class.assert_called_once()

    @pytest.mark.asyncio
    async def test_session_reused(self, service):
        """Test that existing session is reused."""
        mock_session = MagicMock()
        mock_session.closed = False
        service.session = mock_session

        session = await service._get_session()

        assert session is mock_session

    @pytest.mark.asyncio
    async def test_session_recreated_if_closed(self, service):
        """Test that closed session is replaced."""
        old_session = MagicMock()
        old_session.closed = True
        service.session = old_session

        with patch('aiohttp.ClientSession') as mock_session_class:
            new_session = MagicMock()
            new_session.closed = False
            mock_session_class.return_value = new_session

            session = await service._get_session()

            assert session is new_session

    @pytest.mark.asyncio
    async def test_close_session(self, service):
        """Test session cleanup."""
        mock_session = AsyncMock()
        mock_session.closed = False
        service.session = mock_session

        await service.close()

        mock_session.close.assert_called_once()


# ============================================================================
# TEST SINGLETON INSTANCE
# ============================================================================

class TestSingleton:
    """Tests for singleton instance."""

    def test_singleton_exists(self):
        """Test that singleton instance is created."""
        assert google_docs_service is not None
        assert isinstance(google_docs_service, GoogleDocsService)


# ============================================================================
# TEST EDGE CASES
# ============================================================================

class TestEdgeCases:
    """Tests for edge cases and special scenarios."""

    @pytest.mark.asyncio
    async def test_unicode_content(self, service):
        """Test handling of Unicode content."""
        unicode_content = "Привет мир! 你好世界! 🎉"

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.headers = {'Content-Type': 'text/plain; charset=utf-8'}
        mock_response.text = AsyncMock(return_value=unicode_content)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)

        with patch.object(service, '_get_session', return_value=mock_session):
            result = await service._export_as_text("unicode_doc")

        assert result.status == "parsed"
        assert "Привет" in result.content
        assert "你好" in result.content

    @pytest.mark.asyncio
    async def test_very_long_content(self, service):
        """Test handling of very long document."""
        long_content = "A" * 100000  # 100KB of text

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.headers = {'Content-Type': 'text/plain'}
        mock_response.text = AsyncMock(return_value=long_content)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)

        with patch.object(service, '_get_session', return_value=mock_session):
            result = await service._export_as_text("long_doc")

        assert result.status == "parsed"
        assert result.metadata["char_count"] == 100000

    def test_doc_id_with_special_chars(self, service):
        """Test extraction of doc ID with special characters."""
        url = "https://docs.google.com/document/d/1A-B_C2def-xyz_123/edit"
        doc_id = service.extract_doc_id(url)
        assert doc_id == "1A-B_C2def-xyz_123"

    @pytest.mark.asyncio
    async def test_whitespace_only_content(self, service):
        """Test handling of whitespace-only content."""
        whitespace_content = "   \n\t\n   "

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.headers = {'Content-Type': 'text/plain'}
        mock_response.text = AsyncMock(return_value=whitespace_content)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)

        with patch.object(service, '_get_session', return_value=mock_session):
            result = await service._export_as_text("whitespace_doc")

        # After strip(), content is empty - should fail
        assert result.status == "failed"
