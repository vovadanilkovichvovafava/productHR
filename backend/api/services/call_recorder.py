"""
Call Recorder Service - Uses Fireflies.ai for meeting recording & transcription.

Instead of self-hosted Puppeteer recorder, we now use Fireflies API:
- addToLiveMeeting: Fireflies bot joins the meeting
- Fireflies handles recording, transcription, and speaker diarization
- Webhook notifies us when transcription is ready
"""

import logging
from typing import Optional

from .fireflies_client import fireflies_client

logger = logging.getLogger("hr-analyzer.call_recorder")


class CallRecorder:
    """
    Manages call recording via Fireflies.ai API.

    Flow:
    1. User provides meeting URL (Google Meet, Zoom, Teams)
    2. We call Fireflies addToLiveMeeting with title "HR Call #{call_id}"
    3. Fireflies bot joins, records, and transcribes
    4. Fireflies sends webhook when done
    5. We fetch transcript and process with Claude
    """

    async def start_recording(
        self,
        call_id: int,
        meeting_url: str,
        bot_name: str = "HR Recorder",
        duration: int = 90
    ) -> dict:
        """
        Start recording a meeting via Fireflies.

        Args:
            call_id: Our internal call ID (used to identify in webhook)
            meeting_url: URL of the meeting (Google Meet, Zoom, Teams)
            bot_name: Not used by Fireflies, but kept for compatibility
            duration: Max recording duration in minutes (default 90)

        Returns:
            {"success": True/False, "message": "..."}
        """
        # Create title that includes call_id for webhook identification
        title = f"HR Call #{call_id}"

        logger.info(f"Starting Fireflies recording for call {call_id}: {meeting_url}")

        result = await fireflies_client.add_to_live_meeting(
            meeting_link=meeting_url,
            title=title,
            language="ru",
            duration=duration
        )

        if result.get("success"):
            logger.info(f"Fireflies bot dispatched for call {call_id}")
        else:
            logger.error(f"Failed to start Fireflies for call {call_id}: {result.get('message')}")

        return result

    async def stop_recording(self, call_id: int):
        """
        Stop recording is not directly supported by Fireflies.
        The bot will leave when the meeting ends or after duration timeout.
        """
        logger.warning(
            f"Stop recording requested for call {call_id}, "
            "but Fireflies bot leaves automatically when meeting ends"
        )

    async def get_transcript(self, transcript_id: str) -> Optional[dict]:
        """
        Fetch transcript from Fireflies.

        Returns:
            {
                "id": "...",
                "title": "...",
                "duration": 1234,
                "speakers": [...],
                "sentences": [...],
                "summary": {...}
            }
        """
        return await fireflies_client.get_transcript(transcript_id)

    async def upload_audio(
        self,
        audio_url: str,
        call_id: int,
        webhook_url: Optional[str] = None
    ) -> dict:
        """
        Upload audio file to Fireflies for transcription.

        Args:
            audio_url: Public URL of the audio file
            call_id: Our internal call ID
            webhook_url: Optional webhook URL for notification

        Returns:
            {"success": True/False, "message": "..."}
        """
        title = f"HR Call #{call_id}"

        return await fireflies_client.upload_audio(
            audio_url=audio_url,
            title=title,
            webhook_url=webhook_url,
            language="ru"
        )


# Global instance
call_recorder = CallRecorder()
