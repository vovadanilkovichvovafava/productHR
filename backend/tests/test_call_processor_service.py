"""
Comprehensive unit tests for call processor service.

Tests cover:
- CallProcessor initialization and client setup
- Audio file conversion (WAV format)
- Audio transcription (OpenAI Whisper)
- Audio duration extraction (ffprobe)
- AI analysis (Anthropic Claude) - single and chunked
- Full call processing pipeline
- Transcript analysis from external sources
- Error handling and edge cases
- Database state management
"""
import pytest
import pytest_asyncio
import asyncio
import json
import tempfile
import os
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch, mock_open, call
from pathlib import Path

from api.services.call_processor import (
    CallProcessor,
    call_processor,
    process_call_background
)
from api.models.database import CallRecording, CallStatus, CallSource


# ============================================================================
# FIXTURES
# ============================================================================

def _api_connection_error():
    """Сбой Claude так, как его отдаёт SDK. Процессор ловит APIError /
    APIConnectionError, а не любой Exception (голый Exception — это уже баг
    кода, ему лучше упасть громко)."""
    import httpx
    from anthropic import APIConnectionError
    return APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))


@pytest.fixture
def mock_settings():
    """Mock settings with API keys."""
    with patch('api.services.call_processor.settings') as mock_settings:
        mock_settings.openai_api_key = "test-openai-key-12345"
        mock_settings.anthropic_api_key = "test-anthropic-key-12345"
        yield mock_settings


@pytest.fixture
def mock_settings_no_keys():
    """Mock settings without API keys."""
    with patch('api.services.call_processor.settings') as mock_settings:
        mock_settings.openai_api_key = None
        mock_settings.anthropic_api_key = None
        yield mock_settings


@pytest.fixture
def mock_openai_client():
    """Mock AsyncOpenAI client."""
    mock_client = MagicMock()

    # Mock transcription response
    mock_response = MagicMock()
    mock_response.text = "This is a test transcription of the audio file."

    mock_client.audio.transcriptions.create = AsyncMock(return_value=mock_response)

    return mock_client


@pytest.fixture
def mock_anthropic_client():
    """Mock AsyncAnthropic client."""
    mock_client = MagicMock()

    # Mock analysis response
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=json.dumps({
        "summary": "Test call summary",
        "key_points": ["Point 1", "Point 2", "Point 3"],
        "action_items": ["Task 1", "Task 2"]
    }))]

    mock_client.messages.create = AsyncMock(return_value=mock_response)

    return mock_client


@pytest.fixture
def sample_transcript():
    """Sample transcript for testing."""
    return """[10:00] John Doe: Hello, I'm calling about the position.
[10:01] Jane Smith: Great! Can you tell me about your experience?
[10:02] John Doe: I have 5 years of Python development experience.
[10:03] Jane Smith: That sounds perfect for our team."""


@pytest.fixture
def sample_speakers():
    """Sample speaker segments."""
    return [
        {
            "speaker": "Speaker 1",
            "timestamp": "00:00",
            "text": "Hello, I'm calling about the position."
        },
        {
            "speaker": "Speaker 2",
            "timestamp": "00:15",
            "text": "Great! Can you tell me about your experience?"
        }
    ]


@pytest_asyncio.fixture
async def test_call(db_session, organization, admin_user):
    """Create a test call recording."""
    call = CallRecording(
        org_id=organization.id,
        owner_id=admin_user.id,
        title="Test Call",
        source_type=CallSource.upload,
        status=CallStatus.pending,
        audio_file_path="/tmp/test_audio.mp3",
        created_at=datetime.utcnow()
    )
    db_session.add(call)
    await db_session.commit()
    await db_session.refresh(call)
    return call


# ============================================================================
# INITIALIZATION TESTS
# ============================================================================

class TestCallProcessorInitialization:
    """Tests for CallProcessor initialization."""

    def test_init_creates_instance(self):
        """Test that CallProcessor initializes correctly."""
        processor = CallProcessor()

        assert processor.openai is None
        assert processor.anthropic is None

    def test_init_clients_lazy_loading(self, mock_settings):
        """Test that clients are initialized lazily."""
        processor = CallProcessor()

        with patch('api.services.call_processor.AsyncOpenAI') as mock_openai_class, \
             patch('api.services.call_processor.AsyncAnthropic') as mock_anthropic_class:

            mock_openai_instance = MagicMock()
            mock_anthropic_instance = MagicMock()
            mock_openai_class.return_value = mock_openai_instance
            mock_anthropic_class.return_value = mock_anthropic_instance

            processor._init_clients()

            assert processor.openai is not None
            assert processor.anthropic is not None
            mock_openai_class.assert_called_once_with(api_key="test-openai-key-12345")
            mock_anthropic_class.assert_called_once_with(api_key="test-anthropic-key-12345")

    def test_init_clients_only_once(self, mock_settings):
        """Test that clients are not re-initialized if already present."""
        processor = CallProcessor()

        with patch('api.services.call_processor.AsyncOpenAI') as mock_openai_class, \
             patch('api.services.call_processor.AsyncAnthropic') as mock_anthropic_class:

            mock_openai_instance = MagicMock()
            mock_anthropic_instance = MagicMock()
            mock_openai_class.return_value = mock_openai_instance
            mock_anthropic_class.return_value = mock_anthropic_instance

            processor._init_clients()
            processor._init_clients()  # Second call

            # Should only be called once
            mock_openai_class.assert_called_once()
            mock_anthropic_class.assert_called_once()

    def test_init_clients_no_openai_key(self, mock_settings):
        """Test client initialization when OpenAI key is missing."""
        mock_settings.openai_api_key = None
        processor = CallProcessor()

        processor._init_clients()

        assert processor.openai is None

    def test_init_clients_no_anthropic_key(self, mock_settings):
        """Test client initialization when Anthropic key is missing."""
        mock_settings.anthropic_api_key = None
        processor = CallProcessor()

        processor._init_clients()

        assert processor.anthropic is None

    def test_singleton_instance_exists(self):
        """Test that call_processor singleton is available."""
        assert call_processor is not None
        assert isinstance(call_processor, CallProcessor)


# ============================================================================
# AUDIO CONVERSION TESTS
# ============================================================================

class TestAudioConversion:
    """Tests for audio file conversion to WAV."""

    @pytest.mark.asyncio
    async def test_convert_to_wav_already_wav(self):
        """Test that WAV files are not converted."""
        processor = CallProcessor()

        input_path = "/tmp/audio.wav"
        result = await processor._convert_to_wav(input_path)

        assert result == input_path

    @pytest.mark.asyncio
    async def test_convert_to_wav_mp3_success(self):
        """Test successful conversion from MP3 to WAV."""
        processor = CallProcessor()

        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"", b""))

        with patch('asyncio.create_subprocess_exec', AsyncMock(return_value=mock_process)):
            result = await processor._convert_to_wav("/tmp/audio.mp3")

            assert result == "/tmp/audio_converted.wav"

    @pytest.mark.asyncio
    async def test_convert_to_wav_ffmpeg_command(self):
        """Test that correct ffmpeg command is called."""
        processor = CallProcessor()

        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"", b""))

        with patch('asyncio.create_subprocess_exec', AsyncMock(return_value=mock_process)) as mock_exec:
            await processor._convert_to_wav("/tmp/test.mp3")

            # Verify command arguments
            args = mock_exec.call_args[0]
            assert args[0] == 'ffmpeg'
            assert '-i' in args
            assert '/tmp/test.mp3' in args
            assert '-ar' in args
            assert '16000' in args
            assert '-ac' in args
            assert '1' in args

    @pytest.mark.asyncio
    async def test_convert_to_wav_ffmpeg_failure(self):
        """Test conversion fallback when ffmpeg fails."""
        processor = CallProcessor()

        mock_process = AsyncMock()
        mock_process.returncode = 1
        mock_process.communicate = AsyncMock(return_value=(b"", b"error output"))

        with patch('asyncio.create_subprocess_exec', AsyncMock(return_value=mock_process)):
            result = await processor._convert_to_wav("/tmp/audio.mp3")

            # Should return original file on failure
            assert result == "/tmp/audio.mp3"

    @pytest.mark.asyncio
    async def test_convert_to_wav_exception_handling(self):
        """Test that exceptions during conversion are handled."""
        processor = CallProcessor()

        # Ловятся конкретные ошибки ОС: нет ffmpeg = FileNotFoundError (так
        # create_subprocess_exec сообщает о ненайденной программе).
        with patch('asyncio.create_subprocess_exec', AsyncMock(side_effect=FileNotFoundError("ffmpeg not found"))):
            result = await processor._convert_to_wav("/tmp/audio.mp3")

            # Should return original file on exception
            assert result == "/tmp/audio.mp3"

    @pytest.mark.asyncio
    async def test_convert_to_wav_different_extensions(self):
        """Test conversion with different audio file extensions."""
        processor = CallProcessor()

        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"", b""))

        test_files = [
            "/tmp/audio.mp3",
            "/tmp/audio.m4a",
            "/tmp/audio.ogg",
            "/tmp/audio.flac"
        ]

        for input_path in test_files:
            with patch('asyncio.create_subprocess_exec', AsyncMock(return_value=mock_process)):
                result = await processor._convert_to_wav(input_path)
                expected = input_path.rsplit('.', 1)[0] + '_converted.wav'
                assert result == expected


# ============================================================================
# TRANSCRIPTION TESTS
# ============================================================================

class TestTranscription:
    """Tests for audio transcription using OpenAI Whisper."""

    @pytest.mark.asyncio
    async def test_transcribe_success(self, mock_openai_client):
        """Test successful transcription."""
        processor = CallProcessor()
        processor.openai = mock_openai_client

        # Create temporary audio file
        with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.wav') as f:
            f.write(b"fake audio data")
            temp_path = f.name

        try:
            result = await processor._transcribe(temp_path)

            assert result == "This is a test transcription of the audio file."
            mock_openai_client.audio.transcriptions.create.assert_called_once()

            # Verify call arguments
            call_kwargs = mock_openai_client.audio.transcriptions.create.call_args[1]
            assert call_kwargs['model'] == "whisper-1"
            assert call_kwargs['language'] == "ru"
        finally:
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_transcribe_no_openai_client(self):
        """Test transcription fails when OpenAI client is not configured."""
        processor = CallProcessor()
        processor.openai = None

        with pytest.raises(ValueError, match="OpenAI API key not configured"):
            await processor._transcribe("/tmp/audio.wav")

    @pytest.mark.asyncio
    async def test_transcribe_opens_file(self, mock_openai_client):
        """Test that transcription opens the audio file."""
        processor = CallProcessor()
        processor.openai = mock_openai_client

        with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.wav') as f:
            f.write(b"test audio content")
            temp_path = f.name

        try:
            await processor._transcribe(temp_path)

            # Verify file was opened and passed to API
            call_kwargs = mock_openai_client.audio.transcriptions.create.call_args[1]
            assert 'file' in call_kwargs
        finally:
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_transcribe_file_not_found(self, mock_openai_client):
        """Test transcription with non-existent file."""
        processor = CallProcessor()
        processor.openai = mock_openai_client

        with pytest.raises(FileNotFoundError):
            await processor._transcribe("/nonexistent/file.wav")


# ============================================================================
# DURATION EXTRACTION TESTS
# ============================================================================

class TestDurationExtraction:
    """Tests for audio duration extraction using ffprobe."""

    @pytest.mark.asyncio
    async def test_get_duration_success(self):
        """Test successful duration extraction."""
        processor = CallProcessor()

        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"125.5\n", b""))

        with patch('asyncio.create_subprocess_exec', AsyncMock(return_value=mock_process)):
            result = await processor._get_duration("/tmp/audio.mp3")

            assert result == 125  # Should convert to int

    @pytest.mark.asyncio
    async def test_get_duration_ffprobe_command(self):
        """Test that correct ffprobe command is called."""
        processor = CallProcessor()

        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"60.0", b""))

        with patch('asyncio.create_subprocess_exec', AsyncMock(return_value=mock_process)) as mock_exec:
            await processor._get_duration("/tmp/test.mp3")

            # Verify command arguments
            args = mock_exec.call_args[0]
            assert args[0] == 'ffprobe'
            assert '-i' in args
            assert '/tmp/test.mp3' in args
            assert '-show_entries' in args
            assert 'format=duration' in args

    @pytest.mark.asyncio
    async def test_get_duration_exception_handling(self):
        """Test that exceptions return 0."""
        processor = CallProcessor()

        with patch('asyncio.create_subprocess_exec', AsyncMock(side_effect=Exception("ffprobe failed"))):
            result = await processor._get_duration("/tmp/audio.mp3")

            assert result == 0

    @pytest.mark.asyncio
    async def test_get_duration_invalid_output(self):
        """Test handling of invalid ffprobe output."""
        processor = CallProcessor()

        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"invalid", b""))

        with patch('asyncio.create_subprocess_exec', AsyncMock(return_value=mock_process)):
            result = await processor._get_duration("/tmp/audio.mp3")

            assert result == 0

    @pytest.mark.asyncio
    async def test_get_duration_float_conversion(self):
        """Test that duration is properly converted from float to int."""
        processor = CallProcessor()

        test_cases = [
            (b"123.456\n", 123),
            (b"59.9\n", 59),
            (b"60.5\n", 60),
            (b"0.5\n", 0),
        ]

        for output, expected in test_cases:
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(return_value=(output, b""))

            with patch('asyncio.create_subprocess_exec', AsyncMock(return_value=mock_process)):
                result = await processor._get_duration("/tmp/audio.mp3")
                assert result == expected


# ============================================================================
# AI ANALYSIS TESTS - SINGLE TRANSCRIPT
# ============================================================================

class TestAnalyzeSingle:
    """Tests for analyzing a single (short) transcript."""

    @pytest.mark.asyncio
    async def test_analyze_single_success(self, mock_anthropic_client, sample_transcript):
        """Test successful single transcript analysis."""
        processor = CallProcessor()
        processor.anthropic = mock_anthropic_client

        result = await processor._analyze_single(sample_transcript)

        assert result["summary"] == "Test call summary"
        assert len(result["key_points"]) == 3
        assert len(result["action_items"]) == 2

    @pytest.mark.asyncio
    async def test_analyze_single_api_call_params(self, mock_anthropic_client, sample_transcript):
        """Test that correct parameters are passed to Claude API."""
        processor = CallProcessor()
        processor.anthropic = mock_anthropic_client

        await processor._analyze_single(sample_transcript)

        call_kwargs = mock_anthropic_client.messages.create.call_args[1]
        assert call_kwargs['model'] == "claude-sonnet-4-6"
        assert call_kwargs['max_tokens'] == 16000
        assert len(call_kwargs['messages']) == 1
        assert call_kwargs['messages'][0]['role'] == 'user'

    @pytest.mark.asyncio
    async def test_analyze_single_includes_transcript(self, mock_anthropic_client, sample_transcript):
        """Test that transcript is included in the prompt."""
        processor = CallProcessor()
        processor.anthropic = mock_anthropic_client

        await processor._analyze_single(sample_transcript)

        call_kwargs = mock_anthropic_client.messages.create.call_args[1]
        prompt = call_kwargs['messages'][0]['content']

        assert sample_transcript in prompt

    @pytest.mark.asyncio
    async def test_analyze_single_json_parsing(self, mock_anthropic_client):
        """Test JSON parsing from Claude response."""
        processor = CallProcessor()

        # Mock response with JSON embedded in text
        mock_response = MagicMock()
        mock_response.content = [MagicMock(
            text='Here is the analysis:\n{"summary": "Test", "key_points": [], "action_items": []}\nEnd of analysis.'
        )]
        mock_anthropic_client.messages.create = AsyncMock(return_value=mock_response)
        processor.anthropic = mock_anthropic_client

        result = await processor._analyze_single("test transcript")

        assert result["summary"] == "Test"
        assert result["key_points"] == []

    @pytest.mark.asyncio
    async def test_analyze_single_api_error(self, mock_anthropic_client):
        """Test error handling during analysis."""
        processor = CallProcessor()
        mock_anthropic_client.messages.create = AsyncMock(side_effect=Exception("API error"))
        processor.anthropic = mock_anthropic_client

        result = await processor._analyze_single("test transcript")

        # Should return fallback result
        assert "summary" in result
        assert result["key_points"] == []
        assert result["action_items"] == []

    @pytest.mark.asyncio
    async def test_analyze_single_invalid_json(self, mock_anthropic_client):
        """Test handling of invalid JSON in response."""
        processor = CallProcessor()

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Invalid JSON response")]
        mock_anthropic_client.messages.create = AsyncMock(return_value=mock_response)
        processor.anthropic = mock_anthropic_client

        result = await processor._analyze_single("test")

        # Возвращается явное «Ошибка анализа…», а не кусок транскрипта: иначе
        # транскрипт выглядел как готовое резюме созвона.
        assert "summary" in result
        assert result["summary"].startswith("Ошибка анализа")
        assert result["key_points"] == []


# ============================================================================
# AI ANALYSIS TESTS - CHUNKED TRANSCRIPT
# ============================================================================

class TestAnalyzeChunked:
    """Tests for analyzing long transcripts in chunks."""

    @pytest.mark.asyncio
    async def test_analyze_chunked_splits_correctly(self, mock_anthropic_client):
        """Test that long transcript is split into chunks."""
        processor = CallProcessor()
        processor.anthropic = mock_anthropic_client

        # Create long transcript
        long_transcript = "A" * 120000  # 120k characters
        chunk_size = 50000

        await processor._analyze_chunked(long_transcript, chunk_size)

        # Should make 3 calls (120k / 50k = 2.4 -> 3 chunks)
        assert mock_anthropic_client.messages.create.call_count >= 3

    @pytest.mark.asyncio
    async def test_analyze_chunked_chunk_content(self, mock_anthropic_client):
        """Test that chunks contain correct portions of transcript."""
        processor = CallProcessor()
        processor.anthropic = mock_anthropic_client

        transcript = "PART1" * 15000 + "PART2" * 15000  # 150k characters
        chunk_size = 50000

        await processor._analyze_chunked(transcript, chunk_size)

        # Verify first call contains PART1
        first_call_prompt = mock_anthropic_client.messages.create.call_args_list[0][1]['messages'][0]['content']
        assert "PART1" in first_call_prompt

    @pytest.mark.asyncio
    async def test_analyze_chunked_chunk_analysis_error(self, mock_anthropic_client):
        """Test that chunk analysis errors are handled gracefully."""
        processor = CallProcessor()

        # First call succeeds, second fails, third succeeds
        mock_anthropic_client.messages.create = AsyncMock(
            side_effect=[
                MagicMock(content=[MagicMock(text='{"topics": [], "details": [], "key_points": [], "action_items": [], "profiles": [], "decisions": [], "open_questions": []}')]),
                _api_connection_error(),
                MagicMock(content=[MagicMock(text='{"topics": [], "details": [], "key_points": [], "action_items": [], "profiles": [], "decisions": [], "open_questions": []}')]),
                MagicMock(content=[MagicMock(text='{"summary": "Final", "key_points": [], "action_items": []}')])
            ]
        )
        processor.anthropic = mock_anthropic_client

        result = await processor._analyze_chunked("A" * 120000, 50000)

        # Should still return result despite one chunk failing
        assert result is not None

    @pytest.mark.asyncio
    async def test_analyze_chunked_calls_combine(self, mock_anthropic_client):
        """Test that chunked analysis calls combine method."""
        processor = CallProcessor()
        processor.anthropic = mock_anthropic_client

        with patch.object(processor, '_combine_chunk_analyses', AsyncMock(return_value={
            "summary": "Combined",
            "key_points": [],
            "action_items": []
        })) as mock_combine:
            await processor._analyze_chunked("A" * 100000, 50000)

            # Should call combine with list of analyses
            mock_combine.assert_called_once()
            call_args = mock_combine.call_args[0]
            assert isinstance(call_args[0], list)  # List of chunk analyses


class TestCombineChunkAnalyses:
    """Tests for combining multiple chunk analyses."""

    @pytest.mark.asyncio
    async def test_combine_chunk_analyses_merges_data(self, mock_anthropic_client):
        """Test that data from chunks is properly merged."""
        processor = CallProcessor()
        processor.anthropic = mock_anthropic_client

        chunk_analyses = [
            {
                "topics": ["Topic 1", "Topic 2"],
                "key_points": ["Point 1", "Point 2"],
                "action_items": ["Task 1"],
                "details": [], "profiles": [], "decisions": [], "open_questions": []
            },
            {
                "topics": ["Topic 3"],
                "key_points": ["Point 3", "Point 4"],
                "action_items": ["Task 2", "Task 3"],
                "details": [], "profiles": [], "decisions": [], "open_questions": []
            }
        ]

        result = await processor._combine_chunk_analyses(chunk_analyses, 100000)

        # Should have called synthesis
        mock_anthropic_client.messages.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_combine_chunk_analyses_empty_list(self, mock_anthropic_client):
        """Test combining empty chunk analyses list."""
        processor = CallProcessor()
        processor.anthropic = mock_anthropic_client

        result = await processor._combine_chunk_analyses([], 1000)

        assert result["summary"].startswith("Ошибка анализа")
        assert result["key_points"] == []

    @pytest.mark.asyncio
    async def test_combine_chunk_analyses_synthesis_error(self, mock_anthropic_client):
        """Test fallback when synthesis fails."""
        processor = CallProcessor()
        mock_anthropic_client.messages.create = AsyncMock(side_effect=_api_connection_error())
        processor.anthropic = mock_anthropic_client

        chunk_analyses = [
            {
                "topics": ["Topic 1"],
                "key_points": ["Point 1"],
                "action_items": ["Task 1"],
                "details": [], "profiles": [], "decisions": [], "open_questions": []
            }
        ]

        result = await processor._combine_chunk_analyses(chunk_analyses, 50000)

        # Should return fallback with concatenated data
        assert "summary" in result
        assert "key_points" in result


class TestAnalyze:
    """Tests for main analyze method (routing logic)."""

    @pytest.mark.asyncio
    async def test_analyze_short_transcript_uses_single(self, mock_anthropic_client):
        """Test that short transcripts use single analysis."""
        processor = CallProcessor()
        processor.anthropic = mock_anthropic_client

        short_transcript = "A" * 50000  # 50k chars

        with patch.object(processor, '_analyze_single', AsyncMock(return_value={"summary": "test"})) as mock_single:
            await processor._analyze(short_transcript)

            mock_single.assert_called_once_with(short_transcript)

    @pytest.mark.asyncio
    async def test_analyze_long_transcript_uses_chunked(self, mock_anthropic_client):
        """Test that long transcripts use chunked analysis."""
        processor = CallProcessor()
        processor.anthropic = mock_anthropic_client

        long_transcript = "A" * 70000  # 70k chars

        with patch.object(processor, '_analyze_chunked', AsyncMock(return_value={"summary": "test"})) as mock_chunked:
            await processor._analyze(long_transcript)

            mock_chunked.assert_called_once()

    @pytest.mark.asyncio
    async def test_analyze_no_anthropic_client(self):
        """Test analysis without Anthropic client."""
        processor = CallProcessor()
        processor.anthropic = None

        result = await processor._analyze("test transcript")

        assert "Analysis not available" in result["summary"]
        assert result["key_points"] == []
        assert result["action_items"] == []


# ============================================================================
# FULL CALL PROCESSING TESTS
# ============================================================================

class TestProcessCall:
    """Tests for full call processing pipeline."""

    @pytest.mark.asyncio
    async def test_process_call_success(self, db_session, test_call, mock_settings):
        """Test successful full call processing."""
        processor = CallProcessor()

        # Mock all processing steps
        with patch.object(processor, '_convert_to_wav', AsyncMock(return_value="/tmp/test.wav")) as mock_convert, \
             patch.object(processor, '_transcribe', AsyncMock(return_value="Test transcript")) as mock_transcribe, \
             patch.object(processor, '_get_duration', AsyncMock(return_value=120)) as mock_duration, \
             patch.object(processor, '_analyze', AsyncMock(return_value={
                 "summary": "Test summary",
                 "key_points": ["Point 1"],
                 "action_items": ["Task 1"]
             })) as mock_analyze, \
             patch('api.services.call_processor.AsyncSessionLocal') as mock_session_class:

            # Configure mock session
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=db_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session_class.return_value = mock_session

            await processor.process_call(test_call.id)

            # Verify all steps were called
            mock_convert.assert_called_once()
            mock_transcribe.assert_called_once()
            mock_duration.assert_called_once()
            mock_analyze.assert_called_once()

            # Refresh call from database
            await db_session.refresh(test_call)

            # Verify final state
            assert test_call.status == CallStatus.done
            assert test_call.transcript == "Test transcript"
            assert test_call.summary == "Test summary"
            assert test_call.duration_seconds == 120
            assert test_call.processed_at is not None

    @pytest.mark.asyncio
    async def test_process_call_not_found(self, db_session, mock_settings):
        """Test processing non-existent call."""
        processor = CallProcessor()

        with patch('api.services.call_processor.AsyncSessionLocal') as mock_session_class:
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=db_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session_class.return_value = mock_session

            # Should not raise error, just log
            await processor.process_call(99999)

    @pytest.mark.asyncio
    async def test_process_call_no_audio_file(self, db_session, test_call, mock_settings):
        """Test processing call without audio file."""
        test_call.audio_file_path = None
        await db_session.commit()

        processor = CallProcessor()

        with patch('api.services.call_processor.AsyncSessionLocal') as mock_session_class:
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=db_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session_class.return_value = mock_session

            await processor.process_call(test_call.id)

            await db_session.refresh(test_call)
            assert test_call.status == CallStatus.failed
            assert "No audio file" in test_call.error_message

    @pytest.mark.asyncio
    async def test_process_call_transcription_error(self, db_session, test_call, mock_settings):
        """Test handling of transcription errors."""
        processor = CallProcessor()

        with patch.object(processor, '_convert_to_wav', AsyncMock(return_value="/tmp/test.wav")), \
             patch.object(processor, '_transcribe', AsyncMock(side_effect=Exception("Transcription failed"))), \
             patch('api.services.call_processor.AsyncSessionLocal') as mock_session_class:

            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=db_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session_class.return_value = mock_session

            await processor.process_call(test_call.id)

            await db_session.refresh(test_call)
            assert test_call.status == CallStatus.failed
            assert "Transcription failed" in test_call.error_message

    @pytest.mark.asyncio
    async def test_process_call_status_transitions(self, db_session, test_call, mock_settings):
        """Test that call status transitions correctly during processing."""
        processor = CallProcessor()

        statuses = []
        original_commit = db_session.commit

        async def mock_commit():
            await db_session.flush()
            statuses.append(test_call.status)
            # Don't call original commit to avoid transaction issues

        with patch.object(processor, '_convert_to_wav', AsyncMock(return_value="/tmp/test.wav")), \
             patch.object(processor, '_transcribe', AsyncMock(return_value="Test")), \
             patch.object(processor, '_get_duration', AsyncMock(return_value=100)), \
             patch.object(processor, '_analyze', AsyncMock(return_value={"summary": "Test", "key_points": [], "action_items": []})), \
             patch('api.services.call_processor.AsyncSessionLocal') as mock_session_class, \
             patch.object(db_session, 'commit', mock_commit):

            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=db_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session_class.return_value = mock_session

            await processor.process_call(test_call.id)

            # Should transition: pending -> transcribing -> analyzing -> done
            assert CallStatus.transcribing in statuses
            assert CallStatus.analyzing in statuses
            assert CallStatus.done in statuses or test_call.status == CallStatus.done

    @pytest.mark.asyncio
    async def test_process_call_cleanup_converted_file(self, db_session, test_call, mock_settings):
        """Test that converted audio files are cleaned up."""
        processor = CallProcessor()

        # Create temporary files to simulate conversion
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.mp3') as original:
            original_path = original.name

        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='_converted.wav') as converted:
            converted_path = converted.name

        test_call.audio_file_path = original_path
        await db_session.commit()

        try:
            with patch.object(processor, '_convert_to_wav', AsyncMock(return_value=converted_path)), \
                 patch.object(processor, '_transcribe', AsyncMock(return_value="Test")), \
                 patch.object(processor, '_get_duration', AsyncMock(return_value=100)), \
                 patch.object(processor, '_analyze', AsyncMock(return_value={"summary": "Test", "key_points": [], "action_items": []})), \
                 patch('api.services.call_processor.AsyncSessionLocal') as mock_session_class:

                mock_session = AsyncMock()
                mock_session.__aenter__ = AsyncMock(return_value=db_session)
                mock_session.__aexit__ = AsyncMock(return_value=None)
                mock_session_class.return_value = mock_session

                await processor.process_call(test_call.id)

                # Converted file should be deleted
                assert not os.path.exists(converted_path)
                # Original should still exist
                assert os.path.exists(original_path)
        finally:
            # Cleanup
            if os.path.exists(original_path):
                os.unlink(original_path)
            if os.path.exists(converted_path):
                os.unlink(converted_path)


# ============================================================================
# TRANSCRIPT ANALYSIS TESTS
# ============================================================================

class TestAnalyzeTranscript:
    """Tests for analyzing pre-transcribed content (e.g., from Fireflies)."""

    @pytest.mark.asyncio
    async def test_analyze_transcript_success(
        self, db_session, test_call, sample_transcript, sample_speakers, mock_settings
    ):
        """Test successful transcript analysis."""
        processor = CallProcessor()

        with patch.object(processor, '_analyze', AsyncMock(return_value={
            "summary": "Analysis result",
            "key_points": ["Point 1"],
            "action_items": ["Task 1"]
        })), \
             patch('api.services.call_processor.AsyncSessionLocal') as mock_session_class:

            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=db_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session_class.return_value = mock_session

            await processor.analyze_transcript(
                call_id=test_call.id,
                transcript=sample_transcript,
                speakers=sample_speakers
            )

            await db_session.refresh(test_call)
            assert test_call.status == CallStatus.done
            assert test_call.transcript == sample_transcript
            assert test_call.speakers == sample_speakers
            assert test_call.summary == "Analysis result"

    @pytest.mark.asyncio
    async def test_analyze_transcript_with_fireflies_summary(
        self, db_session, test_call, sample_transcript, sample_speakers, mock_settings
    ):
        """Test using Fireflies summary instead of Claude analysis."""
        processor = CallProcessor()

        fireflies_summary = {
            "overview": "Fireflies summary",
            "keywords": ["keyword1", "keyword2"],
            "action_items": ["Fireflies task 1"]
        }

        with patch.object(processor, '_analyze', AsyncMock()) as mock_analyze, \
             patch('api.services.call_processor.AsyncSessionLocal') as mock_session_class:

            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=db_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session_class.return_value = mock_session

            await processor.analyze_transcript(
                call_id=test_call.id,
                transcript=sample_transcript,
                speakers=sample_speakers,
                fireflies_summary=fireflies_summary
            )

            # Should NOT call Claude analysis
            mock_analyze.assert_not_called()

            await db_session.refresh(test_call)
            assert test_call.summary == "Fireflies summary"
            assert test_call.key_points == ["keyword1", "keyword2"]

    @pytest.mark.asyncio
    async def test_analyze_transcript_fireflies_fallback_to_claude(
        self, db_session, test_call, sample_transcript, sample_speakers, mock_settings
    ):
        """Test fallback to Claude when Fireflies summary is incomplete."""
        processor = CallProcessor()

        # Fireflies summary without overview
        fireflies_summary = {
            "keywords": ["keyword1"],
            "action_items": []
        }

        with patch.object(processor, '_analyze', AsyncMock(return_value={
            "summary": "Claude summary",
            "key_points": [],
            "action_items": []
        })) as mock_analyze, \
             patch('api.services.call_processor.AsyncSessionLocal') as mock_session_class:

            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=db_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session_class.return_value = mock_session

            await processor.analyze_transcript(
                call_id=test_call.id,
                transcript=sample_transcript,
                speakers=sample_speakers,
                fireflies_summary=fireflies_summary
            )

            # Should call Claude analysis as fallback
            mock_analyze.assert_called_once()

            await db_session.refresh(test_call)
            assert test_call.summary == "Claude summary"

    @pytest.mark.asyncio
    async def test_analyze_transcript_call_not_found(self, db_session, sample_transcript, sample_speakers, mock_settings):
        """Test analyzing transcript for non-existent call."""
        processor = CallProcessor()

        with patch('api.services.call_processor.AsyncSessionLocal') as mock_session_class:
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=db_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session_class.return_value = mock_session

            # Should not raise error
            await processor.analyze_transcript(
                call_id=99999,
                transcript=sample_transcript,
                speakers=sample_speakers
            )

    @pytest.mark.asyncio
    async def test_analyze_transcript_error_handling(
        self, db_session, test_call, sample_transcript, sample_speakers, mock_settings
    ):
        """Test error handling during transcript analysis."""
        processor = CallProcessor()

        with patch.object(processor, '_analyze', AsyncMock(side_effect=Exception("Analysis failed"))), \
             patch('api.services.call_processor.AsyncSessionLocal') as mock_session_class:

            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=db_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session_class.return_value = mock_session

            await processor.analyze_transcript(
                call_id=test_call.id,
                transcript=sample_transcript,
                speakers=sample_speakers
            )

            await db_session.refresh(test_call)
            assert test_call.status == CallStatus.failed
            assert "Analysis failed" in test_call.error_message


# ============================================================================
# BACKGROUND TASK TESTS
# ============================================================================

class TestProcessCallBackground:
    """Tests for background task wrapper."""

    @pytest.mark.asyncio
    async def test_process_call_background(self, mock_settings):
        """Test background task wrapper calls process_call."""
        with patch('api.services.call_processor.call_processor') as mock_processor:
            mock_processor.process_call = AsyncMock()
            await process_call_background(123)

            mock_processor.process_call.assert_called_once_with(123)


# ============================================================================
# EDGE CASES AND ERROR HANDLING
# ============================================================================

class TestEdgeCasesAndErrors:
    """Tests for edge cases and comprehensive error handling."""

    @pytest.mark.asyncio
    async def test_empty_transcript_analysis(self, mock_anthropic_client):
        """Test analyzing empty transcript."""
        processor = CallProcessor()
        processor.anthropic = mock_anthropic_client

        result = await processor._analyze("")

        assert result is not None
        assert "summary" in result

    @pytest.mark.asyncio
    async def test_very_long_transcript(self, mock_anthropic_client):
        """Test handling of extremely long transcripts."""
        processor = CallProcessor()
        processor.anthropic = mock_anthropic_client

        very_long = "A" * 500000  # 500k characters

        with patch.object(processor, '_analyze_chunked', AsyncMock(return_value={"summary": "test", "key_points": [], "action_items": []})):
            result = await processor._analyze(very_long)
            assert result is not None

    @pytest.mark.asyncio
    async def test_special_characters_in_transcript(self, mock_anthropic_client):
        """Test handling of special characters in transcript."""
        processor = CallProcessor()
        processor.anthropic = mock_anthropic_client

        special_transcript = "Test with émojis 🎉 and spëcial çhars: <>&\""

        result = await processor._analyze_single(special_transcript)
        assert result is not None

    @pytest.mark.asyncio
    async def test_unicode_transcript(self, mock_anthropic_client):
        """Test handling of Unicode characters in transcript."""
        processor = CallProcessor()
        processor.anthropic = mock_anthropic_client

        unicode_transcript = "Тест на русском языке. 测试中文. テスト日本語。"

        result = await processor._analyze_single(unicode_transcript)
        assert result is not None

    @pytest.mark.asyncio
    async def test_concurrent_processing(self, db_session, organization, admin_user, mock_settings):
        """Test that multiple calls can be processed concurrently."""
        processor = CallProcessor()

        # Create multiple calls
        calls = []
        for i in range(3):
            call = CallRecording(
                org_id=organization.id,
                owner_id=admin_user.id,
                title=f"Call {i}",
                source_type=CallSource.upload,
                status=CallStatus.pending,
                audio_file_path=f"/tmp/test_{i}.mp3"
            )
            db_session.add(call)
            calls.append(call)

        await db_session.commit()

        # Mock commit on db_session to avoid concurrent transaction conflicts
        # Use a lock to ensure only one flush happens at a time
        import asyncio
        commit_lock = asyncio.Lock()

        async def safe_commit():
            # Flush to persist changes without committing transaction
            async with commit_lock:
                await db_session.flush()

        with patch.object(processor, '_convert_to_wav', AsyncMock(return_value="/tmp/test.wav")), \
             patch.object(processor, '_transcribe', AsyncMock(return_value="Test")), \
             patch.object(processor, '_get_duration', AsyncMock(return_value=100)), \
             patch.object(processor, '_analyze', AsyncMock(return_value={"summary": "Test", "key_points": [], "action_items": []})), \
             patch('api.services.call_processor.AsyncSessionLocal') as mock_session_class, \
             patch.object(db_session, 'commit', safe_commit):

            # Each call to AsyncSessionLocal() should return a new mock session
            # that uses the same underlying db_session
            def create_mock_session():
                mock_sess = AsyncMock()
                mock_sess.__aenter__ = AsyncMock(return_value=db_session)
                mock_sess.__aexit__ = AsyncMock(return_value=None)
                return mock_sess

            mock_session_class.side_effect = lambda: create_mock_session()

            # Process all calls concurrently
            tasks = [processor.process_call(call.id) for call in calls]
            await asyncio.gather(*tasks)

            # All should complete
            for call in calls:
                await db_session.refresh(call)
                assert call.status == CallStatus.done
