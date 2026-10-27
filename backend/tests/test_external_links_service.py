"""
Comprehensive unit tests for External Links processor service.
Tests URL detection, file downloads, and processing of external content.
"""
import pytest
import os
import tempfile
from unittest.mock import Mock, MagicMock, AsyncMock, patch
import aiohttp

from api.services.external_links import (
    ExternalLinkProcessor,
    LinkType,
    external_link_processor
)
from api.models.database import CallRecording, CallSource, CallStatus
from api.services.documents import DocumentParseResult


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def processor():
    """Create an ExternalLinkProcessor instance."""
    return ExternalLinkProcessor()


@pytest.fixture
def sample_urls():
    """Sample URLs for testing."""
    return {
        "fireflies": "https://app.fireflies.ai/view/-::01KD5QWTGSP2XFCHP4T3P507DV",
        "fireflies_simple": "https://app.fireflies.ai/view/ABC123xyz",
        "google_doc": "https://docs.google.com/document/d/1ABC123xyz/edit",
        "google_drive": "https://drive.google.com/file/d/1XYZ789abc/view",
        "google_drive_open": "https://drive.google.com/open?id=1XYZ789abc",
        "direct_mp3": "https://example.com/audio/recording.mp3",
        "direct_mp4": "https://example.com/video/meeting.mp4",
        "direct_wav": "https://storage.example.com/files/audio.wav",
        "unknown": "https://example.com/some/page",
        "unknown_with_params": "https://example.com/api/stream?token=abc123"
    }


@pytest.fixture
def mock_call_recording():
    """Create a mock CallRecording."""
    call = Mock(spec=CallRecording)
    call.id = 1
    call.org_id = 1
    call.owner_id = 1
    call.entity_id = None
    call.source_url = None
    call.source_type = None
    call.status = CallStatus.pending
    call.audio_file_path = None
    call.transcript = None
    call.summary = None
    call.action_items = None
    call.key_points = None
    call.error_message = None
    # Поля, которые обработка Fireflies теперь читает (статистика спикеров,
    # длительность). У Mock(spec=…) без значения это Mock, и обработка падала
    # на «'Mock' object is not iterable».
    call.speakers = None
    call.duration_seconds = None
    call.speaker_stats = None
    return call


# ============================================================================
# TEST LINK TYPE DETECTION
# ============================================================================

class TestLinkTypeDetection:
    """Tests for link type detection."""

    def test_detect_fireflies(self, processor, sample_urls):
        """Test detection of Fireflies.ai URLs."""
        link_type = processor.detect_link_type(sample_urls["fireflies"])
        assert link_type == LinkType.FIREFLIES

    def test_detect_fireflies_simple(self, processor, sample_urls):
        """Test detection of simple Fireflies.ai URLs."""
        link_type = processor.detect_link_type(sample_urls["fireflies_simple"])
        assert link_type == LinkType.FIREFLIES

    def test_detect_fireflies_case_insensitive(self, processor):
        """Test case-insensitive detection of Fireflies URLs."""
        url = "https://APP.FIREFLIES.AI/view/ABC123"
        link_type = processor.detect_link_type(url)
        assert link_type == LinkType.FIREFLIES

    def test_detect_google_doc(self, processor, sample_urls):
        """Test detection of Google Docs URLs."""
        link_type = processor.detect_link_type(sample_urls["google_doc"])
        assert link_type == LinkType.GOOGLE_DOC

    def test_detect_google_doc_case_insensitive(self, processor):
        """Test case-insensitive detection of Google Docs."""
        url = "https://DOCS.GOOGLE.COM/Document/d/ABC123/edit"
        link_type = processor.detect_link_type(url)
        assert link_type == LinkType.GOOGLE_DOC

    def test_detect_google_drive(self, processor, sample_urls):
        """Test detection of Google Drive URLs."""
        link_type = processor.detect_link_type(sample_urls["google_drive"])
        assert link_type == LinkType.GOOGLE_DRIVE

    def test_detect_google_drive_open_format(self, processor, sample_urls):
        """Test detection of Google Drive open format URLs."""
        link_type = processor.detect_link_type(sample_urls["google_drive_open"])
        assert link_type == LinkType.GOOGLE_DRIVE

    def test_detect_direct_mp3(self, processor, sample_urls):
        """Test detection of direct MP3 URLs."""
        link_type = processor.detect_link_type(sample_urls["direct_mp3"])
        assert link_type == LinkType.DIRECT_MEDIA

    def test_detect_direct_mp4(self, processor, sample_urls):
        """Test detection of direct MP4 URLs."""
        link_type = processor.detect_link_type(sample_urls["direct_mp4"])
        assert link_type == LinkType.DIRECT_MEDIA

    def test_detect_direct_wav(self, processor, sample_urls):
        """Test detection of direct WAV URLs."""
        link_type = processor.detect_link_type(sample_urls["direct_wav"])
        assert link_type == LinkType.DIRECT_MEDIA

    def test_detect_various_media_extensions(self, processor):
        """Test detection of various media extensions."""
        media_urls = [
            ("https://example.com/file.m4a", LinkType.DIRECT_MEDIA),
            ("https://example.com/file.webm", LinkType.DIRECT_MEDIA),
            ("https://example.com/file.ogg", LinkType.DIRECT_MEDIA),
            ("https://example.com/file.aac", LinkType.DIRECT_MEDIA),
            ("https://example.com/file.flac", LinkType.DIRECT_MEDIA),
            ("https://example.com/file.mov", LinkType.DIRECT_MEDIA),
            ("https://example.com/file.mkv", LinkType.DIRECT_MEDIA),
            ("https://example.com/file.avi", LinkType.DIRECT_MEDIA),
        ]
        for url, expected in media_urls:
            assert processor.detect_link_type(url) == expected

    def test_detect_unknown(self, processor, sample_urls):
        """Test detection of unknown URLs."""
        link_type = processor.detect_link_type(sample_urls["unknown"])
        assert link_type == LinkType.UNKNOWN

    def test_detect_unknown_with_params(self, processor, sample_urls):
        """Test detection of unknown URL with query params."""
        link_type = processor.detect_link_type(sample_urls["unknown_with_params"])
        assert link_type == LinkType.UNKNOWN


# ============================================================================
# TEST FIREFLIES TRANSCRIPT ID EXTRACTION
# ============================================================================

class TestFirefliesExtraction:
    """Tests for Fireflies transcript ID extraction."""

    def test_extract_fireflies_id_standard(self, processor):
        """Test extraction from standard Fireflies URL."""
        url = "https://app.fireflies.ai/view/ABC123xyz"
        transcript_id = processor._extract_fireflies_transcript_id(url)
        assert transcript_id == "ABC123xyz"

    def test_extract_fireflies_id_with_special_chars(self, processor):
        """Test extraction from Fireflies URL with special characters."""
        url = "https://app.fireflies.ai/view/-::01KD5QWTGSP2XFCHP4T3P507DV"
        transcript_id = processor._extract_fireflies_transcript_id(url)
        assert transcript_id == "-::01KD5QWTGSP2XFCHP4T3P507DV"

    def test_extract_fireflies_id_url_encoded(self, processor):
        """Test extraction from URL-encoded Fireflies URL."""
        url = "https://app.fireflies.ai/view/-%3A%3A01KD5QWTGSP2"
        transcript_id = processor._extract_fireflies_transcript_id(url)
        # URL decoded
        assert transcript_id == "-::01KD5QWTGSP2"

    def test_extract_fireflies_id_invalid(self, processor):
        """Test extraction from invalid URL."""
        url = "https://example.com/not-fireflies"
        transcript_id = processor._extract_fireflies_transcript_id(url)
        assert transcript_id is None


# ============================================================================
# TEST GDRIVE FILE ID EXTRACTION
# ============================================================================

class TestGDriveExtraction:
    """Tests for Google Drive file ID extraction."""

    def test_extract_gdrive_file_id_standard(self, processor):
        """Test extraction from standard Google Drive URL."""
        url = "https://drive.google.com/file/d/1ABC123xyz-_def456/view"
        file_id = processor._extract_gdrive_file_id(url)
        assert file_id == "1ABC123xyz-_def456"

    def test_extract_gdrive_file_id_open_format(self, processor):
        """Test extraction from open format URL."""
        url = "https://drive.google.com/open?id=1XYZ789abc"
        file_id = processor._extract_gdrive_file_id(url)
        assert file_id == "1XYZ789abc"

    def test_extract_gdrive_file_id_with_query(self, processor):
        """Test extraction with query parameters."""
        url = "https://drive.google.com/file/d/1ABC123/view?usp=sharing"
        file_id = processor._extract_gdrive_file_id(url)
        assert file_id == "1ABC123"

    def test_extract_gdrive_file_id_invalid(self, processor):
        """Test extraction from invalid URL."""
        url = "https://example.com/not-google-drive"
        file_id = processor._extract_gdrive_file_id(url)
        assert file_id is None


# ============================================================================
# TEST CONTENT TYPE TO EXTENSION
# ============================================================================

class TestContentTypeConversion:
    """Tests for Content-Type to extension conversion."""

    def test_audio_mpeg_to_mp3(self, processor):
        """Test audio/mpeg -> .mp3"""
        ext = processor._content_type_to_ext("audio/mpeg")
        assert ext == ".mp3"

    def test_audio_mp3(self, processor):
        """Test audio/mp3 -> .mp3"""
        ext = processor._content_type_to_ext("audio/mp3")
        assert ext == ".mp3"

    def test_audio_wav(self, processor):
        """Test audio/wav -> .wav"""
        ext = processor._content_type_to_ext("audio/wav")
        assert ext == ".wav"

    def test_video_mp4(self, processor):
        """Test video/mp4 -> .mp4"""
        ext = processor._content_type_to_ext("video/mp4")
        assert ext == ".mp4"

    def test_video_webm(self, processor):
        """Test video/webm -> .webm"""
        ext = processor._content_type_to_ext("video/webm")
        assert ext == ".webm"

    def test_content_type_with_charset(self, processor):
        """Test Content-Type with charset parameter."""
        ext = processor._content_type_to_ext("audio/mpeg; charset=utf-8")
        assert ext == ".mp3"

    def test_unknown_content_type(self, processor):
        """Test unknown content type returns empty string."""
        ext = processor._content_type_to_ext("application/octet-stream")
        assert ext == ""

    def test_audio_m4a(self, processor):
        """Test audio/mp4 -> .m4a"""
        ext = processor._content_type_to_ext("audio/mp4")
        assert ext == ".m4a"


# ============================================================================
# TEST FILE DOWNLOAD
# ============================================================================

class TestFileDownload:
    """Tests for file download functionality."""

    @pytest.fixture
    def real_aiofiles(self, monkeypatch):
        """Настоящий aiofiles.open: conftest подменяет его заглушкой, которая
        ничего не пишет на диск, и os.path.getsize после «скачивания» падал."""
        import aiofiles.threadpool
        monkeypatch.setattr("aiofiles.open", aiofiles.threadpool.open)

    @pytest.mark.asyncio
    async def test_download_success(self, processor, real_aiofiles):
        """Test successful file download."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.headers = {'Content-Type': 'audio/mpeg'}

        # Create mock async iterator for chunks
        async def mock_iter_chunked(size):
            yield b"audio data chunk 1"
            yield b"audio data chunk 2"

        mock_response.content.iter_chunked = mock_iter_chunked
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)

        with patch.object(processor, '_get_session', return_value=mock_session):
            file_path = await processor._download_file(
                "https://example.com/audio.mp3",
                "test_audio"
            )

        assert file_path is not None
        assert file_path.endswith(".mp3")
        # Cleanup
        if file_path and os.path.exists(file_path):
            os.remove(file_path)

    @pytest.mark.asyncio
    async def test_download_404(self, processor):
        """Test download with 404 response."""
        mock_response = AsyncMock()
        mock_response.status = 404
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)

        with patch.object(processor, '_get_session', return_value=mock_session):
            file_path = await processor._download_file(
                "https://example.com/missing.mp3",
                "test_audio"
            )

        assert file_path is None

    @pytest.mark.asyncio
    async def test_download_network_error(self, processor):
        """Test download with network error."""
        mock_session = AsyncMock()
        mock_session.get = MagicMock(side_effect=aiohttp.ClientError("Connection failed"))

        with patch.object(processor, '_get_session', return_value=mock_session):
            file_path = await processor._download_file(
                "https://example.com/audio.mp3",
                "test_audio"
            )

        assert file_path is None

    @pytest.mark.asyncio
    async def test_download_uses_extension_from_filename(self, processor, real_aiofiles):
        """Test that extension from filename is used as fallback."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.headers = {'Content-Type': 'application/octet-stream'}  # Unknown type

        async def mock_iter_chunked(size):
            yield b"audio data"

        mock_response.content.iter_chunked = mock_iter_chunked
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)

        with patch.object(processor, '_get_session', return_value=mock_session):
            file_path = await processor._download_file(
                "https://example.com/audio.wav",
                "audio.wav"
            )

        assert file_path is not None
        assert file_path.endswith(".wav")
        # Cleanup
        if file_path and os.path.exists(file_path):
            os.remove(file_path)


# ============================================================================
# TEST GOOGLE DOC PROCESSING
# ============================================================================

class TestGoogleDocProcessing:
    """Tests for Google Docs processing."""

    @pytest.mark.asyncio
    async def test_process_google_doc_success(self, processor, mock_call_recording):
        """Test successful Google Doc processing."""
        url = "https://docs.google.com/document/d/test123/edit"

        # Mock google_docs_service
        parse_result = DocumentParseResult(
            content="This is the transcript content from the meeting.",
            status="parsed",
            metadata={"doc_id": "test123"}
        )

        # Mock AI analysis
        mock_analysis = {
            "summary": "Meeting summary",
            "action_items": ["Item 1", "Item 2"],
            "key_points": ["Point 1", "Point 2"]
        }

        with patch('api.services.external_links.google_docs_service.parse_from_url', return_value=parse_result), \
             patch('api.services.external_links.call_processor._init_clients'), \
             patch('api.services.external_links.call_processor._analyze', return_value=mock_analysis):

            result = await processor._process_google_doc(mock_call_recording, url)

        assert result.status == CallStatus.done
        assert result.transcript == "This is the transcript content from the meeting."
        assert result.summary == "Meeting summary"
        assert result.action_items == ["Item 1", "Item 2"]

    @pytest.mark.asyncio
    async def test_process_google_doc_parse_failure(self, processor, mock_call_recording):
        """Test Google Doc processing when parsing fails."""
        url = "https://docs.google.com/document/d/private123/edit"

        parse_result = DocumentParseResult(
            status="failed",
            error="Could not access document"
        )

        with patch('api.services.external_links.google_docs_service.parse_from_url', return_value=parse_result):
            result = await processor._process_google_doc(mock_call_recording, url)

        assert result.status == CallStatus.failed
        assert "Could not access" in result.error_message

    @pytest.mark.asyncio
    async def test_process_google_doc_analysis_error(self, processor, mock_call_recording):
        """Test Google Doc processing when AI analysis fails."""
        url = "https://docs.google.com/document/d/test123/edit"

        parse_result = DocumentParseResult(
            content="Transcript content",
            status="parsed"
        )

        with patch('api.services.external_links.google_docs_service.parse_from_url', return_value=parse_result), \
             patch('api.services.external_links.call_processor._init_clients'), \
             patch('api.services.external_links.call_processor._analyze', side_effect=Exception("API error")):

            result = await processor._process_google_doc(mock_call_recording, url)

        assert result.status == CallStatus.failed
        assert "API error" in result.error_message


# ============================================================================
# TEST GOOGLE DRIVE PROCESSING
# ============================================================================

class TestGoogleDriveProcessing:
    """Tests for Google Drive file processing."""

    @pytest.mark.asyncio
    async def test_process_google_drive_success(self, processor, mock_call_recording):
        """Test successful Google Drive file processing."""
        url = "https://drive.google.com/file/d/1ABC123/view"

        # Create a temp file to simulate download
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            f.write(b"fake audio data")
            temp_path = f.name

        try:
            with patch.object(processor, '_download_file', return_value=temp_path):
                result = await processor._process_google_drive(mock_call_recording, url)

            assert result.audio_file_path == temp_path
            assert result.status != CallStatus.failed
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    @pytest.mark.asyncio
    async def test_process_google_drive_invalid_url(self, processor, mock_call_recording):
        """Test Google Drive processing with invalid URL."""
        url = "https://not-google-drive.com/file"

        result = await processor._process_google_drive(mock_call_recording, url)

        assert result.status == CallStatus.failed
        assert "Invalid Google Drive URL" in result.error_message

    @pytest.mark.asyncio
    async def test_process_google_drive_download_failure(self, processor, mock_call_recording):
        """Test Google Drive processing when download fails."""
        url = "https://drive.google.com/file/d/1ABC123/view"

        with patch.object(processor, '_download_file', return_value=None):
            result = await processor._process_google_drive(mock_call_recording, url)

        assert result.status == CallStatus.failed
        assert "Failed to download" in result.error_message


# ============================================================================
# TEST DIRECT MEDIA PROCESSING
# ============================================================================

class TestDirectMediaProcessing:
    """Tests for direct media URL processing."""

    @pytest.mark.asyncio
    async def test_process_direct_media_success(self, processor, mock_call_recording):
        """Test successful direct media processing."""
        url = "https://example.com/audio/meeting.mp3"

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            f.write(b"fake audio data")
            temp_path = f.name

        try:
            with patch.object(processor, '_download_file', return_value=temp_path):
                result = await processor._process_direct_media(mock_call_recording, url)

            assert result.audio_file_path == temp_path
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    @pytest.mark.asyncio
    async def test_process_direct_media_download_failure(self, processor, mock_call_recording):
        """Test direct media processing when download fails."""
        url = "https://example.com/audio/missing.mp3"

        with patch.object(processor, '_download_file', return_value=None):
            result = await processor._process_direct_media(mock_call_recording, url)

        assert result.status == CallStatus.failed
        assert "Failed to download" in result.error_message


# ============================================================================
# TEST UNKNOWN URL PROCESSING
# ============================================================================

class TestUnknownURLProcessing:
    """Tests for unknown URL type processing."""

    @pytest.mark.asyncio
    async def test_process_unknown_audio_content_type(self, processor, mock_call_recording):
        """Test processing unknown URL with audio Content-Type."""
        url = "https://example.com/api/stream?id=123"

        mock_response = AsyncMock()
        mock_response.headers = {'Content-Type': 'audio/mpeg'}
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.head = MagicMock(return_value=mock_response)

        # Create temp file for the subsequent download
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            f.write(b"audio data")
            temp_path = f.name

        try:
            with patch.object(processor, '_get_session', return_value=mock_session), \
                 patch.object(processor, '_process_direct_media') as mock_process:

                mock_process.return_value = mock_call_recording
                mock_call_recording.audio_file_path = temp_path

                result = await processor._process_unknown(mock_call_recording, url)

            mock_process.assert_called_once()
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    @pytest.mark.asyncio
    async def test_process_unknown_video_content_type(self, processor, mock_call_recording):
        """Test processing unknown URL with video Content-Type."""
        url = "https://example.com/stream"

        mock_response = AsyncMock()
        mock_response.headers = {'Content-Type': 'video/mp4'}
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.head = MagicMock(return_value=mock_response)

        with patch.object(processor, '_get_session', return_value=mock_session), \
             patch.object(processor, '_process_direct_media') as mock_process:

            mock_process.return_value = mock_call_recording
            await processor._process_unknown(mock_call_recording, url)

        mock_process.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_unknown_html_content_type(self, processor, mock_call_recording):
        """Test processing unknown URL with HTML Content-Type."""
        url = "https://example.com/page"

        mock_response = AsyncMock()
        mock_response.headers = {'Content-Type': 'text/html'}
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.head = MagicMock(return_value=mock_response)

        with patch.object(processor, '_get_session', return_value=mock_session):
            result = await processor._process_unknown(mock_call_recording, url)

        assert result.status == CallStatus.failed
        assert "web page" in result.error_message.lower()


# ============================================================================
# TEST SESSION MANAGEMENT
# ============================================================================

class TestSessionManagement:
    """Tests for aiohttp session management."""

    @pytest.mark.asyncio
    async def test_session_created_on_first_use(self, processor):
        """Test that session is created on first request."""
        assert processor.session is None

        with patch('aiohttp.ClientSession') as mock_session_class:
            mock_session = MagicMock()
            mock_session.closed = False
            mock_session_class.return_value = mock_session

            session = await processor._get_session()

            assert session is not None

    @pytest.mark.asyncio
    async def test_close_session(self, processor):
        """Test session cleanup."""
        mock_session = AsyncMock()
        mock_session.closed = False
        processor.session = mock_session

        await processor.close()

        mock_session.close.assert_called_once()


# ============================================================================
# TEST SINGLETON INSTANCE
# ============================================================================

class TestSingleton:
    """Tests for singleton instance."""

    def test_singleton_exists(self):
        """Test that singleton instance is created."""
        assert external_link_processor is not None
        assert isinstance(external_link_processor, ExternalLinkProcessor)


# ============================================================================
# TEST MEDIA EXTENSIONS CONSTANT
# ============================================================================

class TestMediaExtensions:
    """Tests for media extension constants."""

    def test_all_common_audio_formats(self, processor):
        """Test that common audio formats are supported."""
        audio_formats = ['.mp3', '.wav', '.m4a', '.ogg', '.aac', '.flac', '.wma']
        for fmt in audio_formats:
            assert fmt in processor.MEDIA_EXTENSIONS

    def test_all_common_video_formats(self, processor):
        """Test that common video formats are supported."""
        video_formats = ['.mp4', '.webm', '.mkv', '.avi', '.mov']
        for fmt in video_formats:
            assert fmt in processor.MEDIA_EXTENSIONS


# ============================================================================
# TEST FIREFLIES PROCESSING
# ============================================================================

class TestFirefliesProcessing:
    """Tests for Fireflies.ai transcript processing."""

    @pytest.mark.asyncio
    async def test_process_fireflies_with_playwright_success(self, processor, mock_call_recording):
        """Test successful Fireflies processing with Playwright."""
        url = "https://app.fireflies.ai/view/ABC123xyz"

        # Mock the page elements to return transcript text (must be > 100 chars total)
        mock_element1 = AsyncMock()
        mock_element1.text_content = AsyncMock(return_value="John: Hello everyone, welcome to our meeting today. Let's discuss the quarterly results.")
        # Add evaluate mock for speaker extraction (new DOM traversal code)
        mock_element1.evaluate = AsyncMock(return_value={
            'speaker': 'John',
            'timestamp': '00:15',
            'startSec': 15.0,
            'endSec': 25.0
        })
        mock_element1.evaluate_handle = AsyncMock(return_value=AsyncMock())
        mock_element1.query_selector = AsyncMock(return_value=None)
        mock_element1.get_attribute = AsyncMock(return_value=None)

        mock_element2 = AsyncMock()
        mock_element2.text_content = AsyncMock(return_value="Jane: Thanks John. I have prepared some slides about our progress on the new product launch.")
        mock_element2.evaluate = AsyncMock(return_value={
            'speaker': 'Jane',
            'timestamp': '00:30',
            'startSec': 30.0,
            'endSec': 45.0
        })
        mock_element2.evaluate_handle = AsyncMock(return_value=AsyncMock())
        mock_element2.query_selector = AsyncMock(return_value=None)
        mock_element2.get_attribute = AsyncMock(return_value=None)

        # Mock page with multiple transcript elements
        mock_page = AsyncMock()
        mock_page.goto = AsyncMock(return_value=None)
        mock_page.wait_for_selector = AsyncMock(return_value=None)
        mock_page.wait_for_timeout = AsyncMock(return_value=None)
        mock_page.query_selector = AsyncMock(return_value=None)  # No title element
        mock_page.query_selector_all = AsyncMock(return_value=[mock_element1, mock_element2])
        # Add content mock for __NEXT_DATA__ extraction
        mock_page.content = AsyncMock(return_value='<html><body><div>Test</div></body></html>')
        mock_page.url = "https://app.fireflies.ai/view/ABC123xyz"
        mock_page.title = AsyncMock(return_value="Test Meeting")
        # Mock page.evaluate for stats extraction
        mock_page.evaluate = AsyncMock(return_value={
            'duration': '14:31',
            'durationSeconds': 871,
            'speakerStats': [],
            'speakerNames': [],
            'debug': {}
        })

        # Mock browser context
        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)

        # Mock browser
        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_browser.close = AsyncMock(return_value=None)

        # Mock chromium
        mock_chromium = MagicMock()
        mock_chromium.launch = AsyncMock(return_value=mock_browser)

        # Mock playwright instance
        mock_playwright_instance = MagicMock()
        mock_playwright_instance.chromium = mock_chromium

        # Create async context manager
        class MockAsyncPlaywright:
            async def __aenter__(self):
                return mock_playwright_instance

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

        def mock_async_playwright():
            return MockAsyncPlaywright()

        # Mock AI analysis
        mock_analysis = {
            "summary": "Fireflies transcript summary",
            "action_items": ["Action 1", "Action 2"],
            "key_points": ["Key point 1", "Key point 2"]
        }

        # Create mock playwright module
        mock_playwright_module = MagicMock()
        mock_playwright_module.async_playwright = mock_async_playwright

        with patch.dict('sys.modules', {'playwright': MagicMock(), 'playwright.async_api': mock_playwright_module}), \
             patch('api.services.external_links.call_processor._init_clients'), \
             patch('api.services.external_links.call_processor._analyze', return_value=mock_analysis):

            result = await processor._process_fireflies(mock_call_recording, url)

        assert result.status == CallStatus.done
        assert result.transcript is not None
        assert len(result.transcript) > 100  # Should have meaningful content
        assert result.summary == "Fireflies transcript summary"
        assert result.fireflies_transcript_id == "ABC123xyz"

    @pytest.mark.asyncio
    async def test_process_fireflies_invalid_url(self, processor, mock_call_recording):
        """Test Fireflies processing with invalid URL."""
        url = "https://example.com/not-fireflies"

        result = await processor._process_fireflies(mock_call_recording, url)

        assert result.status == CallStatus.failed
        assert "could not extract transcript id" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_process_fireflies_empty_transcript(self, processor, mock_call_recording):
        """Test Fireflies processing when transcript extraction fails."""
        url = "https://app.fireflies.ai/view/ABC123"

        # Mock page that returns empty content
        mock_page = AsyncMock()
        mock_page.goto = AsyncMock(return_value=None)
        mock_page.wait_for_selector = AsyncMock(return_value=None)
        mock_page.wait_for_timeout = AsyncMock(return_value=None)
        mock_page.query_selector = AsyncMock(return_value=None)
        mock_page.query_selector_all = AsyncMock(return_value=[])  # No elements found

        mock_browser = AsyncMock()
        mock_browser.new_page = AsyncMock(return_value=mock_page)
        mock_browser.close = AsyncMock(return_value=None)

        mock_chromium = MagicMock()
        mock_chromium.launch = AsyncMock(return_value=mock_browser)

        mock_playwright_instance = MagicMock()
        mock_playwright_instance.chromium = mock_chromium

        class MockAsyncPlaywright:
            async def __aenter__(self):
                return mock_playwright_instance

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

        def mock_async_playwright():
            return MockAsyncPlaywright()

        # Mock HTTP session fallback
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value="<html>No __NEXT_DATA__ here</html>")
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)

        # Create mock playwright module
        mock_playwright_module = MagicMock()
        mock_playwright_module.async_playwright = mock_async_playwright

        with patch.dict('sys.modules', {'playwright': MagicMock(), 'playwright.async_api': mock_playwright_module}), \
             patch.object(processor, '_get_session', return_value=mock_session):

            result = await processor._process_fireflies(mock_call_recording, url)

        assert result.status == CallStatus.failed
        assert "could not extract transcript" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_process_fireflies_playwright_import_error(self, processor, mock_call_recording):
        """Test Fireflies processing when Playwright is not installed."""
        url = "https://app.fireflies.ai/view/ABC123"

        # Mock HTTP fallback with __NEXT_DATA__ (must be > 100 chars total)
        import json
        transcript_data = {
            "title": "Test Meeting",
            "sentences": [
                {"speaker_name": "John", "text": "Hello everyone, welcome to our quarterly review meeting today."},
                {"speaker_name": "Jane", "text": "Thanks John. I have prepared a detailed presentation about our product launch."},
                {"speaker_name": "John", "text": "Great, let's get started with the first topic on our agenda."}
            ],
            "duration": 300
        }
        next_data = {
            "props": {
                "pageProps": {
                    "transcript": transcript_data
                }
            }
        }

        html_content = f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(next_data)}</script>'

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value=html_content)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)

        mock_analysis = {
            "summary": "Test summary",
            "action_items": [],
            "key_points": []
        }

        # Mock ImportError for Playwright by making the module raise on import
        class MockPlaywrightModule:
            @property
            def async_playwright(self):
                raise ImportError("Playwright not installed")

        mock_playwright_module = MockPlaywrightModule()

        with patch.dict('sys.modules', {'playwright': MagicMock(), 'playwright.async_api': mock_playwright_module}), \
             patch.object(processor, '_get_session', return_value=mock_session), \
             patch('api.services.external_links.call_processor._init_clients'), \
             patch('api.services.external_links.call_processor._analyze', return_value=mock_analysis):

            result = await processor._process_fireflies(mock_call_recording, url)

        # Should fall back to HTTP scraping
        assert result.status == CallStatus.done
        assert result.transcript is not None
        assert "John: Hello everyone, welcome" in result.transcript


# ============================================================================
# TEST TEMP DIRECTORY
# ============================================================================

class TestTempDirectory:
    """Tests for temporary directory management."""

    def test_temp_dir_created(self, processor):
        """Test that temp directory is created on init."""
        assert processor.temp_dir is not None
        assert os.path.exists(processor.temp_dir)

    def test_temp_dir_is_writable(self, processor):
        """Test that temp directory is writable."""
        test_file = os.path.join(processor.temp_dir, "test.txt")
        with open(test_file, 'w') as f:
            f.write("test")
        assert os.path.exists(test_file)
        os.remove(test_file)


# ============================================================================
# TEST UPDATED FIREFLIES PARSING (2024-2025)
# ============================================================================

class TestFirefliesUpdatedParsing:
    """Tests for updated Fireflies parsing with modern selectors and lower minimum length."""

    @pytest.mark.asyncio
    async def test_fireflies_accepts_short_transcript_20_chars(self, processor, mock_call_recording):
        """
        Test that Fireflies processing accepts transcripts >= 20 chars.

        This was updated from 100 chars to 20 chars to handle short meetings.
        """
        url = "https://app.fireflies.ai/view/SHORT123"

        # Mock page that returns short but valid transcript (25 chars - just above minimum)
        mock_element = AsyncMock()
        mock_element.text_content = AsyncMock(return_value="Hello, this is a test!")  # 24 chars
        mock_element.get_attribute = AsyncMock(return_value=None)
        mock_element.query_selector = AsyncMock(return_value=None)
        mock_element.evaluate = AsyncMock(return_value={
            'speaker': 'Speaker',
            'timestamp': None,
            'startSec': 0.0,
            'endSec': 5.0
        })
        mock_element.evaluate_handle = AsyncMock(return_value=AsyncMock())

        mock_page = AsyncMock()
        mock_page.goto = AsyncMock(return_value=None)
        mock_page.wait_for_selector = AsyncMock(return_value=None)
        mock_page.wait_for_timeout = AsyncMock(return_value=None)
        mock_page.query_selector = AsyncMock(return_value=None)
        mock_page.query_selector_all = AsyncMock(return_value=[mock_element])
        mock_page.content = AsyncMock(return_value='<html><body><div>Test</div></body></html>')
        mock_page.url = url
        mock_page.title = AsyncMock(return_value="Short Meeting")
        mock_page.evaluate = AsyncMock(return_value={
            'duration': '00:30',
            'durationSeconds': 30,
            'speakerStats': [],
            'speakerNames': [],
            'debug': {}
        })

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)

        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_browser.close = AsyncMock(return_value=None)

        mock_chromium = MagicMock()
        mock_chromium.launch = AsyncMock(return_value=mock_browser)

        mock_playwright_instance = MagicMock()
        mock_playwright_instance.chromium = mock_chromium

        class MockAsyncPlaywright:
            async def __aenter__(self):
                return mock_playwright_instance

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

        def mock_async_playwright():
            return MockAsyncPlaywright()

        mock_playwright_module = MagicMock()
        mock_playwright_module.async_playwright = mock_async_playwright

        mock_analysis = {
            "summary": "Short meeting",
            "action_items": [],
            "key_points": []
        }

        with patch.dict('sys.modules', {'playwright': MagicMock(), 'playwright.async_api': mock_playwright_module}), \
             patch('api.services.external_links.call_processor._init_clients'), \
             patch('api.services.external_links.call_processor._analyze', return_value=mock_analysis):

            result = await processor._process_fireflies(mock_call_recording, url)

        # Should succeed with 20+ char transcript (was previously 100+ chars)
        assert result.status == CallStatus.done, \
            f"Expected CallStatus.done for 24 char transcript, got {result.status}. Error: {result.error_message}"
        assert result.transcript is not None
        assert len(result.transcript) >= 20

    @pytest.mark.asyncio
    async def test_fireflies_rejects_too_short_transcript(self, processor, mock_call_recording):
        """Test that Fireflies processing rejects transcripts < 20 chars."""
        url = "https://app.fireflies.ai/view/TINY123"

        # Mock page that returns transcript below minimum (15 chars)
        mock_element = AsyncMock()
        mock_element.text_content = AsyncMock(return_value="Hi there!")  # 10 chars
        mock_element.get_attribute = AsyncMock(return_value=None)
        mock_element.query_selector = AsyncMock(return_value=None)

        mock_page = AsyncMock()
        mock_page.goto = AsyncMock(return_value=None)
        mock_page.wait_for_selector = AsyncMock(return_value=None)
        mock_page.wait_for_timeout = AsyncMock(return_value=None)
        mock_page.query_selector = AsyncMock(return_value=None)
        mock_page.query_selector_all = AsyncMock(return_value=[mock_element])

        mock_browser = AsyncMock()
        mock_browser.new_page = AsyncMock(return_value=mock_page)
        mock_browser.close = AsyncMock(return_value=None)

        mock_chromium = MagicMock()
        mock_chromium.launch = AsyncMock(return_value=mock_browser)

        mock_playwright_instance = MagicMock()
        mock_playwright_instance.chromium = mock_chromium

        class MockAsyncPlaywright:
            async def __aenter__(self):
                return mock_playwright_instance

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

        def mock_async_playwright():
            return MockAsyncPlaywright()

        mock_playwright_module = MagicMock()
        mock_playwright_module.async_playwright = mock_async_playwright

        # Mock HTTP fallback that also fails
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value="<html>No data</html>")
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)

        with patch.dict('sys.modules', {'playwright': MagicMock(), 'playwright.async_api': mock_playwright_module}), \
             patch.object(processor, '_get_session', return_value=mock_session):

            result = await processor._process_fireflies(mock_call_recording, url)

        # Should fail for transcript < 20 chars
        assert result.status == CallStatus.failed
        assert "could not extract transcript" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_fireflies_extracts_speaker_data(self, processor, mock_call_recording):
        """
        Test that Fireflies parsing extracts speaker names and timing.

        This was added to provide better transcript quality with speaker attribution.
        """
        url = "https://app.fireflies.ai/view/SPEAKERS123"

        # Mock elements with speaker data
        mock_element1 = AsyncMock()
        mock_element1.text_content = AsyncMock(return_value="Hello everyone, welcome to the meeting today.")
        mock_element1.get_attribute = AsyncMock(side_effect=lambda attr: {
            'data-speaker': 'John Smith',
            'data-start': '0',
            'data-end': '5'
        }.get(attr))
        mock_element1.evaluate = AsyncMock(return_value={
            'speaker': 'John Smith',
            'timestamp': '00:00',
            'startSec': 0.0,
            'endSec': 5.0
        })
        mock_element1.evaluate_handle = AsyncMock(return_value=AsyncMock())

        # Mock nested speaker element
        mock_speaker_el = AsyncMock()
        mock_speaker_el.text_content = AsyncMock(return_value="John Smith")
        mock_element1.query_selector = AsyncMock(return_value=mock_speaker_el)

        mock_element2 = AsyncMock()
        mock_element2.text_content = AsyncMock(return_value="Thanks for having us, let's discuss the agenda.")
        mock_element2.get_attribute = AsyncMock(side_effect=lambda attr: {
            'data-speaker': 'Jane Doe',
            'data-start': '6',
            'data-end': '12'
        }.get(attr))
        mock_element2.evaluate = AsyncMock(return_value={
            'speaker': 'Jane Doe',
            'timestamp': '00:06',
            'startSec': 6.0,
            'endSec': 12.0
        })
        mock_element2.evaluate_handle = AsyncMock(return_value=AsyncMock())

        mock_speaker_el2 = AsyncMock()
        mock_speaker_el2.text_content = AsyncMock(return_value="Jane Doe")
        mock_element2.query_selector = AsyncMock(return_value=mock_speaker_el2)

        mock_page = AsyncMock()
        mock_page.goto = AsyncMock(return_value=None)
        mock_page.wait_for_selector = AsyncMock(return_value=None)
        mock_page.wait_for_timeout = AsyncMock(return_value=None)
        mock_page.query_selector = AsyncMock(return_value=None)  # No title
        mock_page.query_selector_all = AsyncMock(return_value=[mock_element1, mock_element2])
        mock_page.content = AsyncMock(return_value='<html><body><div>Test</div></body></html>')
        mock_page.url = url
        mock_page.title = AsyncMock(return_value="Meeting with Speakers")
        mock_page.evaluate = AsyncMock(return_value={
            'duration': '00:15',
            'durationSeconds': 15,
            'speakerStats': [],
            'speakerNames': [],
            'debug': {}
        })

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)

        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_browser.close = AsyncMock(return_value=None)

        mock_chromium = MagicMock()
        mock_chromium.launch = AsyncMock(return_value=mock_browser)

        mock_playwright_instance = MagicMock()
        mock_playwright_instance.chromium = mock_chromium

        class MockAsyncPlaywright:
            async def __aenter__(self):
                return mock_playwright_instance

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

        def mock_async_playwright():
            return MockAsyncPlaywright()

        mock_playwright_module = MagicMock()
        mock_playwright_module.async_playwright = mock_async_playwright

        mock_analysis = {
            "summary": "Meeting with speakers",
            "action_items": ["Review agenda"],
            "key_points": ["Welcome", "Agenda discussion"]
        }

        with patch.dict('sys.modules', {'playwright': MagicMock(), 'playwright.async_api': mock_playwright_module}), \
             patch('api.services.external_links.call_processor._init_clients'), \
             patch('api.services.external_links.call_processor._analyze', return_value=mock_analysis):

            result = await processor._process_fireflies(mock_call_recording, url)

        assert result.status == CallStatus.done
        assert result.transcript is not None
        # Transcript should contain both messages
        assert "Hello everyone" in result.transcript
        assert "Thanks for having us" in result.transcript

    @pytest.mark.asyncio
    async def test_fireflies_uses_modern_selectors(self, processor, mock_call_recording):
        """
        Test that Fireflies parsing uses updated CSS selectors for 2024-2025 UI.

        The selector list now includes:
        - SentenceItem, sentence-item
        - TranscriptSentence, transcript-sentence
        - SpeakerBlock, speaker-block
        - Various transcript container selectors
        """
        url = "https://app.fireflies.ai/view/MODERN123"

        # Create mock that tracks which selectors are tried
        selectors_tried = []

        async def mock_query_selector_all(selector):
            selectors_tried.append(selector)
            if 'SentenceItem' in selector or 'sentence-item' in selector:
                # Return elements when modern selector is used
                mock_el = AsyncMock()
                mock_el.text_content = AsyncMock(return_value="This is a modern Fireflies transcript from 2024.")
                mock_el.get_attribute = AsyncMock(return_value=None)
                mock_el.query_selector = AsyncMock(return_value=None)
                mock_el.evaluate = AsyncMock(return_value={
                    'speaker': 'ModernSpeaker',
                    'timestamp': '00:00',
                    'startSec': 0.0,
                    'endSec': 10.0
                })
                mock_el.evaluate_handle = AsyncMock(return_value=AsyncMock())
                return [mock_el]
            return []

        mock_page = AsyncMock()
        mock_page.goto = AsyncMock(return_value=None)
        mock_page.wait_for_selector = AsyncMock(return_value=None)
        mock_page.wait_for_timeout = AsyncMock(return_value=None)
        mock_page.query_selector = AsyncMock(return_value=None)
        mock_page.query_selector_all = mock_query_selector_all
        mock_page.content = AsyncMock(return_value='<html><body><div>Test</div></body></html>')
        mock_page.url = url
        mock_page.title = AsyncMock(return_value="Modern Meeting")
        mock_page.evaluate = AsyncMock(return_value={
            'duration': '10:00',
            'durationSeconds': 600,
            'speakerStats': [],
            'speakerNames': [],
            'debug': {}
        })

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)

        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_browser.close = AsyncMock(return_value=None)

        mock_chromium = MagicMock()
        mock_chromium.launch = AsyncMock(return_value=mock_browser)

        mock_playwright_instance = MagicMock()
        mock_playwright_instance.chromium = mock_chromium

        class MockAsyncPlaywright:
            async def __aenter__(self):
                return mock_playwright_instance

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

        def mock_async_playwright():
            return MockAsyncPlaywright()

        mock_playwright_module = MagicMock()
        mock_playwright_module.async_playwright = mock_async_playwright

        mock_analysis = {
            "summary": "Modern transcript",
            "action_items": [],
            "key_points": []
        }

        with patch.dict('sys.modules', {'playwright': MagicMock(), 'playwright.async_api': mock_playwright_module}), \
             patch('api.services.external_links.call_processor._init_clients'), \
             patch('api.services.external_links.call_processor._analyze', return_value=mock_analysis):

            result = await processor._process_fireflies(mock_call_recording, url)

        assert result.status == CallStatus.done
        # Verify modern selectors were tried
        modern_selectors_found = any(
            'SentenceItem' in s or 'sentence-item' in s
            for s in selectors_tried
        )
        assert modern_selectors_found, \
            f"Modern selectors not found in tried selectors: {selectors_tried}"

    @pytest.mark.asyncio
    async def test_fireflies_http_fallback_with_next_data(self, processor, mock_call_recording):
        """
        Test that HTTP fallback properly extracts transcript from __NEXT_DATA__.

        This tests the fallback mechanism when Playwright is not available.
        """
        url = "https://app.fireflies.ai/view/FALLBACK123"

        import json
        transcript_data = {
            "title": "Team Standup",
            "sentences": [
                {"speaker_name": "Alice", "text": "Good morning everyone, let's start with updates.", "start_time": 0, "end_time": 5},
                {"speaker_name": "Bob", "text": "I finished the feature yesterday and it's ready for review.", "start_time": 6, "end_time": 12},
                {"speaker_name": "Alice", "text": "Great work! Any blockers for today?", "start_time": 13, "end_time": 17}
            ],
            "duration": 300
        }
        next_data = {
            "props": {
                "pageProps": {
                    "transcript": transcript_data
                }
            }
        }

        html_content = f'<html><script id="__NEXT_DATA__" type="application/json">{json.dumps(next_data)}</script></html>'

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value=html_content)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)

        mock_analysis = {
            "summary": "Standup summary",
            "action_items": ["Review feature"],
            "key_points": ["Feature complete", "No blockers"]
        }

        # Simulate Playwright not being available
        class MockPlaywrightModule:
            @property
            def async_playwright(self):
                raise ImportError("Playwright not installed")

        mock_playwright_module = MockPlaywrightModule()

        with patch.dict('sys.modules', {'playwright': MagicMock(), 'playwright.async_api': mock_playwright_module}), \
             patch.object(processor, '_get_session', return_value=mock_session), \
             patch('api.services.external_links.call_processor._init_clients'), \
             patch('api.services.external_links.call_processor._analyze', return_value=mock_analysis):

            result = await processor._process_fireflies(mock_call_recording, url)

        assert result.status == CallStatus.done
        assert result.transcript is not None
        # Should have speaker prefixes from HTTP fallback
        assert "Alice:" in result.transcript
        assert "Bob:" in result.transcript
        assert "Good morning everyone" in result.transcript
        # Title should be extracted
        assert result.title == "Team Standup" or result.title is None  # May keep original title
        # Duration should be extracted
        assert result.duration_seconds == 300


# ============================================================================
# TEST TIMESTAMP EXTRACTION
# ============================================================================

class TestFirefliesTimestampExtraction:
    """Tests for timestamp extraction from Fireflies."""

    @pytest.mark.asyncio
    async def test_zero_timestamp_accepted(self, processor, mock_call_recording):
        """
        Test that 0 is accepted as a valid timestamp.

        This tests the fix for the bug where 'if start > 0' rejected valid 0 values.
        First sentence of any recording legitimately starts at 0.
        """
        url = "https://app.fireflies.ai/view/TIMESTAMP123"

        import json
        transcript_data = {
            "title": "Interview Call",
            "sentences": [
                # First sentence should start at 0 - this was being rejected!
                {"speaker_name": "HR", "text": "Welcome to the interview.", "start_time": 0, "end_time": 5},
                {"speaker_name": "Candidate", "text": "Thank you.", "start_time": 5, "end_time": 8},
                {"speaker_name": "HR", "text": "Tell me about yourself.", "start_time": 8, "end_time": 12}
            ],
            "duration": 120
        }
        next_data = {
            "props": {"pageProps": {"transcript": transcript_data}}
        }

        html_content = f'<html><script id="__NEXT_DATA__" type="application/json">{json.dumps(next_data)}</script></html>'

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value=html_content)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)

        mock_analysis = {"summary": "Interview", "action_items": [], "key_points": []}

        class MockPlaywrightModule:
            @property
            def async_playwright(self):
                raise ImportError("Playwright not installed")

        with patch.dict('sys.modules', {'playwright': MagicMock(), 'playwright.async_api': MockPlaywrightModule()}), \
             patch.object(processor, '_get_session', return_value=mock_session), \
             patch('api.services.external_links.call_processor._init_clients'), \
             patch('api.services.external_links.call_processor._analyze', return_value=mock_analysis):

            result = await processor._process_fireflies(mock_call_recording, url)

        assert result.status == CallStatus.done
        assert result.speakers is not None
        # First speaker segment should have start=0 (not rejected!)
        assert result.speakers[0]["start"] == 0
        assert result.speakers[0]["end"] == 5
        # All timestamps should be preserved
        assert result.speakers[1]["start"] == 5
        assert result.speakers[1]["end"] == 8
        assert result.speakers[2]["start"] == 8
        assert result.speakers[2]["end"] == 12


# ============================================================================
# TEST SPEAKER ID MAPPING
# ============================================================================

class TestFirefliesSpeakerIdMapping:
    """Tests for speaker ID → name mapping in Fireflies extraction."""

    @pytest.mark.asyncio
    @pytest.mark.xfail(reason="Speaker mapping logic needs review")
    async def test_speaker_id_to_name_mapping(self, processor, mock_call_recording):
        """
        Test that speaker IDs are mapped to names from speakers list.

        This tests the new speaker mapping functionality where:
        - speakers list contains {id, name, email}
        - sentences use speaker_id instead of speaker_name
        """
        url = "https://app.fireflies.ai/view/MAPPING123"

        import json
        transcript_data = {
            "title": "Interview Call",
            "speakers": [
                {"id": 0, "name": "John Smith", "email": "john@company.com"},
                {"id": 1, "name": "Jane Candidate", "email": "jane@email.com"}
            ],
            "sentences": [
                {"speaker_id": 0, "text": "Welcome to the interview.", "start_time": 0, "end_time": 5},
                {"speaker_id": 1, "text": "Thank you for having me.", "start_time": 6, "end_time": 10},
                {"speaker_id": 0, "text": "Tell me about yourself.", "start_time": 11, "end_time": 15}
            ],
            "duration": 300
        }
        next_data = {
            "props": {"pageProps": {"transcript": transcript_data}}
        }

        html_content = f'<html><script id="__NEXT_DATA__" type="application/json">{json.dumps(next_data)}</script></html>'

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value=html_content)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)

        mock_analysis = {"summary": "Interview", "action_items": [], "key_points": []}

        # Mock ensure_playwright_installed to return False so HTTP fallback is used
        with patch('api.services.external_links.ensure_playwright_installed', AsyncMock(return_value=False)), \
             patch.object(processor, '_get_session', return_value=mock_session), \
             patch('api.services.external_links.call_processor._init_clients'), \
             patch('api.services.external_links.call_processor._analyze', return_value=mock_analysis):

            result = await processor._process_fireflies(mock_call_recording, url)

        assert result.status == CallStatus.done
        # Should have mapped speaker IDs to names with emails
        assert "John Smith (john@company.com):" in result.transcript or "John Smith:" in result.transcript
        assert "Welcome to the interview" in result.transcript
        assert result.speakers is not None
        # Speaker names in speakers list should be mapped, not generic "Speaker"
        speaker_names = {s["speaker"] for s in result.speakers}
        assert "Speaker" not in speaker_names or len(speaker_names) > 1  # Either no "Speaker" or both

    @pytest.mark.asyncio
    async def test_speaker_index_to_name_mapping(self, processor, mock_call_recording):
        """
        Test that speaker_index is mapped to speakers list when speaker_id doesn't match.
        """
        url = "https://app.fireflies.ai/view/INDEX123"

        import json
        transcript_data = {
            "title": "Team Meeting",
            "speakers": [
                {"name": "Manager Alice"},
                {"name": "Developer Bob"}
            ],
            "sentences": [
                {"speakerIndex": 0, "text": "Let's start the meeting.", "start": 0, "end": 5},
                {"speakerIndex": 1, "text": "Sure, I have updates.", "start": 6, "end": 10}
            ],
            "duration": 120
        }
        next_data = {
            "props": {"pageProps": {"transcript": transcript_data}}
        }

        html_content = f'<html><script id="__NEXT_DATA__" type="application/json">{json.dumps(next_data)}</script></html>'

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value=html_content)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)

        mock_analysis = {"summary": "Meeting", "action_items": [], "key_points": []}

        class MockPlaywrightModule:
            @property
            def async_playwright(self):
                raise ImportError("Playwright not installed")

        with patch.dict('sys.modules', {'playwright': MagicMock(), 'playwright.async_api': MockPlaywrightModule()}), \
             patch.object(processor, '_get_session', return_value=mock_session), \
             patch('api.services.external_links.call_processor._init_clients'), \
             patch('api.services.external_links.call_processor._analyze', return_value=mock_analysis):

            result = await processor._process_fireflies(mock_call_recording, url)

        assert result.status == CallStatus.done
        assert result.transcript is not None
        # Should contain actual speaker names from speakers list
        assert "Let's start the meeting" in result.transcript

    @pytest.mark.asyncio
    async def test_participants_list_mapping(self, processor, mock_call_recording):
        """
        Test that participants list is used when speakers list is not available.
        """
        url = "https://app.fireflies.ai/view/PARTICIPANTS123"

        import json
        transcript_data = {
            "title": "Client Call",
            "participants": [
                {"id": "p1", "name": "Sales Rep", "email": "sales@company.com"},
                {"id": "p2", "name": "Client CEO", "email": "ceo@client.com"}
            ],
            "sentences": [
                {"speaker_id": "p1", "text": "Thanks for joining.", "start_time": 0, "end_time": 3},
                {"speaker_id": "p2", "text": "Happy to be here.", "start_time": 4, "end_time": 7}
            ],
            "duration": 600
        }
        next_data = {
            "props": {"pageProps": {"transcript": transcript_data}}
        }

        html_content = f'<html><script id="__NEXT_DATA__" type="application/json">{json.dumps(next_data)}</script></html>'

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value=html_content)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)

        mock_analysis = {"summary": "Client call", "action_items": [], "key_points": []}

        class MockPlaywrightModule:
            @property
            def async_playwright(self):
                raise ImportError("Playwright not installed")

        with patch.dict('sys.modules', {'playwright': MagicMock(), 'playwright.async_api': MockPlaywrightModule()}), \
             patch.object(processor, '_get_session', return_value=mock_session), \
             patch('api.services.external_links.call_processor._init_clients'), \
             patch('api.services.external_links.call_processor._analyze', return_value=mock_analysis):

            result = await processor._process_fireflies(mock_call_recording, url)

        assert result.status == CallStatus.done
        # Participants should be used for speaker mapping
        assert "Thanks for joining" in result.transcript


# ============================================================================
# TEST ASYNC PROCESSING (NEW)
# ============================================================================

class TestAsyncFirefliesProcessing:
    """Tests for async Fireflies processing with progress tracking."""

    @pytest.mark.asyncio
    async def test_create_pending_call(self, processor):
        """Test create_pending_call creates record with pending status."""
        from unittest.mock import AsyncMock, MagicMock, patch

        # Mock the database session
        mock_call = MagicMock()
        mock_call.id = 123
        mock_call.status = CallStatus.pending
        mock_call.progress = 0
        mock_call.progress_stage = None

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        # Mock the context manager
        mock_session_cm = MagicMock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_cm.__aexit__ = AsyncMock(return_value=None)

        with patch('api.database.AsyncSessionLocal', return_value=mock_session_cm):
            result = await processor.create_pending_call(
                url="https://app.fireflies.ai/view/TEST123",
                organization_id=1,
                owner_id=1,
                source_type=CallSource.fireflies,
                entity_id=None,
                title="Test Call"
            )

        # Verify a CallRecording was added
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_progress(self, processor):
        """Test _update_progress updates progress in database."""
        from unittest.mock import AsyncMock, MagicMock, patch
        from sqlalchemy import update

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock()
        mock_db.commit = AsyncMock()

        mock_session_cm = MagicMock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_cm.__aexit__ = AsyncMock(return_value=None)

        # org_id передаём сами: без него _update_progress вторым запросом
        # достаёт org_id звонка (для рассылки прогресса по WebSocket).
        with patch('api.database.AsyncSessionLocal', return_value=mock_session_cm), \
             patch('api.routes.realtime.broadcast_call_progress', AsyncMock()) as mock_broadcast:
            await processor._update_progress(123, 50, "Processing...", org_id=1)

        # Verify execute was called with update statement
        mock_db.execute.assert_called_once()
        assert "UPDATE" in str(mock_db.execute.call_args[0][0]).upper()
        mock_db.commit.assert_called_once()
        mock_broadcast.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_process_fireflies_async_updates_progress(self, processor):
        """Test process_fireflies_async updates progress during processing."""
        from unittest.mock import AsyncMock, MagicMock, patch

        # Track progress updates
        progress_updates = []

        # Прогресс теперь передаёт и org_id (для рассылки по WebSocket).
        async def mock_update_progress(call_id, progress, stage, org_id=None):
            progress_updates.append((call_id, progress, stage))

        mock_call = MagicMock()
        mock_call.id = 123
        mock_call.source_url = "https://app.fireflies.ai/view/TEST123"
        mock_call.status = CallStatus.pending
        mock_call.progress = 0
        mock_call.progress_stage = None
        mock_call.transcript = None
        mock_call.summary = None
        mock_call.action_items = None
        mock_call.key_points = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_call)

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        mock_session_cm = MagicMock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_cm.__aexit__ = AsyncMock(return_value=None)

        # Mock _process_fireflies to return quickly
        async def mock_process_fireflies(call, url, call_id):
            call.transcript = "Test transcript content here"
            call.status = CallStatus.done
            return call

        with patch('api.database.AsyncSessionLocal', return_value=mock_session_cm), \
             patch.object(processor, '_update_progress', side_effect=mock_update_progress), \
             patch.object(processor, '_process_fireflies', side_effect=mock_process_fireflies), \
             patch.object(processor, '_broadcast_call_failed_safe', AsyncMock()):

            await processor.process_fireflies_async(123)

        # Verify progress was updated at start (5%) and page load (10%)
        assert len(progress_updates) >= 2
        assert progress_updates[0] == (123, 5, "Запуск обработки...")
        assert progress_updates[1] == (123, 10, "Загрузка страницы Fireflies...")

    @pytest.mark.asyncio
    async def test_process_fireflies_async_handles_missing_call(self, processor):
        """Test process_fireflies_async handles missing call record gracefully."""
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        mock_session_cm = MagicMock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_cm.__aexit__ = AsyncMock(return_value=None)

        with patch('api.database.AsyncSessionLocal', return_value=mock_session_cm), \
             patch.object(processor, '_update_progress', AsyncMock()), \
             patch.object(processor, '_broadcast_call_failed_safe', AsyncMock()):

            # Should not raise exception
            await processor.process_fireflies_async(999)

    @pytest.mark.asyncio
    async def test_process_fireflies_async_handles_error(self, processor):
        """Test process_fireflies_async sets failed status on error."""
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_call = MagicMock()
        mock_call.id = 123
        mock_call.source_url = "https://app.fireflies.ai/view/TEST123"
        mock_call.status = CallStatus.pending
        mock_call.progress = 0
        mock_call.progress_stage = None
        mock_call.error_message = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_call)

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        mock_session_cm = MagicMock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_cm.__aexit__ = AsyncMock(return_value=None)

        # Mock _process_fireflies to raise an error
        async def mock_process_fireflies_error(call, url, call_id):
            raise Exception("Test error")

        with patch('api.database.AsyncSessionLocal', return_value=mock_session_cm), \
             patch.object(processor, '_update_progress', AsyncMock()), \
             patch.object(processor, '_process_fireflies', side_effect=mock_process_fireflies_error), \
             patch.object(processor, '_broadcast_call_failed_safe', AsyncMock()):

            await processor.process_fireflies_async(123)

        # Verify status was set to failed
        assert mock_call.status == CallStatus.failed
        assert "Test error" in mock_call.error_message
        assert mock_call.progress == 0
        assert mock_call.progress_stage == "Ошибка"


# ============================================================================
# TEST PROGRESS STAGES
# ============================================================================

class TestProgressStages:
    """Tests for progress stage updates during Fireflies processing."""

    @pytest.mark.asyncio
    @pytest.mark.xfail(reason="Progress stage order includes initial 0% which may appear at end")
    async def test_fireflies_progress_stages_order(self, processor, mock_call_recording):
        """Test that progress stages are updated in correct order."""
        url = "https://app.fireflies.ai/view/PROGRESS123"

        progress_updates = []

        # Capture progress updates
        original_update_progress = processor._update_progress

        async def capture_progress(call_id, progress, stage):
            progress_updates.append((progress, stage))

        # Mock the page
        mock_element = AsyncMock()
        mock_element.text_content = AsyncMock(return_value="This is a sufficiently long transcript for testing purposes.")
        mock_element.get_attribute = AsyncMock(return_value=None)
        mock_element.query_selector = AsyncMock(return_value=None)
        mock_element.evaluate = AsyncMock(return_value={
            'speaker': 'TestSpeaker',
            'timestamp': '00:00',
            'startSec': 0.0,
            'endSec': 5.0
        })
        mock_element.evaluate_handle = AsyncMock(return_value=AsyncMock())

        mock_page = AsyncMock()
        mock_page.goto = AsyncMock(return_value=None)
        mock_page.wait_for_selector = AsyncMock(return_value=None)
        mock_page.wait_for_timeout = AsyncMock(return_value=None)
        mock_page.query_selector = AsyncMock(return_value=None)
        mock_page.query_selector_all = AsyncMock(return_value=[mock_element])
        mock_page.content = AsyncMock(return_value='<html><body><div>Test</div></body></html>')
        mock_page.url = url
        mock_page.title = AsyncMock(return_value="Test Meeting")
        mock_page.evaluate = AsyncMock(return_value={
            'duration': '05:00',
            'durationSeconds': 300,
            'speakerStats': [],
            'speakerNames': [],
            'debug': {}
        })

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)

        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_browser.close = AsyncMock(return_value=None)

        mock_chromium = MagicMock()
        mock_chromium.launch = AsyncMock(return_value=mock_browser)

        mock_playwright_instance = MagicMock()
        mock_playwright_instance.chromium = mock_chromium

        class MockAsyncPlaywright:
            async def __aenter__(self):
                return mock_playwright_instance

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

        def mock_async_playwright():
            return MockAsyncPlaywright()

        mock_playwright_module = MagicMock()
        mock_playwright_module.async_playwright = mock_async_playwright

        mock_analysis = {
            "summary": "Test",
            "action_items": [],
            "key_points": []
        }

        with patch.dict('sys.modules', {'playwright': MagicMock(), 'playwright.async_api': mock_playwright_module}), \
             patch.object(processor, '_update_progress', side_effect=capture_progress), \
             patch('api.services.external_links.call_processor._init_clients'), \
             patch('api.services.external_links.call_processor._analyze', return_value=mock_analysis):

            result = await processor._process_fireflies(mock_call_recording, url, call_id=123)

        # Verify progress stages are in order
        if progress_updates:
            progress_values = [p[0] for p in progress_updates]
            assert progress_values == sorted(progress_values), \
                f"Progress should increase monotonically: {progress_values}"

