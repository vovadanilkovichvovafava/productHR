"""
Call Processor Service - Transcribes audio and analyzes content.
Uses OpenAI Whisper for transcription and Claude for analysis.
"""

import asyncio
import logging
import os
import json
import glob
import tempfile
import shutil
import subprocess
from datetime import datetime
from typing import Optional

import aiofiles
from openai import AsyncOpenAI
from anthropic import AsyncAnthropic, APIError, APIConnectionError
from sqlalchemy import select

from ..config import settings
from ..database import AsyncSessionLocal
from ..models.database import CallRecording, CallStatus

logger = logging.getLogger("hr-analyzer.call_processor")

# OpenAI Whisper has a 25MB file size limit
# Using 24MB as a safe threshold
MAX_FILE_SIZE = 24 * 1024 * 1024  # 24MB in bytes


class CallProcessor:
    """Processes call recordings: transcription + AI analysis."""

    def __init__(self):
        self.openai = None
        self.anthropic = None

    def _init_clients(self):
        """Initialize API clients lazily."""
        if self.openai is None and settings.openai_api_key:
            self.openai = AsyncOpenAI(api_key=settings.openai_api_key)
        if self.anthropic is None and settings.anthropic_api_key:
            self.anthropic = AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def process_call(self, call_id: int):
        """Full processing pipeline for a call recording."""
        self._init_clients()

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(CallRecording).where(CallRecording.id == call_id)
            )
            call = result.scalar_one_or_none()

            if not call:
                logger.error(f"Call {call_id} not found")
                return

            if not call.audio_file_path:
                logger.error(f"Call {call_id} has no audio file")
                call.status = CallStatus.failed
                call.error_message = "No audio file"
                await db.commit()
                return

            try:
                # 1. Convert to WAV if needed
                audio_path = await self._convert_to_wav(call.audio_file_path)

                # 2. Transcribe via Whisper
                call.status = CallStatus.transcribing
                await db.commit()

                transcript = await self._transcribe(audio_path)
                call.transcript = transcript

                # 3. Get audio duration
                duration = await self._get_duration(call.audio_file_path)
                call.duration_seconds = duration

                # 4. AI analysis
                call.status = CallStatus.analyzing
                await db.commit()

                analysis = await self._analyze(transcript)
                call.summary = analysis.get("summary")
                call.action_items = analysis.get("action_items")
                call.key_points = analysis.get("key_points")

                # Use formatted transcript with speaker labels if available
                if analysis.get("formatted_transcript"):
                    call.transcript = analysis.get("formatted_transcript")

                # Done!
                call.status = CallStatus.done
                call.processed_at = datetime.utcnow()
                await db.commit()

                logger.info(f"Call {call_id} processed successfully")

                # Cleanup converted file if different from original
                if audio_path != call.audio_file_path and os.path.exists(audio_path):
                    os.remove(audio_path)

            except (APIError, APIConnectionError) as e:
                logger.error(f"API error processing call {call_id}: {e}", exc_info=True)
                call.status = CallStatus.failed
                call.error_message = f"API error: {str(e)}"
                await db.commit()
            except (OSError, IOError) as e:
                logger.error(f"File I/O error processing call {call_id}: {e}", exc_info=True)
                call.status = CallStatus.failed
                call.error_message = f"File error: {str(e)}"
                await db.commit()
            except ValueError as e:
                logger.error(f"Value error processing call {call_id}: {e}", exc_info=True)
                call.status = CallStatus.failed
                call.error_message = str(e)
                await db.commit()
            except Exception as e:
                logger.error(f"Unexpected error processing call {call_id}: {e}", exc_info=True)
                call.status = CallStatus.failed
                call.error_message = str(e)
                await db.commit()

    async def _convert_to_wav(self, input_path: str) -> str:
        """Convert audio to WAV 16kHz mono for Whisper."""
        if input_path.endswith('.wav'):
            return input_path

        output_path = input_path.rsplit('.', 1)[0] + '_converted.wav'

        cmd = [
            'ffmpeg', '-i', input_path,
            '-ar', '16000',  # 16kHz sample rate
            '-ac', '1',       # mono
            '-y',             # overwrite
            output_path
        ]

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                logger.warning(f"ffmpeg conversion warning: {stderr.decode()}")
                # Return original if conversion fails
                return input_path

            return output_path

        except FileNotFoundError as e:
            logger.warning(f"ffmpeg not found, using original: {e}")
            return input_path
        except (OSError, IOError) as e:
            logger.warning(f"File I/O error during conversion, using original: {e}")
            return input_path

    async def _transcribe(self, audio_path: str) -> str:
        """
        Transcribe audio using OpenAI Whisper API.
        For large files (>24MB), automatically splits into chunks and combines transcripts.
        """
        if not self.openai:
            raise ValueError("OpenAI API key not configured")

        file_size = os.path.getsize(audio_path)

        # If file is small enough, transcribe directly
        if file_size <= MAX_FILE_SIZE:
            return await self._transcribe_single_file(audio_path)

        # Large file: split into chunks and transcribe each
        logger.info(f"Large file detected ({file_size / 1024 / 1024:.1f}MB), splitting into chunks...")
        chunk_files = await self._split_audio_chunks(audio_path)

        try:
            transcripts = []
            for i, chunk_path in enumerate(chunk_files):
                logger.info(f"Transcribing chunk {i + 1}/{len(chunk_files)}...")
                chunk_size = os.path.getsize(chunk_path)

                if chunk_size > MAX_FILE_SIZE:
                    # Re-split this chunk with smaller duration
                    sub_chunks = await self._split_audio_chunks(chunk_path, chunk_duration_sec=300)
                    try:
                        for sub_chunk in sub_chunks:
                            transcript = await self._transcribe_single_file(sub_chunk)
                            transcripts.append(transcript)
                    finally:
                        sub_dir = os.path.dirname(sub_chunks[0]) if sub_chunks else None
                        if sub_dir and os.path.exists(sub_dir):
                            shutil.rmtree(sub_dir)
                else:
                    transcript = await self._transcribe_single_file(chunk_path)
                    transcripts.append(transcript)

            # Combine all transcripts into one
            combined = " ".join(transcripts)
            logger.info(f"Successfully combined {len(transcripts)} transcript chunks")
            return combined

        finally:
            # Clean up chunk files
            chunk_dir = os.path.dirname(chunk_files[0]) if chunk_files else None
            if chunk_dir and os.path.exists(chunk_dir):
                shutil.rmtree(chunk_dir)

    async def _transcribe_single_file(self, audio_path: str) -> str:
        """Transcribe a single audio file (must be under 25MB)."""
        async with aiofiles.open(audio_path, 'rb') as f:
            file_content = await f.read()
        # OpenAI API needs a file-like object with a name attribute
        import io
        file_obj = io.BytesIO(file_content)
        file_obj.name = os.path.basename(audio_path)
        response = await self.openai.audio.transcriptions.create(
            model="whisper-1",
            file=file_obj,
            language="ru"
        )
        return response.text

    async def _split_audio_chunks(self, audio_path: str, chunk_duration_sec: int = 600) -> list:
        """
        Split audio file into chunks using FFmpeg.

        Args:
            audio_path: Path to the audio file
            chunk_duration_sec: Duration of each chunk in seconds (default 10 minutes)

        Returns:
            List of paths to chunk files
        """
        temp_dir = tempfile.mkdtemp(prefix="audio_chunks_")

        _, ext = os.path.splitext(audio_path)
        if not ext:
            ext = ".wav"

        output_pattern = os.path.join(temp_dir, f"chunk_%03d{ext}")

        try:
            process = await asyncio.create_subprocess_exec(
                "ffmpeg", "-i", audio_path,
                "-f", "segment",
                "-segment_time", str(chunk_duration_sec),
                "-c", "copy",
                "-y", output_pattern,
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            )
            _, stderr = await process.communicate()

            if process.returncode != 0:
                stderr_text = stderr.decode() if stderr else ""
                raise Exception(f"FFmpeg split failed: {stderr_text[:200]}")

            chunk_pattern = os.path.join(temp_dir, f"chunk_*{ext}")
            chunk_files = sorted(glob.glob(chunk_pattern))

            if not chunk_files:
                raise Exception("No chunks were created")

            logger.info(f"Split audio into {len(chunk_files)} chunks")
            return chunk_files

        except RuntimeError as e:
            logger.error(f"FFmpeg split runtime error: {e}", exc_info=True)
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            raise
        except (OSError, IOError) as e:
            logger.error(f"File I/O error during audio split: {e}", exc_info=True)
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            raise

    async def _get_duration(self, audio_path: str) -> int:
        """Get audio duration in seconds using ffprobe."""
        cmd = [
            'ffprobe', '-i', audio_path,
            '-show_entries', 'format=duration',
            '-v', 'quiet', '-of', 'csv=p=0'
        ]

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await process.communicate()

            return int(float(stdout.decode().strip()))
        except Exception:
            return 0

    async def analyze_transcript(
        self,
        call_id: int,
        transcript: str,
        speakers: list,
        fireflies_summary: Optional[dict] = None
    ):
        """
        Analyze a transcript from Fireflies (already transcribed with speaker diarization).

        Args:
            call_id: Internal call ID
            transcript: Formatted transcript text
            speakers: List of speaker segments with timestamps
            fireflies_summary: Optional summary from Fireflies
        """
        self._init_clients()

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(CallRecording).where(CallRecording.id == call_id)
            )
            call = result.scalar_one_or_none()

            if not call:
                logger.error(f"Call {call_id} not found for transcript analysis")
                return

            try:
                call.status = CallStatus.analyzing
                call.transcript = transcript
                call.speakers = speakers
                await db.commit()

                # Use Fireflies summary if available, otherwise use Claude
                if fireflies_summary and fireflies_summary.get("overview"):
                    analysis = {
                        "summary": fireflies_summary.get("overview", ""),
                        "key_points": fireflies_summary.get("keywords", []),
                        "action_items": fireflies_summary.get("action_items", [])
                    }
                    logger.info(f"Using Fireflies summary for call {call_id}")
                else:
                    # Fallback to Claude analysis
                    analysis = await self._analyze(transcript)
                    logger.info(f"Used Claude analysis for call {call_id}")

                call.summary = analysis.get("summary")
                call.action_items = analysis.get("action_items")
                call.key_points = analysis.get("key_points")
                call.status = CallStatus.done
                call.processed_at = datetime.utcnow()
                await db.commit()

                logger.info(f"Call {call_id} transcript analyzed successfully")

                # Try to auto-link to candidate after analysis
                await auto_link_call_to_entity(call_id)

            except (APIError, APIConnectionError) as e:
                logger.error(f"API error analyzing transcript for call {call_id}: {e}", exc_info=True)
                call.status = CallStatus.failed
                call.error_message = f"API error: {str(e)}"
                await db.commit()
            except json.JSONDecodeError as e:
                logger.error(f"JSON parsing error for call {call_id}: {e}", exc_info=True)
                call.status = CallStatus.failed
                call.error_message = f"Response parsing error: {str(e)}"
                await db.commit()
            except Exception as e:
                logger.error(f"Unexpected error analyzing transcript for call {call_id}: {e}", exc_info=True)
                call.status = CallStatus.failed
                call.error_message = str(e)
                await db.commit()

    async def _analyze(self, transcript: str) -> dict:
        """Analyze transcript using Claude. Handles long transcripts by chunking."""
        if not self.anthropic:
            logger.warning("Anthropic API key not configured, skipping analysis")
            return {
                "summary": "Analysis not available (API key not configured)",
                "key_points": [],
                "action_items": []
            }

        # For very long transcripts, analyze in chunks and combine
        CHUNK_SIZE = 50000  # Characters per chunk
        MAX_SINGLE_ANALYSIS = 60000  # If less than this, analyze as single piece

        if len(transcript) <= MAX_SINGLE_ANALYSIS:
            # Short transcript - analyze directly
            return await self._analyze_single(transcript)
        else:
            # Long transcript - chunk and combine
            logger.info(f"Long transcript ({len(transcript)} chars), using chunked analysis")
            return await self._analyze_chunked(transcript, CHUNK_SIZE)

    async def _analyze_chunked(self, transcript: str, chunk_size: int) -> dict:
        """Analyze long transcript by splitting into chunks and combining."""
        # Split transcript into chunks
        chunks = []
        for i in range(0, len(transcript), chunk_size):
            chunk = transcript[i:i + chunk_size]
            chunks.append(chunk)

        logger.info(f"Split transcript into {len(chunks)} chunks")

        # Analyze each chunk
        chunk_analyses = []
        for i, chunk in enumerate(chunks):
            logger.info(f"Analyzing chunk {i + 1}/{len(chunks)}")
            chunk_prompt = f"""Проанализируй ЧАСТЬ {i + 1} из {len(chunks)} транскрипта созвона.

ВАЖНО: Это только часть разговора. Извлеки ВСЕ детали из этой части:
- Все обсуждаемые темы и подтемы
- Все упомянутые требования, характеристики, критерии
- Все имена, цифры, примеры
- Все идеи и предложения
- Все договорённости и задачи

ТАКЖЕ: Преобразуй эту часть транскрипта в диалог с указанием спикеров:
- Определи спикеров по контексту (вопросы vs ответы)
- Используй роли: "HR:", "Кандидат:", "Менеджер:", "Спикер 1:", "Спикер 2:"
- Сохрани ВСЕ слова, только добавь метки спикеров

Часть транскрипта:
---
{chunk}
---

Ответь JSON:
{{
  "topics": ["тема 1", "тема 2", ...],
  "details": ["важная деталь 1", "важная деталь 2", ...],
  "key_points": ["ключевой момент 1", "ключевой момент 2", ...],
  "action_items": ["задача 1", "задача 2", ...],
  "profiles": ["если обсуждались роли/кандидаты - все характеристики"],
  "decisions": ["решение 1", "решение 2", ...],
  "open_questions": ["нерешённый вопрос 1", ...],
  "formatted_transcript": "HR: реплика...\\nКандидат: реплика..."
}}"""

            try:
                response = await self.anthropic.messages.create(
                    model=settings.claude_model,
                    max_tokens=8000,
                    messages=[{"role": "user", "content": chunk_prompt}]
                )
                text = response.content[0].text
                start = text.find('{')
                end = text.rfind('}') + 1
                if start != -1 and end > start:
                    chunk_analyses.append(json.loads(text[start:end]))
            except (APIError, APIConnectionError) as e:
                logger.error(f"Chunk {i + 1} API error: {e}", exc_info=True)
            except json.JSONDecodeError as e:
                logger.error(f"Chunk {i + 1} JSON parsing failed: {e}", exc_info=True)

        # Combine all chunk analyses into final analysis
        return await self._combine_chunk_analyses(chunk_analyses, len(transcript))

    async def _combine_chunk_analyses(self, chunk_analyses: list, total_length: int) -> dict:
        """Combine multiple chunk analyses into a final comprehensive analysis."""
        if not chunk_analyses:
            logger.error(f"No chunk analyses available for {total_length} char transcript")
            return {"summary": "Ошибка анализа: не удалось обработать чанки транскрипта. Попробуйте переанализировать позже.", "key_points": [], "action_items": []}

        # Collect all data from chunks
        all_topics = []
        all_details = []
        all_key_points = []
        all_action_items = []
        all_profiles = []
        all_decisions = []
        all_open_questions = []
        all_formatted_transcripts = []

        for analysis in chunk_analyses:
            all_topics.extend(analysis.get("topics", []))
            all_details.extend(analysis.get("details", []))
            all_key_points.extend(analysis.get("key_points", []))
            all_action_items.extend(analysis.get("action_items", []))
            all_profiles.extend(analysis.get("profiles", []))
            all_decisions.extend(analysis.get("decisions", []))
            all_open_questions.extend(analysis.get("open_questions", []))
            if analysis.get("formatted_transcript"):
                all_formatted_transcripts.append(analysis.get("formatted_transcript"))

        # Now create final synthesis
        synthesis_prompt = f"""На основе анализа ВСЕХ частей длинного созвона ({total_length} символов, {len(chunk_analyses)} частей), создай ФИНАЛЬНЫЙ ИСЧЕРПЫВАЮЩИЙ анализ.

Собранные данные из всех частей:

ТЕМЫ: {json.dumps(all_topics, ensure_ascii=False)}

ДЕТАЛИ: {json.dumps(all_details[:100], ensure_ascii=False)}

КЛЮЧЕВЫЕ МОМЕНТЫ: {json.dumps(all_key_points, ensure_ascii=False)}

ЗАДАЧИ: {json.dumps(all_action_items, ensure_ascii=False)}

ПРОФИЛИ/РОЛИ: {json.dumps(all_profiles, ensure_ascii=False)}

РЕШЕНИЯ: {json.dumps(all_decisions, ensure_ascii=False)}

ОТКРЫТЫЕ ВОПРОСЫ: {json.dumps(all_open_questions, ensure_ascii=False)}

Создай ФИНАЛЬНЫЙ структурированный анализ:

## SUMMARY:

**СУТЬ РАЗГОВОРА** (2-3 предложения):
Главная цель и ключевой результат встречи.

**ОСНОВНАЯ ТЕМА:**
Детальное описание главной темы.

**ПОДТЕМЫ** (все что обсуждалось):
Перечисли ВСЕ подтемы с кратким описанием каждой.

**ДЕТАЛЬНЫЕ РАЗБОРЫ ТЕМ:**
Для каждой важной темы/роли/проекта:
- Какие требования/характеристики назывались
- Какие идеи предлагались
- Какие примеры приводились

**К ЧЕМУ ПРИШЛИ (договорённости):**
ВСЕ решения и договорённости.

**К ЧЕМУ НЕ ПРИШЛИ (открытые вопросы):**
Что осталось нерешённым.

**ПОРТРЕТЫ И ПРОФИЛИ:**
Если обсуждались требования к ролям - ВСЕ характеристики:
- Hard skills, Soft skills, Опыт, Личные качества

**ИНСАЙТЫ И ВЫВОДЫ:**
Наблюдения, риски, возможности.

**ОБЩАЯ ОЦЕНКА:**
Продуктивность встречи.

Ответь ТОЛЬКО JSON:
{{
  "summary": "Полное форматированное резюме со ВСЕМИ разделами",
  "key_points": ["15-25 ключевых моментов с деталями"],
  "action_items": ["все задачи"]
}}"""

        try:
            response = await self.anthropic.messages.create(
                model=settings.claude_model,
                max_tokens=16000,
                messages=[{"role": "user", "content": synthesis_prompt}]
            )
            text = response.content[0].text
            start = text.find('{')
            end = text.rfind('}') + 1
            if start != -1 and end > start:
                result = json.loads(text[start:end])
                # Add combined formatted transcript from all chunks
                if all_formatted_transcripts:
                    result["formatted_transcript"] = "\n\n".join(all_formatted_transcripts)
                return result
        except (APIError, APIConnectionError) as e:
            logger.error(f"Synthesis API error: {e}", exc_info=True)
        except json.JSONDecodeError as e:
            logger.error(f"Synthesis JSON parsing failed: {e}", exc_info=True)

        # Fallback: just concatenate key points
        result = {
            "summary": f"Длинный созвон ({total_length} символов). Темы: " + ", ".join(all_topics[:10]),
            "key_points": all_key_points[:25],
            "action_items": all_action_items[:15]
        }
        # Add combined formatted transcript even in fallback
        if all_formatted_transcripts:
            result["formatted_transcript"] = "\n\n".join(all_formatted_transcripts)
        return result

    def _is_already_formatted(self, transcript: str) -> bool:
        """Check if transcript already has timestamps and speaker labels (e.g., from Fireflies)."""
        import re
        # Pattern: [00:00] or [00:00:00] followed by speaker name
        pattern = r'\[\d{2}:\d{2}(:\d{2})?\]\s*[^:]+:'
        # Check first 500 chars for pattern
        matches = re.findall(pattern, transcript[:500])
        return len(matches) >= 2  # At least 2 matches = formatted transcript

    async def _analyze_single(self, transcript: str) -> dict:
        """Analyze a single (short) transcript."""
        # Check if transcript is already formatted (from Fireflies/bot)
        is_formatted = self._is_already_formatted(transcript)

        if is_formatted:
            # Full prompt for already formatted transcripts (Fireflies bot)
            # Same detail level as raw transcripts, but without formatted_transcript request
            prompt = f"""Ты опытный бизнес-аналитик с безупречным вниманием к деталям. Твоя задача - создать ИСЧЕРПЫВАЮЩИЙ анализ созвона.

Транскрипт уже содержит временные метки и имена спикеров - НЕ нужно создавать formatted_transcript.

КРИТИЧЕСКИ ВАЖНО:
- Прочитай ВЕСЬ транскрипт от начала до конца
- Извлеки ВСЕ конкретные детали, идеи, требования, характеристики
- Если обсуждались портреты людей/ролей - опиши ВСЕ упомянутые характеристики
- Не упускай детали из любой части транскрипта (начало, середина, конец)
- Лучше добавить больше деталей, чем упустить важное

Создай анализ по структуре:

## SUMMARY:

**СУТЬ РАЗГОВОРА** (2-3 предложения):
Главная цель и ключевой результат встречи.

**ОСНОВНАЯ ТЕМА:**
Детальное описание главной темы.

**ПОДТЕМЫ** (все что обсуждалось):
Перечисли ВСЕ подтемы с кратким описанием каждой.

**ДЕТАЛЬНЫЕ РАЗБОРЫ ТЕМ:**
Для каждой важной темы/роли/проекта что обсуждались подробно:
- Какие требования/характеристики назывались
- Какие идеи предлагались
- Какие примеры приводились
- Какие критерии определяли

**К ЧЕМУ ПРИШЛИ (договорённости):**
ВСЕ решения и договорённости, даже предварительные.

**К ЧЕМУ НЕ ПРИШЛИ (открытые вопросы):**
Что осталось нерешённым и требует дальнейшего обсуждения.

**ПОРТРЕТЫ И ПРОФИЛИ:**
Если обсуждались требования к кандидатам, ролям, сотрудникам - выпиши ВСЕ характеристики:
- Hard skills
- Soft skills
- Опыт
- Личные качества
- Что должен уметь делать
- Примеры из обсуждения

**ИНСАЙТЫ И ВЫВОДЫ:**
- Скрытые паттерны и наблюдения
- Риски и возможности
- Что читается между строк
- Динамика общения участников

**ОБЩАЯ ОЦЕНКА:**
Продуктивность встречи и рекомендации.

## KEY_POINTS (15-25 ключевых моментов):
Каждый пункт КОНКРЕТНЫЙ с деталями, именами, цифрами, примерами.
Охвати ВСЕ части разговора - начало, середину и конец!

## ACTION_ITEMS:
Все задачи с ответственными и сроками.

Транскрипт:
---
{transcript}
---

Ответь ТОЛЬКО валидным JSON:
{{
  "summary": "Полное форматированное резюме со ВСЕМИ разделами (используй **жирный** для заголовков, \\n для переносов)",
  "key_points": ["Детальный пункт 1", "Детальный пункт 2", ...],
  "action_items": ["Задача: кто, что, когда", ...]
}}"""
            logger.info(f"Using prompt for already formatted transcript ({len(transcript)} chars)")
        else:
            # Full prompt for raw transcripts (uploaded files)
            prompt = f"""Ты опытный бизнес-аналитик с безупречным вниманием к деталям. Твоя задача - создать ИСЧЕРПЫВАЮЩИЙ анализ созвона.

КРИТИЧЕСКИ ВАЖНО:
- Прочитай ВЕСЬ транскрипт от начала до конца
- Извлеки ВСЕ конкретные детали, идеи, требования, характеристики
- Если обсуждались портреты людей/ролей - опиши ВСЕ упомянутые характеристики
- Не упускай детали из любой части транскрипта (начало, середина, конец)
- Лучше добавить больше деталей, чем упустить важное

Создай анализ по структуре:

## SUMMARY:

**СУТЬ РАЗГОВОРА** (2-3 предложения):
Главная цель и ключевой результат встречи.

**ОСНОВНАЯ ТЕМА:**
Детальное описание главной темы.

**ПОДТЕМЫ** (все что обсуждалось):
Перечисли ВСЕ подтемы с кратким описанием каждой.

**ДЕТАЛЬНЫЕ РАЗБОРЫ ТЕМ:**
Для каждой важной темы/роли/проекта что обсуждались подробно:
- Какие требования/характеристики назывались
- Какие идеи предлагались
- Какие примеры приводились
- Какие критерии определяли

**К ЧЕМУ ПРИШЛИ (договорённости):**
ВСЕ решения и договорённости, даже предварительные.

**К ЧЕМУ НЕ ПРИШЛИ (открытые вопросы):**
Что осталось нерешённым и требует дальнейшего обсуждения.

**ПОРТРЕТЫ И ПРОФИЛИ:**
Если обсуждались требования к кандидатам, ролям, сотрудникам - выпиши ВСЕ характеристики:
- Hard skills
- Soft skills
- Опыт
- Личные качества
- Что должен уметь делать
- Примеры из обсуждения

**ИНСАЙТЫ И ВЫВОДЫ:**
- Скрытые паттерны и наблюдения
- Риски и возможности
- Что читается между строк
- Динамика общения участников

**ОБЩАЯ ОЦЕНКА:**
Продуктивность встречи и рекомендации.

## KEY_POINTS (15-25 ключевых моментов):
Каждый пункт КОНКРЕТНЫЙ с деталями, именами, цифрами, примерами.
Охвати ВСЕ части разговора - начало, середину и конец!

## ACTION_ITEMS:
Все задачи с ответственными и сроками.

## FORMATTED_TRANSCRIPT (Транскрипт с разделением по спикерам):
Преобразуй транскрипт в читаемый диалог с указанием спикеров.
ВАЖНО:
- Определи спикеров по контексту (вопросы vs ответы, стиль речи)
- Используй понятные роли: "HR:", "Кандидат:", "Менеджер:", "Спикер 1:", "Спикер 2:" и т.д.
- Каждая реплика с новой строки
- Сохрани ВСЕ слова из оригинала, только добавь метки спикеров
- Формат: "Спикер: текст реплики"

Транскрипт:
---
{transcript}
---

Ответь ТОЛЬКО валидным JSON:
{{
  "summary": "Полное форматированное резюме со ВСЕМИ разделами (используй **жирный** для заголовков, \\n для переносов)",
  "key_points": ["Детальный пункт 1", "Детальный пункт 2", ...],
  "action_items": ["Задача: кто, что, когда", ...],
  "formatted_transcript": "HR: Хорошо, давай перейдем к твоему опыту...\\nКандидат: Да, я сейчас студент...\\nHR: А ты учишься очно?\\nКандидат: Вечерняя форма..."
}}"""

        try:
            response = await self.anthropic.messages.create(
                model=settings.claude_model,
                max_tokens=16000,
                messages=[{"role": "user", "content": prompt}]
            )

            text = response.content[0].text

            # Parse JSON from response
            start = text.find('{')
            end = text.rfind('}') + 1
            if start != -1 and end > start:
                try:
                    result = json.loads(text[start:end])
                    logger.info(f"Successfully parsed Claude analysis response")
                    return result
                except json.JSONDecodeError as json_err:
                    logger.error(f"Failed to parse JSON from Claude response: {json_err}")
                    logger.error(f"Claude response text (first 500 chars): {text[:500]}")
                    # Re-raise to trigger the outer exception handler
                    raise
            else:
                logger.error(f"No JSON found in Claude response. Response (first 500 chars): {text[:500]}")
                raise ValueError("No valid JSON in Claude response")

        except Exception as e:
            logger.error(f"Analysis failed: {e}", exc_info=True)

        # Return error message instead of transcript as fallback
        # This makes it clear that analysis failed rather than showing transcript as summary
        return {
            "summary": "Ошибка анализа: не удалось обработать транскрипт. Попробуйте переанализировать позже.",
            "key_points": [],
            "action_items": []
        }


# Global instance
call_processor = CallProcessor()


async def auto_link_call_to_entity(call_id: int):
    """
    Try to automatically link a call to an entity by matching speaker names
    from the transcript to existing candidates in the same organization.
    Only links if the call is not already linked to an entity.
    """
    from ..models.database import Entity, EntityType
    from sqlalchemy import select, func

    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(CallRecording).where(CallRecording.id == call_id)
            )
            call = result.scalar_one_or_none()

            if not call or call.entity_id or call.status != CallStatus.done:
                return  # Already linked or not done

            # Collect candidate names from transcript/title/speakers
            search_names = set()

            # From speakers data
            if call.speakers:
                for segment in call.speakers:
                    speaker = segment.get('speaker', '') if isinstance(segment, dict) else ''
                    if speaker and speaker.lower() not in ('unknown', 'speaker 1', 'speaker 2', 'спикер 1', 'спикер 2'):
                        search_names.add(speaker.strip())

            # From speaker_stats
            if call.speaker_stats and isinstance(call.speaker_stats, dict):
                for name in call.speaker_stats.keys():
                    if name and name.lower() not in ('unknown',):
                        search_names.add(name.strip())

            # From title
            if call.title:
                # Common patterns: "Interview with John Smith", "Звонок с Иван Петров"
                import re
                title_patterns = [
                    r'(?:with|с|interview|интервью|звонок)\s+(.+)',
                    r'(.+?)\s*[-–—]\s*(?:interview|интервью|звонок|встреча)',
                ]
                for pattern in title_patterns:
                    match = re.search(pattern, call.title, re.IGNORECASE)
                    if match:
                        name = match.group(1).strip()
                        if len(name) > 2 and len(name) < 100:
                            search_names.add(name)

            if not search_names:
                return

            # Search for matching entities
            for name in search_names:
                # Try exact and partial name matching
                name_parts = name.split()

                # Search by full name first
                result = await db.execute(
                    select(Entity).where(
                        Entity.org_id == call.org_id,
                        Entity.type == EntityType.candidate,
                        func.lower(Entity.name).contains(name.lower())
                    ).limit(1)
                )
                entity = result.scalar_one_or_none()

                # If not found by full name and we have first+last, try parts
                if not entity and len(name_parts) >= 2:
                    for part in name_parts:
                        if len(part) < 3:
                            continue
                        result = await db.execute(
                            select(Entity).where(
                                Entity.org_id == call.org_id,
                                Entity.type == EntityType.candidate,
                                func.lower(Entity.name).contains(part.lower())
                            ).limit(5)
                        )
                        candidates = list(result.scalars().all())
                        # If exactly one match - use it
                        if len(candidates) == 1:
                            entity = candidates[0]
                            break

                if entity:
                    call.entity_id = entity.id
                    await db.commit()
                    logger.info(f"Auto-linked call {call_id} to entity {entity.id} ({entity.name}) by name match '{name}'")
                    return

            logger.debug(f"No entity match found for call {call_id} with names: {search_names}")

    except Exception as e:
        logger.warning(f"Auto-link failed for call {call_id}: {e}")


async def process_call_background(call_id: int):
    """Background task wrapper for call processing."""
    await call_processor.process_call(call_id)
    # Try to auto-link to candidate after processing
    await auto_link_call_to_entity(call_id)


# =============================================================================
# SMART CONTEXT FUNCTIONS FOR AI ANALYSIS
# =============================================================================

# Segment duration in seconds (10 minutes)
SEGMENT_DURATION = 600

# Short call threshold - use full transcript if under this (30 minutes)
SHORT_CALL_THRESHOLD = 1800


def calculate_speaker_stats(speakers: list, call_duration_seconds: int = None) -> dict:
    """
    Calculate statistics for each speaker from call segments.

    Args:
        speakers: List of speaker segments [{speaker, start, end, text}, ...]
        call_duration_seconds: Optional total call duration for validation

    Returns:
        Dict mapping speaker name to stats
    """
    if not speakers:
        return {}

    stats = {}
    # Average speaking rate: ~150 words per minute, ~5 characters per word
    # So roughly 750 characters per minute = 12.5 chars per second
    CHARS_PER_SECOND = 12.5

    # Check if timestamps are available
    has_real_timestamps = any(
        (segment.get("start", 0) or 0) > 0 or (segment.get("end", 0) or 0) > 0
        for segment in speakers
    )

    total_chars_all = sum(len(segment.get("text", "") or "") for segment in speakers)

    for segment in speakers:
        speaker = segment.get("speaker", "Unknown")
        start = segment.get("start", 0) or 0
        end = segment.get("end", 0) or 0
        text = segment.get("text", "") or ""

        # Calculate duration - use timestamps if available, otherwise estimate from text length
        if has_real_timestamps:
            duration = max(0, end - start)
        else:
            # Estimate duration based on text length
            duration = len(text) / CHARS_PER_SECOND if text else 0

        # Count words in text
        word_count = len(text.split()) if text else 0

        if speaker not in stats:
            stats[speaker] = {
                "total_seconds": 0,
                "talktime_seconds": 0,  # Alias for UI compatibility
                "segment_count": 0,
                "first_speak_time": start,
                "last_speak_time": end,
                "total_chars": 0,  # Track chars for percentage calculation
                "total_words": 0,  # Track words for WPM calculation
                "estimated": not has_real_timestamps  # Flag if estimated
            }

        stats[speaker]["total_seconds"] += duration
        stats[speaker]["talktime_seconds"] += duration
        stats[speaker]["segment_count"] += 1
        stats[speaker]["total_chars"] += len(text)
        stats[speaker]["total_words"] += word_count
        if has_real_timestamps:
            stats[speaker]["first_speak_time"] = min(stats[speaker]["first_speak_time"], start)
            stats[speaker]["last_speak_time"] = max(stats[speaker]["last_speak_time"], end)

    # Validation: check if timestamps-based calculation is reasonable
    total_seconds_all = sum(s["total_seconds"] for s in stats.values())

    # If we have call duration and calculated time is unreasonably short (<10% of call),
    # fall back to text-based estimation
    min_expected_speaking = (call_duration_seconds or 0) * 0.3  # Expect at least 30% speaking time
    if has_real_timestamps and call_duration_seconds and total_seconds_all < min_expected_speaking:
        logger.warning(f"Timestamp-based speaker stats ({total_seconds_all:.0f}s) too low for {call_duration_seconds}s call, using text estimation")
        # Recalculate using text-based estimation
        for speaker, data in stats.items():
            text_duration = data["total_chars"] / CHARS_PER_SECOND
            data["total_seconds"] = text_duration
            data["talktime_seconds"] = text_duration
            data["estimated"] = True
        total_seconds_all = sum(s["total_seconds"] for s in stats.values())

    # Calculate averages, percentages, and WPM
    total_seconds_all = sum(s["total_seconds"] for s in stats.values())
    for speaker, data in stats.items():
        if data["segment_count"] > 0:
            data["avg_segment_length"] = data["total_seconds"] / data["segment_count"]
        else:
            data["avg_segment_length"] = 0

        # Add percentage of total speaking time
        if total_seconds_all > 0:
            data["percentage"] = round(data["total_seconds"] / total_seconds_all * 100, 1)
            data["talktime_percent"] = int(data["total_seconds"] / total_seconds_all * 100)
        else:
            data["percentage"] = 0
            data["talktime_percent"] = 0

        # Calculate WPM (words per minute)
        if data["total_seconds"] > 0:
            minutes = data["total_seconds"] / 60
            data["wpm"] = int(data["total_words"] / minutes) if minutes > 0 else 0
        else:
            data["wpm"] = 0

    return stats


async def identify_participant_roles(call, db) -> dict:
    """
    Identify roles of call participants.

    Returns:
        {
            "evaluator": {"user_id": 5, "name": "HR Manager", "speaker_name": "..."},
            "target": {"entity_id": 12, "name": "Candidate", "type": "candidate", "speaker_name": "..."},
            "others": [{"name": "...", "speaker_name": "...", "role": "unknown"}]
        }
    """
    from sqlalchemy import select
    from ..models.database import User, Entity

    roles = {
        "evaluator": None,
        "target": None,
        "others": []
    }

    if not call.speakers:
        return roles

    # Get call owner as potential evaluator
    if call.owner_id:
        result = await db.execute(select(User).where(User.id == call.owner_id))
        owner = result.scalar_one_or_none()
        if owner:
            roles["evaluator"] = {
                "user_id": owner.id,
                "name": owner.name,
                "email": owner.email,
                "speaker_name": None
            }

    # Get target entity
    if call.entity_id:
        result = await db.execute(select(Entity).where(Entity.id == call.entity_id))
        entity = result.scalar_one_or_none()
        if entity:
            roles["target"] = {
                "entity_id": entity.id,
                "name": entity.name,
                "type": entity.type.value if entity.type else None,
                "email": entity.email,
                "speaker_name": None
            }

    # Try to match speakers to roles by email
    speaker_stats = calculate_speaker_stats(call.speakers, call.duration_seconds)

    for speaker_name in speaker_stats.keys():
        # Extract email from speaker name if present
        email = None
        if "@" in speaker_name:
            parts = speaker_name.split()
            for part in parts:
                if "@" in part:
                    email = part.strip("()<>[]\"'").lower()
                    break

        matched = False

        # Match evaluator by email
        if roles["evaluator"] and email:
            evaluator_email = (roles["evaluator"].get("email") or "").lower()
            if evaluator_email and evaluator_email == email:
                roles["evaluator"]["speaker_name"] = speaker_name
                matched = True

        # Match target by email
        if not matched and roles["target"] and email:
            target_email = (roles["target"].get("email") or "").lower()
            if target_email and target_email == email:
                roles["target"]["speaker_name"] = speaker_name
                matched = True

        # Unmatched speakers go to others
        if not matched:
            roles["others"].append({
                "name": speaker_name,
                "speaker_name": speaker_name,
                "role": "unknown"
            })

    return roles


async def process_call_for_ai(call, db, force_reprocess: bool = False):
    """
    Process call recording for efficient AI analysis.

    Calculates speaker stats and identifies participant roles.
    """
    # Skip if already processed (unless forced)
    if not force_reprocess and call.speaker_stats and call.participant_roles:
        logger.debug(f"Call {call.id} already processed, skipping")
        return call

    logger.info(f"Processing call {call.id} for AI analysis")

    # Calculate speaker stats
    if call.speakers:
        call.speaker_stats = calculate_speaker_stats(call.speakers, call.duration_seconds)
        logger.debug(f"Calculated stats for {len(call.speaker_stats)} speakers")

    # Identify participant roles
    call.participant_roles = await identify_participant_roles(call, db)

    # Save changes
    db.add(call)
    await db.commit()
    await db.refresh(call)

    return call


def build_smart_context(call, include_full_transcript: bool = False) -> str:
    """
    Build optimized context for AI analysis.

    For short calls (< 30 min): includes full transcript
    For long calls: includes summary + smart truncated transcript + participant info
    """
    parts = []

    # Call metadata
    call_date = call.created_at.strftime('%d.%m.%Y') if call.created_at else "дата неизвестна"
    parts.append(f"### Звонок от {call_date}")

    if call.title:
        parts.append(f"**Название:** {call.title}")

    if call.duration_seconds:
        mins = call.duration_seconds // 60
        secs = call.duration_seconds % 60
        parts.append(f"**Длительность:** {mins}м {secs}с")

    # Participant roles with speaking time
    if call.participant_roles:
        parts.append("\n**Участники:**")

        evaluator = call.participant_roles.get("evaluator")
        if evaluator:
            speaker_name = evaluator.get("speaker_name", "")
            time_str = ""
            if speaker_name and call.speaker_stats:
                stats = call.speaker_stats.get(speaker_name, {})
                total_secs = stats.get("total_seconds", 0)
                if total_secs:
                    time_str = f" (~{int(total_secs // 60)}м)"
            parts.append(f"- 🔑 {evaluator.get('name', 'Неизвестно')} (оценивает){time_str}")

        target = call.participant_roles.get("target")
        if target:
            speaker_name = target.get("speaker_name", "")
            time_str = ""
            if speaker_name and call.speaker_stats:
                stats = call.speaker_stats.get(speaker_name, {})
                total_secs = stats.get("total_seconds", 0)
                if total_secs:
                    time_str = f" (~{int(total_secs // 60)}м)"
            entity_type = target.get("type", "контакт")
            parts.append(f"- 🎯 {target.get('name', 'Неизвестно')} ({entity_type}){time_str}")

        for other in call.participant_roles.get("others", []):
            speaker_name = other.get("speaker_name", "")
            time_str = ""
            if speaker_name and call.speaker_stats:
                stats = call.speaker_stats.get(speaker_name, {})
                total_secs = stats.get("total_seconds", 0)
                if total_secs:
                    time_str = f" (~{int(total_secs // 60)}м)"
            parts.append(f"- 👤 {other.get('name', 'Неизвестно')}{time_str}")

    elif call.speaker_stats:
        # Fallback to speaker stats if no roles identified
        parts.append("\n**Участники звонка:**")
        for speaker, stats in sorted(call.speaker_stats.items(), key=lambda x: -x[1].get("total_seconds", 0)):
            total_secs = stats.get("total_seconds", 0)
            mins = int(total_secs // 60)
            secs = int(total_secs % 60)
            parts.append(f"- {speaker}: ~{mins}м {secs}с")

    # Summary
    if call.summary:
        parts.append(f"\n**Саммари:** {call.summary}")

    # Key points
    if call.key_points:
        parts.append("\n**Ключевые моменты:**")
        for point in call.key_points[:10]:
            parts.append(f"- {point}")

    # Transcript handling
    is_short_call = not call.duration_seconds or call.duration_seconds <= SHORT_CALL_THRESHOLD

    if call.transcript:
        if include_full_transcript or is_short_call:
            # Include full transcript for short calls
            parts.append(f"\n**Транскрипт:**\n{call.transcript}")
        else:
            # For long calls, use smart truncation
            MAX_CHARS = 40000
            if len(call.transcript) > MAX_CHARS:
                first_part = int(MAX_CHARS * 0.6)
                last_part = MAX_CHARS - first_part
                transcript = (
                    call.transcript[:first_part] +
                    f"\n\n... [пропущено ~{(len(call.transcript) - MAX_CHARS) // 1000}k символов] ...\n\n" +
                    call.transcript[-last_part:]
                )
            else:
                transcript = call.transcript
            parts.append(f"\n**Транскрипт:**\n{transcript}")

    return "\n".join(parts)
