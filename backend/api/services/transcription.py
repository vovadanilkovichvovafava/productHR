import os
import tempfile
import asyncio
import subprocess
import glob
import io

import aiofiles
from openai import AsyncOpenAI
from ..config import get_settings

settings = get_settings()

# OpenAI Whisper has a 25MB file size limit
# Using 24MB as a safe threshold
MAX_FILE_SIZE = 24 * 1024 * 1024  # 24MB in bytes


class TranscriptionService:
    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None

    async def _split_audio_chunks(self, audio_path: str, chunk_duration_sec: int = 600) -> list[str]:
        """
        Split audio file into chunks using FFmpeg.

        Args:
            audio_path: Path to the audio file
            chunk_duration_sec: Duration of each chunk in seconds (default 10 minutes)

        Returns:
            List of paths to chunk files
        """
        # Create temp directory for chunks
        temp_dir = tempfile.mkdtemp(prefix="audio_chunks_")

        # Get file extension
        _, ext = os.path.splitext(audio_path)
        if not ext:
            ext = ".mp3"

        # Output pattern for chunks
        output_pattern = os.path.join(temp_dir, f"chunk_%03d{ext}")

        try:
            # Use FFmpeg to split audio into segments
            process = await asyncio.create_subprocess_exec(
                "ffmpeg", "-i", audio_path,
                "-f", "segment",
                "-segment_time", str(chunk_duration_sec),
                "-c", "copy",  # Copy codec without re-encoding (faster)
                "-y", output_pattern,
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            )
            _, stderr = await process.communicate()

            if process.returncode != 0:
                stderr_text = stderr.decode() if stderr else ""
                raise Exception(f"FFmpeg split failed: {stderr_text[:200]}")

            # Get list of created chunk files, sorted by name
            chunk_pattern = os.path.join(temp_dir, f"chunk_*{ext}")
            chunk_files = sorted(glob.glob(chunk_pattern))

            if not chunk_files:
                raise Exception("No chunks were created")

            return chunk_files

        except Exception as e:
            # Clean up on error
            import shutil
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            raise e

    async def _transcribe_single_file(self, file_path: str) -> str:
        """Transcribe a single audio file (must be under 25MB)."""
        try:
            async with aiofiles.open(file_path, "rb") as f:
                file_content = await f.read()
            # OpenAI API needs a file-like object with a name attribute
            file_obj = io.BytesIO(file_content)
            file_obj.name = os.path.basename(file_path)
            response = await self.client.audio.transcriptions.create(
                model="whisper-1", file=file_obj, language="ru"
            )
            return response.text
        except Exception as e:
            return f"[Ошибка транскрипции: {e}]"

    async def transcribe_audio(self, audio_bytes: bytes) -> str:
        """
        Transcribe audio bytes using OpenAI Whisper.
        For large files (>24MB), automatically splits into chunks and combines transcripts.
        """
        if not self.client:
            return "[Транскрипция недоступна - OPENAI_API_KEY не настроен]"

        try:
            # Check file size
            file_size = len(audio_bytes)

            # Save bytes to temp file
            with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
                tmp.write(audio_bytes)
                tmp_path = tmp.name

            try:
                # If file is small enough, transcribe directly
                if file_size <= MAX_FILE_SIZE:
                    return await self._transcribe_single_file(tmp_path)

                # Large file: split into chunks and transcribe each
                chunk_files = await self._split_audio_chunks(tmp_path)

                try:
                    transcripts = []
                    for i, chunk_path in enumerate(chunk_files):
                        # Check chunk size - if still too large, we have a problem
                        chunk_size = os.path.getsize(chunk_path)
                        if chunk_size > MAX_FILE_SIZE:
                            # Re-split this chunk with smaller duration
                            sub_chunks = await self._split_audio_chunks(chunk_path, chunk_duration_sec=300)
                            try:
                                for sub_chunk in sub_chunks:
                                    transcript = await self._transcribe_single_file(sub_chunk)
                                    if not transcript.startswith("[Ошибка"):
                                        transcripts.append(transcript)
                            finally:
                                # Clean up sub-chunks
                                import shutil
                                sub_dir = os.path.dirname(sub_chunks[0]) if sub_chunks else None
                                if sub_dir and os.path.exists(sub_dir):
                                    shutil.rmtree(sub_dir)
                        else:
                            transcript = await self._transcribe_single_file(chunk_path)
                            if not transcript.startswith("[Ошибка"):
                                transcripts.append(transcript)

                    # Combine all transcripts into one
                    if transcripts:
                        return " ".join(transcripts)
                    else:
                        return "[Не удалось транскрибировать аудио]"

                finally:
                    # Clean up chunk files
                    import shutil
                    chunk_dir = os.path.dirname(chunk_files[0]) if chunk_files else None
                    if chunk_dir and os.path.exists(chunk_dir):
                        shutil.rmtree(chunk_dir)

            finally:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
        except Exception as e:
            return f"[Ошибка транскрипции: {e}]"

    async def transcribe_video(self, video_bytes: bytes, filename: str = None) -> str:
        """Extract audio from video and transcribe."""
        if not self.client:
            return "[Транскрипция недоступна - OPENAI_API_KEY не настроен]"

        # Detect file extension from filename or use mp4 as default
        suffix = ".mp4"
        if filename:
            if filename.lower().endswith('.webm'):
                suffix = ".webm"
            elif filename.lower().endswith('.mov'):
                suffix = ".mov"
            elif filename.lower().endswith('.avi'):
                suffix = ".avi"

        video_path = None
        audio_path = None
        try:
            # Save video to temp file with correct extension
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(video_bytes)
                video_path = tmp.name

            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                audio_path = tmp.name

            # Extract audio using ffmpeg
            process = await asyncio.create_subprocess_exec(
                "ffmpeg", "-i", video_path, "-vn", "-acodec", "libmp3lame",
                "-ar", "16000", "-ac", "1", "-y", audio_path,
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            )
            _, stderr = await process.communicate()

            if process.returncode != 0:
                # Check if video has no audio stream
                stderr_text = stderr.decode() if stderr else ""
                if "does not contain any stream" in stderr_text or "Output file is empty" in stderr_text:
                    return "[Видео без звука]"
                return "[Не удалось извлечь аудио из видео]"

            # Check if audio file has content
            if os.path.getsize(audio_path) < 100:
                return "[Видео без звука]"

            # Read audio and transcribe
            async with aiofiles.open(audio_path, "rb") as f:
                audio_bytes = await f.read()
            return await self.transcribe_audio(audio_bytes)
        except Exception as e:
            return f"[Ошибка транскрипции видео: {e}]"
        finally:
            if video_path and os.path.exists(video_path):
                os.unlink(video_path)
            if audio_path and os.path.exists(audio_path):
                os.unlink(audio_path)


# Singleton instance
transcription_service = TranscriptionService()
