"""
Tests for call processor smart context functions.

Tests:
- calculate_speaker_stats: statistics calculation from speaker segments
- build_smart_context: context building for AI analysis
- identify_participant_roles: role identification for speakers
"""
import pytest
from unittest.mock import MagicMock, AsyncMock
from datetime import datetime


class TestCalculateSpeakerStats:
    """Tests for calculate_speaker_stats function."""

    def test_empty_speakers(self):
        """Test with empty speakers list."""
        from api.services.call_processor import calculate_speaker_stats

        result = calculate_speaker_stats([])
        assert result == {}

    def test_none_speakers(self):
        """Test with None speakers."""
        from api.services.call_processor import calculate_speaker_stats

        result = calculate_speaker_stats(None)
        assert result == {}

    def test_single_speaker(self):
        """Test with single speaker."""
        from api.services.call_processor import calculate_speaker_stats

        speakers = [
            {"speaker": "Speaker 1", "start": 0, "end": 60, "text": "Hello"},
            {"speaker": "Speaker 1", "start": 120, "end": 180, "text": "World"},
        ]

        result = calculate_speaker_stats(speakers)

        assert "Speaker 1" in result
        assert result["Speaker 1"]["total_seconds"] == 120  # 60 + 60
        assert result["Speaker 1"]["segment_count"] == 2
        assert result["Speaker 1"]["first_speak_time"] == 0
        assert result["Speaker 1"]["last_speak_time"] == 180

    def test_multiple_speakers(self):
        """Test with multiple speakers."""
        from api.services.call_processor import calculate_speaker_stats

        speakers = [
            {"speaker": "HR Manager", "start": 0, "end": 30, "text": "Hello"},
            {"speaker": "Candidate", "start": 30, "end": 90, "text": "Hi"},
            {"speaker": "HR Manager", "start": 90, "end": 120, "text": "Tell me..."},
            {"speaker": "Candidate", "start": 120, "end": 300, "text": "I have experience..."},
        ]

        result = calculate_speaker_stats(speakers)

        assert len(result) == 2
        assert result["HR Manager"]["total_seconds"] == 60  # 30 + 30
        assert result["Candidate"]["total_seconds"] == 240  # 60 + 180

    def test_handles_none_timestamps(self):
        """Test handling of None timestamps."""
        from api.services.call_processor import calculate_speaker_stats

        speakers = [
            {"speaker": "Speaker 1", "start": None, "end": 60, "text": "Hello"},
            {"speaker": "Speaker 1", "start": 120, "end": None, "text": "World"},
        ]

        result = calculate_speaker_stats(speakers)

        assert "Speaker 1" in result
        # Should handle None as 0
        assert result["Speaker 1"]["total_seconds"] == 60  # 60-0 + 0-0 (clamped to 0)

    def test_calculates_average(self):
        """Test average segment length calculation."""
        from api.services.call_processor import calculate_speaker_stats

        speakers = [
            {"speaker": "Speaker 1", "start": 0, "end": 20, "text": "Hello"},
            {"speaker": "Speaker 1", "start": 100, "end": 140, "text": "World"},
        ]

        result = calculate_speaker_stats(speakers)

        assert result["Speaker 1"]["avg_segment_length"] == 30  # (20 + 40) / 2

    def test_text_length_fallback_when_no_timestamps(self):
        """Test fallback to text-length estimation when timestamps are all 0."""
        from api.services.call_processor import calculate_speaker_stats

        # Simulate Fireflies data with no timestamps (common issue)
        speakers = [
            {"speaker": "HR Manager", "start": 0, "end": 0, "text": "Hello, welcome to the interview. " * 10},  # ~330 chars
            {"speaker": "Candidate", "start": 0, "end": 0, "text": "Thank you for having me. I am excited to be here. " * 20},  # ~1000 chars
        ]

        result = calculate_speaker_stats(speakers)

        # Should estimate time from text length (~12.5 chars/sec)
        assert result["HR Manager"]["total_seconds"] > 0
        assert result["Candidate"]["total_seconds"] > 0
        assert result["HR Manager"]["estimated"] == True
        assert result["Candidate"]["estimated"] == True
        # Candidate spoke more (more text)
        assert result["Candidate"]["total_seconds"] > result["HR Manager"]["total_seconds"]
        # Should have percentage
        assert result["HR Manager"]["percentage"] > 0
        assert result["Candidate"]["percentage"] > 0
        assert abs(result["HR Manager"]["percentage"] + result["Candidate"]["percentage"] - 100) < 0.5

    def test_percentage_calculation(self):
        """Test that percentage of speaking time is calculated correctly."""
        from api.services.call_processor import calculate_speaker_stats

        speakers = [
            {"speaker": "Speaker A", "start": 0, "end": 60, "text": "Hello"},  # 60 sec
            {"speaker": "Speaker B", "start": 60, "end": 180, "text": "Hi"},  # 120 sec
            {"speaker": "Speaker A", "start": 180, "end": 240, "text": "Bye"},  # 60 sec
        ]

        result = calculate_speaker_stats(speakers)

        # Speaker A: 120 sec (50%), Speaker B: 120 sec (50%)
        assert result["Speaker A"]["percentage"] == 50.0
        assert result["Speaker B"]["percentage"] == 50.0

    def test_real_timestamps_override_text_estimation(self):
        """Test that real timestamps are used when available, not text length."""
        from api.services.call_processor import calculate_speaker_stats

        speakers = [
            {"speaker": "Speaker", "start": 0, "end": 10, "text": "x" * 1000},  # 10 sec from timestamps, not ~80 from text
        ]

        result = calculate_speaker_stats(speakers)

        # Should use timestamp duration (10 sec), not text estimation
        assert result["Speaker"]["total_seconds"] == 10
        assert result["Speaker"]["estimated"] == False

    def test_zero_start_timestamp_accepted(self):
        """Test that 0 is accepted as valid start timestamp (first sentence)."""
        from api.services.call_processor import calculate_speaker_stats

        # First sentence should legitimately start at 0
        speakers = [
            {"speaker": "Speaker A", "start": 0, "end": 5, "text": "Hello"},  # First sentence at 0
            {"speaker": "Speaker B", "start": 5, "end": 15, "text": "Hi there"},  # Second sentence
            {"speaker": "Speaker A", "start": 15, "end": 20, "text": "Bye"},  # Third sentence
        ]

        result = calculate_speaker_stats(speakers)

        # Timestamps should be recognized as valid (not estimated)
        assert result["Speaker A"]["estimated"] == False
        assert result["Speaker B"]["estimated"] == False
        # Durations should be correct
        assert result["Speaker A"]["total_seconds"] == 10  # (5-0) + (20-15) = 10
        assert result["Speaker B"]["total_seconds"] == 10  # (15-5) = 10


class TestBuildSmartContext:
    """Tests for build_smart_context function."""

    def test_basic_call_context(self):
        """Test basic call context building."""
        from api.services.call_processor import build_smart_context

        # Create mock call
        call = MagicMock()
        call.created_at = datetime(2024, 1, 15, 10, 30)
        call.title = "Interview with John"
        call.duration_seconds = 1800  # 30 minutes
        call.summary = "Technical interview discussion"
        call.key_points = ["Experience with Python", "Leadership skills"]
        call.transcript = "Hello, welcome to the interview..."
        call.speakers = None
        call.speaker_stats = None
        call.participant_roles = None

        result = build_smart_context(call)

        assert "15.01.2024" in result
        assert "Interview with John" in result
        assert "30м" in result
        assert "Technical interview discussion" in result
        assert "Experience with Python" in result
        assert "Hello, welcome to the interview..." in result

    def test_short_call_includes_full_transcript(self):
        """Test that short calls include full transcript."""
        from api.services.call_processor import build_smart_context, SHORT_CALL_THRESHOLD

        call = MagicMock()
        call.created_at = datetime(2024, 1, 15)
        call.title = "Short call"
        call.duration_seconds = SHORT_CALL_THRESHOLD - 100  # Under threshold
        call.summary = None
        call.key_points = None
        call.transcript = "A" * 50000  # Long transcript
        call.speakers = None
        call.speaker_stats = None
        call.participant_roles = None

        result = build_smart_context(call)

        # Full transcript should be included for short calls
        assert "A" * 1000 in result  # Check a portion is there
        assert "пропущено" not in result

    def test_long_call_truncates_transcript(self):
        """Test that long calls use smart truncation."""
        from api.services.call_processor import build_smart_context, SHORT_CALL_THRESHOLD

        call = MagicMock()
        call.created_at = datetime(2024, 1, 15)
        call.title = "Long call"
        call.duration_seconds = SHORT_CALL_THRESHOLD + 100  # Over threshold
        call.summary = None
        call.key_points = None
        call.transcript = "START" + "X" * 80000 + "END"  # Very long transcript
        call.speakers = None
        call.speaker_stats = None
        call.participant_roles = None

        result = build_smart_context(call)

        # Should have truncation marker
        assert "пропущено" in result
        # Should have beginning
        assert "START" in result
        # Should have end
        assert "END" in result

    def test_participant_roles_display(self):
        """Test that participant roles are displayed correctly."""
        from api.services.call_processor import build_smart_context

        call = MagicMock()
        call.created_at = datetime(2024, 1, 15)
        call.title = "Interview"
        call.duration_seconds = 1800
        call.summary = None
        call.key_points = None
        call.transcript = "Hello"
        call.speakers = None
        call.speaker_stats = {
            "Speaker 1": {"total_seconds": 900},
            "Speaker 2": {"total_seconds": 600}
        }
        call.participant_roles = {
            "evaluator": {"user_id": 1, "name": "HR Manager", "speaker_name": "Speaker 1"},
            "target": {"entity_id": 5, "name": "John Doe", "type": "candidate", "speaker_name": "Speaker 2"},
            "others": []
        }

        result = build_smart_context(call)

        assert "🔑" in result  # Evaluator icon
        assert "HR Manager" in result
        assert "оценивает" in result
        assert "🎯" in result  # Target icon
        assert "John Doe" in result
        assert "candidate" in result

    def test_speaker_stats_fallback(self):
        """Test fallback to speaker_stats when no roles identified."""
        from api.services.call_processor import build_smart_context

        call = MagicMock()
        call.created_at = datetime(2024, 1, 15)
        call.title = "Call"
        call.duration_seconds = 1800
        call.summary = None
        call.key_points = None
        call.transcript = "Hello"
        call.speakers = None
        call.speaker_stats = {
            "Alex": {"total_seconds": 900},
            "Bob": {"total_seconds": 300}
        }
        call.participant_roles = None

        result = build_smart_context(call)

        assert "Alex" in result
        assert "15м" in result  # 900 seconds = 15 min
        assert "Bob" in result
        assert "5м" in result  # 300 seconds = 5 min


class TestIdentifyParticipantRoles:
    """Tests for identify_participant_roles function."""

    @pytest.mark.asyncio
    async def test_empty_speakers(self):
        """Test with no speakers."""
        from api.services.call_processor import identify_participant_roles

        call = MagicMock()
        call.speakers = None
        call.owner_id = None
        call.entity_id = None

        db = AsyncMock()

        result = await identify_participant_roles(call, db)

        assert result["evaluator"] is None
        assert result["target"] is None
        assert result["others"] == []

    @pytest.mark.asyncio
    async def test_identifies_evaluator_by_email(self):
        """Test evaluator identification by email match."""
        from api.services.call_processor import identify_participant_roles

        # Mock call with speakers
        call = MagicMock()
        call.speakers = [
            {"speaker": "John (john@company.com)", "start": 0, "end": 60}
        ]
        call.owner_id = 1
        # identify_participant_roles считает статистику спикеров по длительности
        # звонка — у голого MagicMock это MagicMock, а не число.
        call.duration_seconds = 60
        call.entity_id = None

        # Mock owner user
        owner = MagicMock()
        owner.id = 1
        owner.name = "John Smith"
        owner.email = "john@company.com"

        # Mock database
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = owner
        db.execute.return_value = mock_result

        result = await identify_participant_roles(call, db)

        assert result["evaluator"] is not None
        assert result["evaluator"]["user_id"] == 1
        assert result["evaluator"]["name"] == "John Smith"
        assert result["evaluator"]["speaker_name"] == "John (john@company.com)"

    @pytest.mark.asyncio
    async def test_unmatched_speakers_go_to_others(self):
        """Test that unmatched speakers are added to others."""
        from api.services.call_processor import identify_participant_roles

        call = MagicMock()
        call.speakers = [
            {"speaker": "Unknown Speaker", "start": 0, "end": 60}
        ]
        call.owner_id = None
        # identify_participant_roles считает статистику спикеров по длительности
        # звонка — у голого MagicMock это MagicMock, а не число.
        call.duration_seconds = 60
        call.entity_id = None

        db = AsyncMock()

        result = await identify_participant_roles(call, db)

        assert len(result["others"]) == 1
        assert result["others"][0]["name"] == "Unknown Speaker"
        assert result["others"][0]["role"] == "unknown"


class TestIntegration:
    """Integration tests for smart context workflow."""

    def test_full_workflow(self):
        """Test complete workflow from speakers to context."""
        from api.services.call_processor import calculate_speaker_stats, build_smart_context

        # Simulate Fireflies data
        speakers = [
            {"speaker": "HR (hr@company.com)", "start": 0, "end": 300, "text": "Welcome..."},
            {"speaker": "Candidate", "start": 300, "end": 900, "text": "Thanks..."},
            {"speaker": "HR (hr@company.com)", "start": 900, "end": 1200, "text": "Great..."},
        ]

        # Calculate stats
        stats = calculate_speaker_stats(speakers)

        assert len(stats) == 2
        assert stats["HR (hr@company.com)"]["total_seconds"] == 600  # 300 + 300
        assert stats["Candidate"]["total_seconds"] == 600

        # Build context
        call = MagicMock()
        call.created_at = datetime(2024, 1, 15)
        call.title = "Interview"
        call.duration_seconds = 1200
        call.summary = "Interview went well"
        call.key_points = ["Good skills"]
        call.transcript = "Welcome to the interview..."
        call.speakers = speakers
        call.speaker_stats = stats
        call.participant_roles = {
            "evaluator": {"user_id": 1, "name": "HR Manager", "speaker_name": "HR (hr@company.com)"},
            "target": {"entity_id": 5, "name": "John", "type": "candidate", "speaker_name": "Candidate"},
            "others": []
        }

        context = build_smart_context(call)

        # Verify context contains all expected elements
        assert "Interview" in context
        assert "HR Manager" in context
        assert "John" in context
        assert "Interview went well" in context
        assert "Good skills" in context
