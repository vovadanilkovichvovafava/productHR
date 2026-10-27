"""
External Links Processor Service.

Processes external URLs containing call recordings or transcripts:
- Google Docs (already transcribed)
- Google Drive (audio/video files)
- Direct URLs (audio/video files)
- Fireflies.ai (transcripts)
"""

import os
import re
import logging
import tempfile
import asyncio
import subprocess
import threading
import aiohttp
import aiofiles
from datetime import datetime
from typing import Optional, Tuple
from urllib.parse import urlparse, unquote

from ..config import settings
from ..models.database import CallRecording, CallSource, CallStatus
from .google_docs import google_docs_service
from .call_processor import call_processor

logger = logging.getLogger("hr-analyzer.external_links")

# Track Playwright installation status with thread-safe access
_playwright_installed = False
_playwright_install_attempted = False
_playwright_lock = threading.Lock()


async def ensure_playwright_installed() -> bool:
    """
    Ensure Playwright browsers are installed.
    Auto-installs chromium if not present.
    Returns True if Playwright is ready to use.

    Thread-safe: Uses lock for accessing global state.
    """
    global _playwright_installed, _playwright_install_attempted

    with _playwright_lock:
        if _playwright_installed:
            return True

        if _playwright_install_attempted:
            return False

        _playwright_install_attempted = True

    # Log environment info for debugging
    browsers_path = os.environ.get('PLAYWRIGHT_BROWSERS_PATH', 'not set')
    logger.info(f"Playwright check - PLAYWRIGHT_BROWSERS_PATH: {browsers_path}")

    # Check if chromium is already installed
    try:
        from playwright.async_api import async_playwright
        logger.info("Attempting to launch Playwright chromium...")
        async with async_playwright() as p:
            # Try to launch with --no-sandbox for Docker/Railway environments
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',
                    '--single-process'
                ]
            )
            await browser.close()
            with _playwright_lock:
                _playwright_installed = True
            logger.info("Playwright chromium is ready and working")
            return True
    except RuntimeError as e:
        logger.warning(f"Playwright runtime error: {type(e).__name__}: {e}", exc_info=True)
    except OSError as e:
        logger.warning(f"Playwright OS error: {type(e).__name__}: {e}", exc_info=True)

    # Try to install chromium
    logger.info("Installing Playwright chromium browser...")
    try:
        result = await asyncio.create_subprocess_exec(
            "playwright", "install", "chromium",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(result.communicate(), timeout=300)

        if result.returncode == 0:
            logger.info("Playwright chromium installed successfully")
            with _playwright_lock:
                _playwright_installed = True
            return True
        else:
            logger.error(f"Playwright install failed: {stderr.decode()}")
            return False
    except asyncio.TimeoutError:
        logger.error("Playwright install timed out after 5 minutes")
        return False
    except FileNotFoundError:
        logger.error("Playwright CLI not found - pip install playwright first")
        return False
    except OSError as e:
        logger.error(f"OS error during Playwright install: {e}", exc_info=True)
        return False
    except RuntimeError as e:
        logger.error(f"Runtime error during Playwright install: {e}", exc_info=True)
        return False


class LinkType:
    """Constants for link types."""
    GOOGLE_DOC = "google_doc"
    GOOGLE_SHEET = "google_sheet"
    GOOGLE_FORM = "google_form"
    GOOGLE_DRIVE = "google_drive"
    DIRECT_MEDIA = "direct_media"
    FIREFLIES = "fireflies"
    UNKNOWN = "unknown"


class ExternalLinkProcessor:
    """Processes external links to call recordings or transcripts."""

    # Supported media extensions
    MEDIA_EXTENSIONS = {'.mp3', '.mp4', '.wav', '.m4a', '.webm', '.ogg', '.aac', '.flac', '.wma', '.avi', '.mov', '.mkv'}

    # Google Drive file URL pattern
    GDRIVE_PATTERN = re.compile(r'drive\.google\.com/file/d/([a-zA-Z0-9_-]+)')
    GDRIVE_OPEN_PATTERN = re.compile(r'drive\.google\.com/open\?id=([a-zA-Z0-9_-]+)')

    # Fireflies URL pattern
    FIREFLIES_PATTERN = re.compile(r'app\.fireflies\.ai/view/([^/?]+)')

    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.temp_dir = tempfile.mkdtemp()

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def close(self):
        """Close the session."""
        if self.session and not self.session.closed:
            await self.session.close()

    def detect_link_type(self, url: str) -> str:
        """
        Detect the type of link.

        Returns:
            LinkType constant
        """
        url_lower = url.lower()

        # Fireflies.ai
        if "fireflies.ai" in url_lower:
            return LinkType.FIREFLIES

        # Google Docs
        if "docs.google.com/document" in url_lower:
            return LinkType.GOOGLE_DOC

        # Google Sheets
        if "docs.google.com/spreadsheets" in url_lower:
            return LinkType.GOOGLE_SHEET

        # Google Forms
        if "docs.google.com/forms" in url_lower:
            return LinkType.GOOGLE_FORM

        # Google Drive
        if "drive.google.com" in url_lower:
            return LinkType.GOOGLE_DRIVE

        # Direct media URL
        parsed = urlparse(url)
        ext = os.path.splitext(parsed.path)[1].lower()
        if ext in self.MEDIA_EXTENSIONS:
            return LinkType.DIRECT_MEDIA

        # Check Content-Type header as fallback (will be done during download)
        return LinkType.UNKNOWN

    def _extract_gdrive_file_id(self, url: str) -> Optional[str]:
        """Extract file ID from Google Drive URL."""
        match = self.GDRIVE_PATTERN.search(url)
        if match:
            return match.group(1)

        match = self.GDRIVE_OPEN_PATTERN.search(url)
        if match:
            return match.group(1)

        return None

    def _extract_fireflies_transcript_id(self, url: str) -> Optional[str]:
        """Extract transcript ID from Fireflies URL."""
        match = self.FIREFLIES_PATTERN.search(url)
        if match:
            # URL decode the ID (it may contain special chars like ::)
            return unquote(match.group(1))
        return None

    async def process_url(
        self,
        url: str,
        organization_id: int,
        owner_id: int,
        department_id: Optional[int] = None,
        entity_id: Optional[int] = None,
        title: Optional[str] = None
    ) -> CallRecording:
        """
        Process an external URL and create a CallRecording.

        Args:
            url: External URL (Google Docs, Google Drive, Fireflies, or direct media)
            organization_id: Organization ID
            owner_id: Owner user ID
            department_id: Optional department ID
            entity_id: Optional entity ID to link
            title: Optional custom title

        Returns:
            Created CallRecording
        """
        from ..database import AsyncSessionLocal

        link_type = self.detect_link_type(url)
        logger.info(f"Processing external URL: {url} (type: {link_type})")

        async with AsyncSessionLocal() as db:
            # Create initial CallRecording
            call = CallRecording(
                org_id=organization_id,
                owner_id=owner_id,
                entity_id=entity_id,
                source_url=url,
                title=title or f"External Recording - {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}",
                status=CallStatus.pending,
                created_at=datetime.utcnow()
            )

            if link_type == LinkType.FIREFLIES:
                call.source_type = CallSource.fireflies
                call = await self._process_fireflies(call, url)

            elif link_type == LinkType.GOOGLE_DOC:
                call.source_type = CallSource.google_doc
                call = await self._process_google_doc(call, url)

            elif link_type == LinkType.GOOGLE_SHEET:
                call.source_type = CallSource.google_doc  # Use google_doc as source type
                call = await self._process_google_sheet(call, url)

            elif link_type == LinkType.GOOGLE_FORM:
                call.source_type = CallSource.google_doc  # Use google_doc as source type
                call = await self._process_google_form(call, url)

            elif link_type == LinkType.GOOGLE_DRIVE:
                call.source_type = CallSource.google_drive
                call = await self._process_google_drive(call, url)

            elif link_type == LinkType.DIRECT_MEDIA:
                call.source_type = CallSource.direct_url
                call = await self._process_direct_media(call, url)

            else:
                # Try to detect type by downloading
                call.source_type = CallSource.direct_url
                call = await self._process_unknown(call, url)

            db.add(call)
            try:
                await db.commit()
                await db.refresh(call)
            except Exception as db_error:
                logger.error(f"Database error saving CallRecording: {type(db_error).__name__}: {db_error}", exc_info=True)
                raise

            logger.info(f"Created CallRecording {call.id} from external URL")
            return call

    async def _process_fireflies(self, call: CallRecording, url: str, call_id: Optional[int] = None) -> CallRecording:
        """
        Process Fireflies.ai shared/public transcript URL.
        Uses Playwright to render the page and extract transcript.

        NOTE: This handles PUBLIC shared Fireflies links, not the internal API.
        Fireflies uses client-side rendering, so Playwright is required for reliable extraction.

        Args:
            call: CallRecording object
            url: Fireflies URL
            call_id: Optional call ID for progress tracking (if processing async)
        """
        try:
            transcript_id = self._extract_fireflies_transcript_id(url)
            if not transcript_id:
                call.status = CallStatus.failed
                call.error_message = "Invalid Fireflies URL - could not extract transcript ID"
                return call

            call.status = CallStatus.transcribing
            call.fireflies_transcript_id = transcript_id

            logger.info(f"Fetching Fireflies transcript: {url}")

            transcript_text = None
            title = None
            speakers = []

            # Fireflies uses client-side rendering - Playwright is required
            playwright_ready = await ensure_playwright_installed()

            if playwright_ready:
                try:
                    from playwright.async_api import async_playwright

                    logger.info("Using Playwright for Fireflies extraction")
                    async with async_playwright() as p:
                        # Launch with --no-sandbox for Docker/Railway environments
                        browser = await p.chromium.launch(
                            headless=True,
                            args=[
                                '--no-sandbox',
                                '--disable-setuid-sandbox',
                                '--disable-dev-shm-usage',
                                '--disable-gpu',
                                '--single-process'
                            ]
                        )
                        context = await browser.new_context(
                            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                            viewport={'width': 1920, 'height': 1080},
                            locale='en-US'
                        )
                        page = await context.new_page()

                        # Navigate to the page with longer timeout for heavy JS apps
                        try:
                            await page.goto(url, wait_until='networkidle', timeout=90000)
                        except Exception as nav_err:
                            logger.warning(f"Navigation with networkidle failed: {nav_err}, trying domcontentloaded")
                            await page.goto(url, wait_until='domcontentloaded', timeout=60000)
                            await page.wait_for_timeout(10000)  # Extra wait for JS

                        # Progress: Page loaded
                        if call_id:
                            await self._update_progress(call_id, 30, "Страница загружена, ищем транскрипт...")

                        # Wait for transcript content to load - try multiple selectors
                        transcript_loaded = False
                        wait_selectors = [
                            '[class*="transcript"]',
                            '[class*="Transcript"]',
                            '[class*="sentence"]',
                            '[class*="Sentence"]',
                            '.is-speaker',
                            '[data-testid*="transcript"]',
                        ]

                        for wait_selector in wait_selectors:
                            try:
                                await page.wait_for_selector(wait_selector, timeout=10000)
                                transcript_loaded = True
                                logger.info(f"Found transcript element with selector: {wait_selector}")
                                break
                            except Exception as e:
                                logger.debug(f"Selector {wait_selector} not found: {e}")
                                continue

                        if not transcript_loaded:
                            # Extra wait for dynamic content
                            logger.warning("No transcript selectors found, waiting extra time for JS rendering")
                            await page.wait_for_timeout(15000)

                            # Get page HTML and URL for debugging
                            try:
                                current_url = page.url
                                page_content = await page.content()
                                page_title = await page.title()

                                logger.info(f"Page URL after loading: {current_url}")
                                logger.info(f"Page title: {page_title}")
                                logger.info(f"Page content length: {len(page_content)} chars")

                                # Check for common issues
                                if "sign" in current_url.lower() or "login" in current_url.lower():
                                    logger.error("FIREFLIES ERROR: Page redirected to login - link is NOT publicly shared!")
                                    call.error_message = "Fireflies link requires login. Please share the link publicly: click 'Share' > enable 'Anyone with link can view'"
                                elif "captcha" in page_content.lower() or "verify" in page_title.lower():
                                    logger.error("FIREFLIES ERROR: Captcha or verification detected")
                                    call.error_message = "Fireflies is showing captcha/verification. Try again later or use a different link."
                                elif "not found" in page_title.lower() or "404" in page_content[:1000]:
                                    logger.error("FIREFLIES ERROR: Page not found (404)")
                                    call.error_message = "Fireflies transcript not found. The link may be expired or invalid."
                                elif len(page_content) < 1000:
                                    logger.warning(f"Page content seems too short: {page_content[:500]}")

                                # Save screenshot for debugging
                                try:
                                    screenshot_path = f"/tmp/fireflies_debug_{transcript_id}.png"
                                    await page.screenshot(path=screenshot_path, full_page=True)
                                    logger.info(f"Debug screenshot saved: {screenshot_path}")
                                except Exception as ss_err:
                                    logger.debug(f"Screenshot failed: {ss_err}")

                            except Exception as debug_err:
                                logger.debug(f"Debug info extraction failed: {debug_err}")

                        # First try to extract from __NEXT_DATA__ (most reliable for timestamps)
                        try:
                            page_html = await page.content()
                            import json as json_module
                            next_data_match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', page_html, re.DOTALL)
                            if next_data_match:
                                logger.info("Found __NEXT_DATA__ in Fireflies page via Playwright")
                                next_data = json_module.loads(next_data_match.group(1))
                                page_props = next_data.get('props', {}).get('pageProps', {})
                                logger.info(f"Fireflies pageProps keys: {list(page_props.keys())}")

                                # Log ALL pageProps structure to find speakers/analytics
                                for pp_key in page_props.keys():
                                    pp_val = page_props.get(pp_key)
                                    if isinstance(pp_val, dict):
                                        logger.info(f"pageProps['{pp_key}'] is dict with keys: {list(pp_val.keys())}")
                                    elif isinstance(pp_val, list) and len(pp_val) > 0:
                                        logger.info(f"pageProps['{pp_key}'] is list with {len(pp_val)} items")
                                        if isinstance(pp_val[0], dict):
                                            logger.info(f"  First item keys: {list(pp_val[0].keys())}")

                                transcript_data = page_props.get('transcript', {})

                                if not transcript_data:
                                    logger.warning(f"No transcript in pageProps. Available keys: {list(page_props.keys())}")
                                    # Maybe transcript is under different key
                                    for key in ['meeting', 'data', 'transcriptData', 'content']:
                                        if page_props.get(key):
                                            logger.info(f"Found alternative key '{key}': {type(page_props.get(key))}")

                                # Extract duration from initialMeetingNote if available
                                initial_meeting = page_props.get('initialMeetingNote', {})
                                if initial_meeting:
                                    duration_mins = initial_meeting.get('durationMins')
                                    if duration_mins:
                                        # Convert to float first, then multiply (duration_mins might be string)
                                        call.duration_seconds = int(float(duration_mins) * 60)
                                        logger.info(f"Extracted duration from initialMeetingNote: {duration_mins} mins ({call.duration_seconds} seconds)")

                                    # Also try to get title if not set
                                    meeting_title = initial_meeting.get('title')
                                    if meeting_title and not call.title:
                                        call.title = meeting_title
                                        logger.info(f"Extracted title from initialMeetingNote: {meeting_title}")

                                if transcript_data:
                                    # Log ALL available fields in transcript_data for debugging
                                    logger.info(f"Fireflies transcript_data keys: {list(transcript_data.keys())}")

                                    # Log all top-level data to understand structure
                                    for key in transcript_data.keys():
                                        val = transcript_data.get(key)
                                        if isinstance(val, list) and len(val) > 0:
                                            logger.info(f"Fireflies '{key}' is list with {len(val)} items, first item keys: {list(val[0].keys()) if isinstance(val[0], dict) else type(val[0])}")
                                            if isinstance(val[0], dict):
                                                logger.info(f"Fireflies '{key}' first item sample: {val[0]}")
                                        elif isinstance(val, dict):
                                            logger.info(f"Fireflies '{key}' is dict with keys: {list(val.keys())}")
                                            # Log nested dict contents for important keys
                                            if key in ['analytics', 'speakerAnalytics', 'speaker_analytics', 'speakerTalktime', 'speaker_talktime', 'speakers']:
                                                for nested_key, nested_val in val.items():
                                                    if isinstance(nested_val, list) and nested_val:
                                                        logger.info(f"  '{key}.{nested_key}' list ({len(nested_val)} items): {nested_val[:2]}")
                                                    elif isinstance(nested_val, dict):
                                                        logger.info(f"  '{key}.{nested_key}' dict keys: {list(nested_val.keys())}")
                                                    else:
                                                        logger.info(f"  '{key}.{nested_key}': {nested_val}")
                                        elif val is not None:
                                            logger.info(f"Fireflies '{key}': {type(val).__name__} = {str(val)[:100]}")

                                    title = transcript_data.get('title')
                                    sentences = transcript_data.get('sentences', [])

                                    # Extract participants info (email, name) if available - try more keys
                                    participants = (
                                        transcript_data.get('participants', []) or
                                        transcript_data.get('attendees', []) or
                                        transcript_data.get('meeting_attendees', []) or
                                        transcript_data.get('users', []) or
                                        []
                                    )
                                    if participants:
                                        logger.info(f"Fireflies participants ({len(participants)}): {participants[:3]}...")  # Log first 3

                                    # Also check for speakers list with more info - try more keys
                                    speakers_info = (
                                        transcript_data.get('speakers', []) or
                                        transcript_data.get('speakerList', []) or
                                        transcript_data.get('speaker_list', []) or
                                        transcript_data.get('speakerInfo', []) or
                                        transcript_data.get('speaker_info', []) or
                                        []
                                    )
                                    if speakers_info:
                                        logger.info(f"Fireflies speakers info ({len(speakers_info)}): {speakers_info}")
                                    else:
                                        logger.warning(f"No speakers list found in transcript_data. Available keys: {list(transcript_data.keys())}")

                                    # Try meeting_attendees for participant names (may have display names)
                                    meeting_attendees = transcript_data.get('meeting_attendees', []) or []
                                    if meeting_attendees:
                                        logger.info(f"Fireflies meeting_attendees ({len(meeting_attendees)}): {meeting_attendees}")

                                    # Try analytics for speaker stats (name, duration, word_count)
                                    analytics = transcript_data.get('analytics', {})
                                    analytics_speakers = []
                                    if isinstance(analytics, dict):
                                        # Analytics may have speaker-level data
                                        analytics_speakers = analytics.get('speakers', []) or analytics.get('speaker_analytics', []) or []
                                        if analytics_speakers:
                                            logger.info(f"Fireflies analytics speakers ({len(analytics_speakers)}): {analytics_speakers}")

                                    # Build speaker ID → name mapping
                                    speaker_map = {}

                                    # Source 1: speakers list (usually has id and name)
                                    for sp in speakers_info:
                                        sp_id = sp.get('id') or sp.get('speaker_id') or sp.get('speakerId')
                                        sp_name = sp.get('name') or sp.get('displayName') or sp.get('speaker_name')
                                        sp_email = sp.get('email')
                                        if sp_id is not None:
                                            # Include email in name if available for matching
                                            if sp_name and sp_email:
                                                speaker_map[str(sp_id)] = f"{sp_name} ({sp_email})"
                                            elif sp_name:
                                                speaker_map[str(sp_id)] = sp_name
                                        # Also map by name in case sentence uses name directly
                                        if sp_name:
                                            speaker_map[sp_name] = sp_name if not sp_email else f"{sp_name} ({sp_email})"

                                    # Source 2: analytics speakers (may have name, duration, word_count)
                                    # Also extract speaker statistics from analytics (wpm, talktime, etc.)
                                    fireflies_stats_from_analytics = []
                                    total_talk_time = 0
                                    for asp in analytics_speakers:
                                        asp_id = asp.get('speaker_id') or asp.get('speakerId') or asp.get('id')
                                        asp_name = asp.get('name') or asp.get('displayName')
                                        if asp_id is not None and asp_name and asp_name != 'Speaker':
                                            if str(asp_id) not in speaker_map:
                                                speaker_map[str(asp_id)] = asp_name

                                        # Extract statistics from analytics_speakers
                                        if asp_name and asp_name != 'Speaker':
                                            talk_time = asp.get('talk_time') or asp.get('talkTime') or asp.get('duration') or asp.get('talk_time_seconds') or 0
                                            total_talk_time += talk_time if isinstance(talk_time, (int, float)) else 0

                                    # Calculate percentages and build stats
                                    for asp in analytics_speakers:
                                        asp_name = asp.get('name') or asp.get('displayName')
                                        if asp_name and asp_name != 'Speaker':
                                            talk_time = asp.get('talk_time') or asp.get('talkTime') or asp.get('duration') or asp.get('talk_time_seconds') or 0
                                            word_count = asp.get('word_count') or asp.get('wordCount') or asp.get('words') or 0
                                            wpm = asp.get('wpm') or asp.get('wordsPerMinute') or asp.get('words_per_minute') or 0

                                            # Calculate WPM if not provided but we have word_count and talk_time
                                            if not wpm and word_count and talk_time:
                                                talk_mins = talk_time / 60 if talk_time > 60 else talk_time  # talk_time could be in seconds or minutes
                                                if talk_mins > 0:
                                                    wpm = int(word_count / talk_mins)

                                            # Calculate talktime percentage
                                            talktime_pct = asp.get('percentage') or asp.get('talkTimePercentage') or asp.get('talk_time_percentage') or 0
                                            if not talktime_pct and total_talk_time > 0 and talk_time:
                                                talktime_pct = int(talk_time * 100 / total_talk_time)

                                            if wpm or talktime_pct:
                                                fireflies_stats_from_analytics.append({
                                                    'name': asp_name,
                                                    'wpm': int(wpm) if wpm else None,
                                                    'talktimePercent': int(talktime_pct) if talktime_pct else None,
                                                    'talktimeSeconds': int(talk_time) if talk_time else None
                                                })
                                                logger.info(f"Extracted stats from analytics for '{asp_name}': wpm={wpm}, talktime={talktime_pct}%, talk_time={talk_time}s")

                                    # Store Fireflies speaker stats for later merging
                                    if fireflies_stats_from_analytics:
                                        logger.info(f"Fireflies analytics speaker stats: {fireflies_stats_from_analytics}")
                                        if not hasattr(call, '_fireflies_speaker_stats'):
                                            call._fireflies_speaker_stats = fireflies_stats_from_analytics
                                        else:
                                            # Merge with existing stats
                                            call._fireflies_speaker_stats.extend(fireflies_stats_from_analytics)

                                    # Source 3: meeting_attendees (may have displayName, name, email)
                                    for idx, att in enumerate(meeting_attendees):
                                        if isinstance(att, dict):
                                            att_name = att.get('displayName') or att.get('name') or att.get('email')
                                            att_email = att.get('email')
                                            if att_name:
                                                # Map by index as some systems use index-based speaker IDs
                                                if str(idx) not in speaker_map:
                                                    speaker_map[str(idx)] = f"{att_name} ({att_email})" if att_email and att_email != att_name else att_name

                                    # Also use participants list
                                    for i, p in enumerate(participants):
                                        if isinstance(p, dict):
                                            p_id = p.get('id') or p.get('participantId') or str(i)
                                            p_name = p.get('name') or p.get('displayName') or p.get('email', f'Participant {i+1}')
                                            p_email = p.get('email')
                                            if p_name and p_email and not p_name.endswith(')'):
                                                speaker_map[str(p_id)] = f"{p_name} ({p_email})"
                                            else:
                                                speaker_map[str(p_id)] = p_name
                                        elif isinstance(p, str):
                                            # Simple string participant
                                            speaker_map[str(i)] = p

                                    if speaker_map:
                                        logger.info(f"Built speaker mapping: {speaker_map}")
                                    else:
                                        logger.warning(f"No speaker mapping built - speakers_info empty and no participants found")

                                    # FALLBACK: Try to extract name from meeting title
                                    # Fireflies often uses participant name as meeting title (e.g., "Inna I.", "плюхаев матвей")
                                    if not speaker_map and title:
                                        # Clean title - remove common suffixes
                                        clean_title = title
                                        for suffix in [' - Meeting recording', ' - Запись встречи', ' meeting', ' Meeting', ' call', ' Call']:
                                            if clean_title.endswith(suffix):
                                                clean_title = clean_title[:-len(suffix)]

                                        # If title looks like a name (not too long, no special chars)
                                        if clean_title and len(clean_title) < 50 and not any(c in clean_title for c in ['http', '/', '@', '#']):
                                            # Use title as first speaker name
                                            speaker_map['0'] = clean_title.strip()
                                            logger.info(f"Using meeting title as speaker name: '{clean_title}'")

                                    # Log first sentence structure to understand fields - CRITICAL FOR DEBUGGING
                                    if sentences:
                                        logger.info(f"Fireflies sentence count: {len(sentences)}")
                                        logger.info(f"Fireflies sentence[0] ALL keys: {list(sentences[0].keys())}")
                                        # Log the full first sentence to see all data
                                        first_sentence_safe = {k: str(v)[:200] if isinstance(v, str) else v for k, v in sentences[0].items()}
                                        logger.info(f"Fireflies sentence[0] FULL DATA: {first_sentence_safe}")

                                    if sentences:
                                        lines = []
                                        speakers = []

                                        for s in sentences:
                                            # Get speaker name - try multiple approaches
                                            speaker_name = None

                                            # 1. Try direct name fields (most common)
                                            for name_key in ['speaker_name', 'speakerName', 'name', 'speaker', 'user_name', 'userName', 'participant_name']:
                                                val = s.get(name_key)
                                                if val and val != 'Speaker' and not str(val).startswith('Speaker '):
                                                    speaker_name = val
                                                    break

                                            # 2. Try nested objects (Fireflies sometimes uses this)
                                            if not speaker_name or speaker_name == 'Speaker':
                                                for obj_key in ['user', 'speaker', 'participant', 'attendee']:
                                                    obj = s.get(obj_key)
                                                    if isinstance(obj, dict):
                                                        for name_key in ['name', 'displayName', 'full_name', 'email']:
                                                            val = obj.get(name_key)
                                                            if val and val != 'Speaker':
                                                                speaker_name = val
                                                                break
                                                    if speaker_name and speaker_name != 'Speaker':
                                                        break

                                            # 3. Try to map speaker ID to name from speaker_map
                                            if not speaker_name or speaker_name == 'Speaker':
                                                for id_key in ['speaker_id', 'speakerId', 'speaker_index', 'speakerIndex', 'user_id', 'userId', 'participant_id']:
                                                    sp_id = s.get(id_key)
                                                    if sp_id is not None and str(sp_id) in speaker_map:
                                                        speaker_name = speaker_map[str(sp_id)]
                                                        break

                                            # 4. Use index in speakers_info if available
                                            if not speaker_name or speaker_name == 'Speaker':
                                                sp_idx = s.get('speaker_index') or s.get('speakerIndex') or s.get('speaker_id')
                                                if sp_idx is not None:
                                                    try:
                                                        idx = int(sp_idx)
                                                        if speakers_info and 0 <= idx < len(speakers_info):
                                                            sp_info = speakers_info[idx]
                                                            speaker_name = sp_info.get('name') or sp_info.get('displayName') or sp_info.get('email')
                                                    except (ValueError, TypeError):
                                                        pass

                                            # 5. Check ai_filters or other Fireflies-specific fields
                                            if not speaker_name or speaker_name == 'Speaker':
                                                ai_filters = s.get('ai_filters') or s.get('aiFilters') or {}
                                                if isinstance(ai_filters, dict):
                                                    speaker_name = ai_filters.get('speaker_name') or ai_filters.get('speakerName')

                                            # 6. If still no name, try to use raw "speaker" field even with "Speaker X" format
                                            if not speaker_name or speaker_name == 'Speaker':
                                                raw_speaker = s.get('speaker') or s.get('speakerName') or s.get('speaker_name')
                                                if raw_speaker and raw_speaker != 'Speaker':
                                                    speaker_name = raw_speaker  # Use "Speaker 1", "Speaker 2" etc if that's all we have

                                            # 7. LAST RESORT: Use numbered speaker based on speaker_id
                                            # This ensures we at least distinguish between different speakers
                                            if not speaker_name or speaker_name == 'Speaker':
                                                sp_id = s.get('speaker_id') or s.get('speakerId') or s.get('speaker_index') or s.get('speakerIndex')
                                                if sp_id is not None:
                                                    try:
                                                        sp_num = int(sp_id)
                                                        # Use title for speaker 0 if available, otherwise numbered
                                                        if sp_num == 0 and '0' in speaker_map:
                                                            speaker_name = speaker_map['0']
                                                        else:
                                                            speaker_name = f"Спикер {sp_num + 1}"
                                                    except (ValueError, TypeError):
                                                        speaker_name = f"Спикер ({sp_id})"

                                            speaker_name = speaker_name or 'Спикер'

                                            # Log first few sentences to debug speaker extraction
                                            if len(speakers) < 5:
                                                logger.info(f"Sentence {len(speakers)}: speaker='{speaker_name}', sentence keys={list(s.keys())}, speaker_id={s.get('speaker_id')}, speakerId={s.get('speakerId')}")

                                            text = s.get('text', s.get('raw_text', ''))
                                            if text:
                                                lines.append(f"{speaker_name}: {text}")

                                            # Extract timestamps - try many possible field names
                                            # Note: 0 is a valid timestamp (start of recording), so we use found_start flag
                                            start = None
                                            for key in ["start_time", "startTime", "start", "s", "begin", "from", "timestamp"]:
                                                val = s.get(key)
                                                if val is not None:
                                                    try:
                                                        start = float(val)
                                                        break  # Found a value, don't check other keys
                                                    except (ValueError, TypeError):
                                                        pass
                                            # Also check millisecond variants if not found
                                            if start is None:
                                                for key in ["start_ms", "startMs", "sMs"]:
                                                    val = s.get(key)
                                                    if val is not None:
                                                        try:
                                                            start = float(val) / 1000
                                                            break
                                                        except (ValueError, TypeError):
                                                            pass
                                            start = start if start is not None else 0

                                            end = None
                                            for key in ["end_time", "endTime", "end", "e", "to", "finish"]:
                                                val = s.get(key)
                                                if val is not None:
                                                    try:
                                                        end = float(val)
                                                        break  # Found a value, don't check other keys
                                                    except (ValueError, TypeError):
                                                        pass
                                            # Also check millisecond variants if not found
                                            if end is None:
                                                for key in ["end_ms", "endMs", "eMs"]:
                                                    val = s.get(key)
                                                    if val is not None:
                                                        try:
                                                            end = float(val) / 1000
                                                            break
                                                        except (ValueError, TypeError):
                                                            pass
                                            end = end if end is not None else 0

                                            speakers.append({
                                                "speaker": speaker_name,
                                                "start": start,
                                                "end": end,
                                                "text": text
                                            })

                                        transcript_text = "\n".join(lines)
                                        call.speakers = speakers
                                        # Duration from Fireflies API - check if it's in minutes or seconds
                                        raw_duration = transcript_data.get('duration') or transcript_data.get('duration_seconds') or transcript_data.get('duration_sec')
                                        if raw_duration:
                                            # Fireflies 'duration' is typically in minutes, 'duration_seconds' is in seconds
                                            # If value is small (< 300) and we got it from 'duration' field, it's likely minutes
                                            if transcript_data.get('duration') and not transcript_data.get('duration_seconds') and raw_duration < 300:
                                                call.duration_seconds = int(raw_duration * 60)
                                                logger.info(f"Converted duration from minutes to seconds: {raw_duration} min -> {call.duration_seconds} sec")
                                            else:
                                                call.duration_seconds = int(raw_duration)

                                        # Log if timestamps were found
                                        has_timestamps = any(sp['start'] > 0 or sp['end'] > 0 for sp in speakers)
                                        logger.info(f"Playwright extracted {len(transcript_text)} chars from __NEXT_DATA__ with {len(speakers)} speakers (has_timestamps={has_timestamps})")

                                        # Progress: Transcript extracted
                                        if call_id:
                                            await self._update_progress(call_id, 50, "Транскрипт извлечён, обработка спикеров...")

                        except Exception as next_data_err:
                            logger.debug(f"__NEXT_DATA__ extraction failed: {next_data_err}")

                        # Try to get title (if not already extracted)
                        if not title:
                            try:
                                title_selectors = ['h1', '[class*="MeetingTitle"]', '[class*="title"]', '[class*="Title"]']
                                for ts in title_selectors:
                                    title_el = await page.query_selector(ts)
                                    if title_el:
                                        title = await title_el.text_content()
                                        if title and title.strip() and len(title.strip()) > 3:
                                            title = title.strip()
                                            break
                            except Exception as e:
                                logger.debug(f"Title extraction failed: {e}")

                        # Extract transcript via DOM if __NEXT_DATA__ didn't work
                        transcript_parts = []
                        speaker_data = []

                        if not transcript_text:
                            # Modern Fireflies selectors (2024-2025) - updated for latest UI
                            selectors = [
                                # Primary: Direct transcript text elements
                                '[data-testid="transcript-text"]',
                                '[data-testid*="sentence"]',
                                '[data-testid*="transcript"]',
                                # Sentence-based extraction (best quality)
                                '[class*="SentenceItem"], [class*="sentence-item"]',
                                '[class*="TranscriptSentence"], [class*="transcript-sentence"]',
                                '[class*="TranscriptLine"], [class*="transcript-line"]',
                                # Speaker blocks with text
                                '[class*="SpeakerSegment"], [class*="speaker-segment"]',
                                '[class*="SpeakerBlock"], [class*="speaker-block"]',
                                '.is-speaker',
                                # Generic transcript containers
                                '[class*="transcript"] p',
                                '[class*="transcript"] [class*="text"]',
                                '[class*="Transcript"] [class*="Text"]',
                                # React/Next.js dynamic content
                                '[class*="css-"][class*="text"]',
                                'div[class*="transcript"] > div > div',
                                # Fallback - any sentence-like elements
                                '[class*="sentence"]',
                                '[class*="Sentence"]',
                            ]

                            for selector in selectors:
                                try:
                                    elements = await page.query_selector_all(selector)
                                    if elements and len(elements) > 0:
                                        logger.info(f"Found {len(elements)} elements with selector: {selector}")

                                        # Log first element's HTML structure to understand DOM
                                        if elements:
                                            try:
                                                first_outer = await elements[0].evaluate('el => el.outerHTML.substring(0, 500)')
                                                logger.info(f"First element HTML preview: {first_outer}")
                                                # Also check parent structure
                                                parent_outer = await elements[0].evaluate('el => el.parentElement ? el.parentElement.outerHTML.substring(0, 800) : "no parent"')
                                                logger.info(f"Parent element HTML preview: {parent_outer}")
                                            except Exception as e:
                                                logger.debug(f"Could not log element HTML: {e}")

                                        for el in elements:
                                            # Try multiple approaches to find speaker name
                                            speaker_name = "Speaker"
                                            timestamp_text = None
                                            start_time_sec = 0
                                            end_time_sec = 0

                                            try:
                                                # NEW Approach 0: Use JavaScript to traverse DOM and find speaker
                                                # Fireflies structure: speaker headers precede groups of transcript sentences
                                                # Timestamps are encoded in class names like "cap-time-75.524--76.024"
                                                speaker_info = await el.evaluate('''el => {
                                                    let result = {speaker: null, timestamp: null, startSec: null, endSec: null};

                                                    // FIRST: Extract timestamp from class name pattern cap-time-XX.XXX--YY.YYY
                                                    const checkTimestamp = (element) => {
                                                        const classes = element.className || '';
                                                        const match = classes.match(/cap-time-([\d.]+)--([\d.]+)/);
                                                        if (match) {
                                                            result.startSec = parseFloat(match[1]);
                                                            result.endSec = parseFloat(match[2]);
                                                            return true;
                                                        }
                                                        return false;
                                                    };

                                                    // Check element itself and children for timestamp
                                                    checkTimestamp(el);
                                                    if (!result.startSec) {
                                                        const spans = el.querySelectorAll('span');
                                                        for (const span of spans) {
                                                            if (checkTimestamp(span)) break;
                                                        }
                                                    }

                                                    // SECOND: Find speaker name by looking at DOM structure
                                                    // Traverse up to find ContentPost container, then look for speaker header
                                                    let container = el;
                                                    let contentPost = null;

                                                    // Go up to find ContentPost or similar container
                                                    for (let i = 0; i < 10 && container; i++) {
                                                        // Check for ContentPost data attribute
                                                        if (container.dataset?.sentryElement?.includes('ContentPost') ||
                                                            container.className?.includes('ContentPost') ||
                                                            container.id?.startsWith('content-post')) {
                                                            contentPost = container;
                                                            break;
                                                        }
                                                        // Check for speaker wrapper patterns
                                                        const cls = container.className || '';
                                                        if (cls.includes('speaker-section') || cls.includes('SpeakerSection') ||
                                                            cls.includes('speaker-block') || cls.includes('SpeakerBlock')) {
                                                            contentPost = container;
                                                            break;
                                                        }
                                                        container = container.parentElement;
                                                    }

                                                    // Look for speaker header in various locations
                                                    const findSpeakerName = (element) => {
                                                        if (!element) return null;

                                                        // Try name selectors within element
                                                        const nameSelectors = [
                                                            '[class*="SpeakerName"]', '[class*="speakerName"]', '[class*="speaker-name"]',
                                                            '[class*="UserName"]', '[class*="userName"]', '[class*="user-name"]',
                                                            '[class*="AuthorName"]', '[class*="author-name"]',
                                                            '[class*="ParticipantName"]', '[class*="participant-name"]',
                                                            'a[href*="mailto"]',
                                                            '[class*="avatar"] + *', // Element after avatar often has name
                                                            '[class*="name"]:not([class*="timestamp"])'
                                                        ];

                                                        for (const sel of nameSelectors) {
                                                            try {
                                                                const nameEl = element.querySelector(sel);
                                                                if (nameEl) {
                                                                    const text = nameEl.textContent?.trim();
                                                                    // Valid speaker name: 2-50 chars, not "Speaker", not a timestamp
                                                                    if (text && text.length >= 2 && text.length < 50 &&
                                                                        !text.includes('Speaker') && !/^\d{1,2}:\d{2}/.test(text)) {
                                                                        return text.split('\\n')[0].trim();
                                                                    }
                                                                }
                                                            } catch(e) {}
                                                        }
                                                        return null;
                                                    };

                                                    // Try to find speaker in ContentPost container
                                                    if (contentPost) {
                                                        result.speaker = findSpeakerName(contentPost);

                                                        // If not found, look at preceding siblings of ContentPost
                                                        if (!result.speaker) {
                                                            let sibling = contentPost.previousElementSibling;
                                                            for (let i = 0; i < 5 && sibling && !result.speaker; i++) {
                                                                result.speaker = findSpeakerName(sibling);
                                                                if (!result.speaker) {
                                                                    // Check sibling's text directly
                                                                    const sibText = sibling.textContent?.trim();
                                                                    if (sibText && sibText.length >= 2 && sibText.length < 50 &&
                                                                        !sibText.includes('Speaker') && !/^\d{1,2}:\d{2}/.test(sibText)) {
                                                                        result.speaker = sibText.split('\\n')[0].trim();
                                                                    }
                                                                }
                                                                sibling = sibling.previousElementSibling;
                                                            }
                                                        }
                                                    }

                                                    // Fallback: traverse up and look at each level
                                                    if (!result.speaker) {
                                                        container = el.parentElement;
                                                        for (let i = 0; i < 8 && container && !result.speaker; i++) {
                                                            // Check previous siblings at this level
                                                            let sibling = container.previousElementSibling;
                                                            for (let j = 0; j < 3 && sibling && !result.speaker; j++) {
                                                                result.speaker = findSpeakerName(sibling);
                                                                if (!result.speaker) {
                                                                    // Direct text check
                                                                    const sibText = sibling.textContent?.trim();
                                                                    // Look for patterns like "Name I." or single words that look like names
                                                                    if (sibText && sibText.length >= 2 && sibText.length < 40) {
                                                                        const lines = sibText.split('\\n');
                                                                        for (const line of lines) {
                                                                            const trimmed = line.trim();
                                                                            // Name pattern: not starting with number, not containing typical non-name chars
                                                                            if (trimmed && trimmed.length >= 2 && trimmed.length < 40 &&
                                                                                !/^\d/.test(trimmed) && !trimmed.includes('Speaker') &&
                                                                                !/^\d{1,2}:\d{2}/.test(trimmed) &&
                                                                                !trimmed.includes('WPM') && !trimmed.includes('%')) {
                                                                                result.speaker = trimmed;
                                                                                break;
                                                                            }
                                                                        }
                                                                    }
                                                                }
                                                                sibling = sibling.previousElementSibling;
                                                            }

                                                            // Also check within container's children
                                                            if (!result.speaker) {
                                                                result.speaker = findSpeakerName(container);
                                                            }

                                                            container = container.parentElement;
                                                        }
                                                    }

                                                    // Look for MM:SS timestamp text as fallback
                                                    if (!result.timestamp) {
                                                        const allText = el.closest('[class*="speaker"], [class*="content"]')?.textContent || '';
                                                        const timeMatch = allText.match(/(\d{1,2}:\d{2})/);
                                                        if (timeMatch) {
                                                            result.timestamp = timeMatch[1];
                                                        }
                                                    }

                                                    return result;
                                                }''')

                                                if speaker_info.get('speaker'):
                                                    speaker_name = speaker_info['speaker']
                                                if speaker_info.get('timestamp'):
                                                    timestamp_text = speaker_info['timestamp']
                                                # Use extracted timestamps from class pattern
                                                if speaker_info.get('startSec') is not None:
                                                    start_time_sec = speaker_info['startSec']
                                                if speaker_info.get('endSec') is not None:
                                                    end_time_sec = speaker_info['endSec']

                                                # Approach 1: Look in parent container for speaker name (fallback)
                                                if speaker_name == "Speaker":
                                                    parent = await el.evaluate_handle('el => el.parentElement')
                                                    if parent:
                                                        # Try to find speaker name in parent's children
                                                        for sp_selector in [
                                                            '[class*="speaker"]', '[class*="Speaker"]',
                                                            '[class*="name"]', '[class*="Name"]',
                                                            '[class*="author"]', '[class*="Author"]',
                                                            '[class*="user"]', '[class*="User"]',
                                                            'span[class*="css-"]'  # React dynamic classes
                                                        ]:
                                                            try:
                                                                sp_el = await parent.query_selector(sp_selector)
                                                                if sp_el:
                                                                    sp_text = await sp_el.text_content()
                                                                    if sp_text and sp_text.strip() and len(sp_text.strip()) < 50:
                                                                        sp_text = sp_text.strip()
                                                                        if sp_text != speaker_name and not sp_text.startswith('Speaker'):
                                                                            speaker_name = sp_text
                                                                            break
                                                            except Exception as e:
                                                                logger.warning(f"Speaker name extraction from parent failed: {e}")

                                                        # Also look for timestamp in parent
                                                        if not timestamp_text:
                                                            for time_selector in ['[class*="time"]', '[class*="Time"]', '[class*="timestamp"]', 'time']:
                                                                try:
                                                                    time_el = await parent.query_selector(time_selector)
                                                                    if time_el:
                                                                        timestamp_text = await time_el.text_content()
                                                                        break
                                                                except Exception as e:
                                                                    logger.warning(f"Timestamp extraction with selector {time_selector} failed: {e}")

                                                # Approach 2: Look in previous sibling
                                                if speaker_name == "Speaker":
                                                    try:
                                                        prev_sibling = await el.evaluate_handle('el => el.previousElementSibling')
                                                        if prev_sibling:
                                                            sib_text = await prev_sibling.text_content()
                                                            if sib_text and len(sib_text.strip()) < 50:
                                                                speaker_name = sib_text.strip()
                                                    except Exception as e:
                                                        logger.warning(f"Speaker extraction from previous sibling failed: {e}")

                                                # Approach 3: Direct child elements
                                                if speaker_name == "Speaker":
                                                    speaker_el = await el.query_selector('[class*="speaker"], [class*="Speaker"], [class*="name"], [class*="Name"]')
                                                    if speaker_el:
                                                        speaker_name = await speaker_el.text_content() or "Speaker"

                                                # Approach 4: data attributes
                                                if speaker_name == "Speaker":
                                                    speaker_name = await el.get_attribute('data-speaker') or await el.get_attribute('data-speaker-name') or "Speaker"

                                            except Exception as e:
                                                logger.debug(f"Error extracting speaker: {e}")

                                            # Get text content
                                            text = await el.text_content()
                                            if text and text.strip():
                                                clean_text = text.strip()
                                                # Skip if it's just the speaker name or too short
                                                if len(clean_text) > 2 and clean_text.lower() != speaker_name.lower():
                                                    transcript_parts.append(clean_text)

                                                    # Use pre-extracted timestamps from cap-time class pattern
                                                    start_time = start_time_sec
                                                    end_time = end_time_sec

                                                    # Fallback: try data attributes if class pattern didn't work
                                                    if start_time == 0:
                                                        try:
                                                            start_time = float(await el.get_attribute('data-start') or 0)
                                                            end_time = float(await el.get_attribute('data-end') or 0)
                                                        except Exception as e:
                                                            logger.warning(f"Timestamp extraction from data attributes failed: {e}")

                                                    # Fallback: parse timestamp from text like "01:15"
                                                    if start_time == 0 and timestamp_text:
                                                        try:
                                                            # Parse MM:SS or HH:MM:SS
                                                            parts = timestamp_text.strip().split(':')
                                                            if len(parts) == 2:
                                                                start_time = int(parts[0]) * 60 + int(parts[1])
                                                            elif len(parts) == 3:
                                                                start_time = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
                                                        except Exception as e:
                                                            logger.warning(f"Timestamp parsing from text '{timestamp_text}' failed: {e}")

                                                    speaker_data.append({
                                                        "speaker": speaker_name.strip() if speaker_name else "Speaker",
                                                        "text": clean_text,
                                                        "start": start_time,
                                                        "end": end_time
                                                    })

                                        if transcript_parts:
                                            logger.info(f"Extracted {len(transcript_parts)} transcript parts")
                                            # Log first few speakers and timestamps for debugging
                                            if speaker_data:
                                                logger.info(f"First speaker extracted: {speaker_data[0].get('speaker', 'Unknown')}")
                                                # Log first 3 segments with details
                                                for i, seg in enumerate(speaker_data[:3]):
                                                    logger.info(f"Segment {i}: speaker='{seg.get('speaker')}', start={seg.get('start'):.2f}s, end={seg.get('end'):.2f}s, text='{seg.get('text', '')[:50]}...'")
                                                # Count unique speakers
                                                unique_speakers = set(s.get('speaker') for s in speaker_data)
                                                logger.info(f"Unique speakers found: {unique_speakers}")
                                            break
                                except Exception as sel_err:
                                    logger.debug(f"Selector {selector} failed: {sel_err}")
                                    continue

                            # If no transcript found, try main content as fallback
                            if not transcript_parts:
                                logger.warning("No transcript elements found, trying main content fallback")
                                try:
                                    main_content = await page.query_selector('main, [class*="content"], [class*="Content"], [role="main"]')
                                    if main_content:
                                        text = await main_content.text_content()
                                        if text:
                                            # Filter out short lines and navigation elements
                                            lines = []
                                            for line in text.split('\n'):
                                                line = line.strip()
                                                if line and len(line) > 15 and not any(skip in line.lower() for skip in ['sign in', 'log in', 'cookie', 'privacy', 'terms']):
                                                    lines.append(line)
                                            transcript_parts = lines
                                except Exception as main_err:
                                    logger.debug(f"Main content fallback failed: {main_err}")

                            # Set transcript_text from DOM extraction
                            if transcript_parts:
                                transcript_text = "\n".join(transcript_parts)
                                if speaker_data:
                                    speakers = speaker_data
                                logger.info(f"Playwright extracted {len(transcript_text)} chars, {len(speakers)} speaker segments from Fireflies (DOM)")

                                # Progress: Transcript extracted
                                if call_id:
                                    await self._update_progress(call_id, 50, "Транскрипт извлечён, обработка спикеров...")

                        # Extract duration and speaker statistics from the page
                        try:
                            stats = await page.evaluate('''() => {
                                let result = {
                                    duration: null,
                                    durationSeconds: null,
                                    speakerStats: [],
                                    speakerNames: [],  // Also collect speaker names for mapping
                                    debug: {}
                                };

                                // Try to find duration (format: "MM:SS" or "HH:MM:SS")
                                const durationSelectors = [
                                    '[class*="duration"]', '[class*="Duration"]',
                                    '[class*="time-total"]', '[class*="total-time"]',
                                    '[class*="audio-duration"]', '[class*="video-duration"]',
                                    '[class*="player"] [class*="time"]',
                                    'time', '[datetime]'
                                ];

                                for (const sel of durationSelectors) {
                                    const els = document.querySelectorAll(sel);
                                    for (const el of els) {
                                        const text = el.textContent?.trim();
                                        const match = text?.match(/(\d{1,2}):(\d{2})(?::(\d{2}))?/);
                                        if (match) {
                                            result.duration = text;
                                            if (match[3]) {
                                                result.durationSeconds = parseInt(match[1])*3600 + parseInt(match[2])*60 + parseInt(match[3]);
                                            } else {
                                                result.durationSeconds = parseInt(match[1])*60 + parseInt(match[2]);
                                            }
                                            break;
                                        }
                                    }
                                    if (result.duration) break;
                                }

                                // Try "00:00 / MM:SS" pattern
                                if (!result.duration) {
                                    const allText = document.body.innerText;
                                    const playerMatch = allText.match(/\d{1,2}:\d{2}\s*\/\s*(\d{1,2}):(\d{2})(?::(\d{2}))?/);
                                    if (playerMatch) {
                                        if (playerMatch[3]) {
                                            result.duration = `${playerMatch[1]}:${playerMatch[2]}:${playerMatch[3]}`;
                                            result.durationSeconds = parseInt(playerMatch[1])*3600 + parseInt(playerMatch[2])*60 + parseInt(playerMatch[3]);
                                        } else {
                                            result.duration = `${playerMatch[1]}:${playerMatch[2]}`;
                                            result.durationSeconds = parseInt(playerMatch[1])*60 + parseInt(playerMatch[2]);
                                        }
                                    }
                                }

                                // ENHANCED: Look for speaker names and stats in sidebar/panel
                                // Fireflies shows: Avatar | Name | WPM | TALKTIME%

                                // Strategy 1: Find sidebar with speaker list
                                const sidebarSelectors = [
                                    '[class*="sidebar"]', '[class*="Sidebar"]',
                                    '[class*="panel"]', '[class*="Panel"]',
                                    '[class*="speaker-list"]', '[class*="SpeakerList"]',
                                    '[class*="participants"]', '[class*="Participants"]',
                                    'aside', '[role="complementary"]'
                                ];

                                let sidebar = null;
                                for (const sel of sidebarSelectors) {
                                    sidebar = document.querySelector(sel);
                                    if (sidebar) {
                                        result.debug.sidebarFound = sel;
                                        break;
                                    }
                                }

                                // Strategy 2: Look for speaker stat cards/rows anywhere on page
                                const speakerRowSelectors = [
                                    '[class*="speaker"][class*="row"]',
                                    '[class*="speaker"][class*="card"]',
                                    '[class*="speaker"][class*="item"]',
                                    '[class*="participant"][class*="row"]',
                                    '[class*="talktime"]',
                                    '[class*="Talktime"]',
                                    '[class*="analytics"] [class*="row"]',
                                    '[class*="Analytics"] [class*="row"]'
                                ];

                                // Helper to fix doubled first letter (avatar + name concatenation)
                                const fixDuplicatedFirstChar = (name) => {
                                    if (!name || name.length < 2) return name;
                                    // If first two chars are the same (case-insensitive), remove first one
                                    // Examples: "IInna I." -> "Inna I.", "ММатвей" -> "Матвей"
                                    if (name[0].toLowerCase() === name[1].toLowerCase()) {
                                        return name.substring(1);
                                    }
                                    return name;
                                };

                                for (const sel of speakerRowSelectors) {
                                    const rows = document.querySelectorAll(sel);
                                    if (rows.length > 0) {
                                        result.debug.speakerRowsFound = sel;
                                        for (const row of rows) {
                                            const text = row.textContent?.trim();
                                            // Try various patterns
                                            // "Name 123 WPM 45%" or "Name 123 45%"
                                            let wpmMatch = text?.match(/^([^0-9]+?)\s*(\d+)\s*(?:WPM|wpm|слов\/мин)?\s*(\d+)\s*%/);
                                            if (!wpmMatch) {
                                                // Try "Name | 123 | 45%" with separators
                                                wpmMatch = text?.match(/^([^|0-9]+?)[|]?\s*(\d+)\s*[|]?\s*(\d+)\s*%/);
                                            }
                                            if (wpmMatch) {
                                                let name = wpmMatch[1].trim();
                                                // Fix doubled first character from avatar + name concatenation
                                                name = fixDuplicatedFirstChar(name);
                                                if (name && name.length >= 2 && name.length < 50) {
                                                    result.speakerStats.push({
                                                        name: name,
                                                        wpm: parseInt(wpmMatch[2]),
                                                        talktimePercent: parseInt(wpmMatch[3])
                                                    });
                                                }
                                            }
                                        }
                                        if (result.speakerStats.length > 0) break;
                                    }
                                }

                                // Strategy 3: Look for speaker names near avatars
                                if (result.speakerStats.length === 0) {
                                    const avatarSelectors = [
                                        '[class*="avatar"]', '[class*="Avatar"]',
                                        'img[class*="profile"]', 'img[class*="user"]'
                                    ];

                                    for (const sel of avatarSelectors) {
                                        const avatars = document.querySelectorAll(sel);
                                        for (const avatar of avatars) {
                                            // Look at adjacent elements for name
                                            const parent = avatar.closest('[class*="speaker"], [class*="participant"], [class*="user"], [class*="row"]');
                                            if (parent) {
                                                // Find name element (usually span/div after avatar)
                                                const textNodes = parent.querySelectorAll('span, div, p');
                                                for (const node of textNodes) {
                                                    if (node === avatar || node.contains(avatar)) continue;
                                                    const text = node.textContent?.trim();
                                                    // Check if it looks like a name (not number, not too long)
                                                    if (text && text.length >= 2 && text.length < 40 &&
                                                        !/^\d/.test(text) && !/^\d{1,2}:\d{2}/.test(text) &&
                                                        !text.includes('%') && !text.includes('WPM')) {
                                                        if (!result.speakerNames.includes(text)) {
                                                            result.speakerNames.push(text);
                                                        }
                                                        break;
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }

                                // Strategy 4: Find percentage elements and work backwards
                                if (result.speakerStats.length === 0) {
                                    const processedParents = new Set();

                                    // Iterate through elements looking for percentage text (vanilla JS approach)
                                    document.querySelectorAll('[class*="percent"], [class*="Percent"], span, div').forEach(el => {
                                        const text = el.textContent?.trim();
                                        if (text && /^\d{1,2}%$/.test(text)) {
                                            const parent = el.closest('[class*="speaker"], [class*="row"], [class*="item"], [class*="participant"]');
                                            if (parent && !processedParents.has(parent)) {
                                                processedParents.add(parent);
                                                const fullText = parent.textContent?.trim();
                                                // Extract name (everything before numbers)
                                                const match = fullText?.match(/^([^0-9%]+)/);
                                                if (match) {
                                                    let name = match[1].trim();
                                                    // Fix doubled first character from avatar + name concatenation
                                                    name = fixDuplicatedFirstChar(name);
                                                    const percentMatch = fullText.match(/(\d{1,2})%/);
                                                    const wpmMatch = fullText.match(/(\d{2,3})\s*(?:WPM|wpm|слов)?/);
                                                    if (name && percentMatch) {
                                                        result.speakerStats.push({
                                                            name: name,
                                                            wpm: wpmMatch ? parseInt(wpmMatch[1]) : null,
                                                            talktimePercent: parseInt(percentMatch[1])
                                                        });
                                                    }
                                                }
                                            }
                                        }
                                    });
                                }

                                // Log what we found for debugging
                                result.debug.totalElements = document.querySelectorAll('*').length;
                                result.debug.speakerRelatedElements = document.querySelectorAll('[class*="speaker"], [class*="Speaker"]').length;

                                return result;
                            }''')

                            if stats:
                                # Log debug info
                                if stats.get('debug'):
                                    logger.info(f"Stats extraction debug: {stats['debug']}")

                                if stats.get('duration'):
                                    logger.info(f"Extracted duration: {stats['duration']} ({stats.get('durationSeconds')} seconds)")
                                    call.duration_seconds = stats.get('durationSeconds')

                                if stats.get('speakerStats'):
                                    logger.info(f"Extracted speaker stats ({len(stats['speakerStats'])}): {stats['speakerStats']}")
                                    if not hasattr(call, '_fireflies_speaker_stats'):
                                        call._fireflies_speaker_stats = stats['speakerStats']

                                    # Also use these names to improve speaker mapping in transcript
                                    for sp_stat in stats['speakerStats']:
                                        name = sp_stat.get('name')
                                        if name and name not in ['Speaker', 'Спикер']:
                                            # Add to speakerNames list for potential transcript remapping
                                            if not hasattr(call, '_fireflies_speaker_names'):
                                                call._fireflies_speaker_names = []
                                            if name not in call._fireflies_speaker_names:
                                                call._fireflies_speaker_names.append(name)

                                if stats.get('speakerNames'):
                                    logger.info(f"Extracted speaker names ({len(stats['speakerNames'])}): {stats['speakerNames']}")
                                    if not hasattr(call, '_fireflies_speaker_names'):
                                        call._fireflies_speaker_names = stats['speakerNames']
                                    else:
                                        for name in stats['speakerNames']:
                                            if name not in call._fireflies_speaker_names:
                                                call._fireflies_speaker_names.append(name)

                        except Exception as stats_err:
                            logger.warning(f"Could not extract duration/stats: {stats_err}", exc_info=True)

                        await browser.close()

                except ImportError:
                    logger.warning("Playwright not installed, falling back to HTTP scraping")
                    if call_id:
                        await self._update_progress(call_id, 15, "Playwright недоступен, HTTP fallback...")
                except Exception as e:
                    logger.error(f"Playwright failed: {type(e).__name__}: {e}", exc_info=True)
                    if call_id:
                        await self._update_progress(call_id, 15, "Ошибка Playwright, HTTP fallback...")
            else:
                logger.warning("Playwright not available - Fireflies requires JavaScript rendering for reliable extraction")
                if call_id:
                    await self._update_progress(call_id, 15, "Playwright недоступен, HTTP fallback...")

            # Fallback to HTTP if Playwright didn't work (may not work for JS-rendered content)
            if not transcript_text:
                logger.info("Attempting HTTP fallback for Fireflies transcript extraction")
                if call_id:
                    await self._update_progress(call_id, 20, "HTTP извлечение транскрипта...")
                try:
                    session = await self._get_session()
                    async with session.get(url, headers={
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                        'Accept-Language': 'en-US,en;q=0.5',
                    }, timeout=aiohttp.ClientTimeout(total=30)) as response:
                        if response.status != 200:
                            logger.warning(f"Fireflies HTTP request returned status {response.status}")
                            call.status = CallStatus.failed
                            call.error_message = f"Failed to access Fireflies link: HTTP {response.status}"
                            return call

                        html = await response.text()
                        logger.info(f"Fireflies HTTP response received: {len(html)} chars")

                    # Try __NEXT_DATA__ extraction (Next.js SSR data)
                    import json
                    next_data_match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)

                    if next_data_match:
                        logger.info("Found __NEXT_DATA__ in Fireflies page (HTTP), parsing...")
                        try:
                            next_data = json.loads(next_data_match.group(1))
                            page_props = next_data.get('props', {}).get('pageProps', {})

                            # Log ALL pageProps structure
                            logger.info(f"[HTTP] pageProps keys: {list(page_props.keys())}")
                            for pp_key in page_props.keys():
                                pp_val = page_props.get(pp_key)
                                if isinstance(pp_val, dict):
                                    logger.info(f"[HTTP] pageProps['{pp_key}'] dict keys: {list(pp_val.keys())}")
                                elif isinstance(pp_val, list) and len(pp_val) > 0:
                                    logger.info(f"[HTTP] pageProps['{pp_key}'] list ({len(pp_val)} items)")

                            transcript_data = page_props.get('transcript', {})

                            if transcript_data:
                                # Log ALL keys for debugging (HTTP path)
                                logger.info(f"[HTTP] Fireflies transcript_data keys: {list(transcript_data.keys())}")

                                # Log all top-level data with nested inspection
                                for key in transcript_data.keys():
                                    val = transcript_data.get(key)
                                    if isinstance(val, list) and len(val) > 0:
                                        logger.info(f"[HTTP] Fireflies '{key}' is list with {len(val)} items, first item: {val[0] if isinstance(val[0], dict) else type(val[0])}")
                                    elif isinstance(val, dict):
                                        logger.info(f"[HTTP] Fireflies '{key}' is dict with keys: {list(val.keys())}")
                                        # Log nested for important keys
                                        if key in ['analytics', 'speakerAnalytics', 'speakers']:
                                            for nk, nv in val.items():
                                                if isinstance(nv, list) and nv:
                                                    logger.info(f"[HTTP]   '{key}.{nk}' list: {nv[:2]}")
                                                else:
                                                    logger.info(f"[HTTP]   '{key}.{nk}': {str(nv)[:100]}")

                                title = title or transcript_data.get('title')
                                sentences = transcript_data.get('sentences', [])

                                # Build speaker mapping (same as Playwright version) - try more keys
                                speakers_info = (
                                    transcript_data.get('speakers', []) or
                                    transcript_data.get('speakerList', []) or
                                    transcript_data.get('speaker_list', []) or
                                    []
                                )
                                participants = (
                                    transcript_data.get('participants', []) or
                                    transcript_data.get('attendees', []) or
                                    transcript_data.get('meeting_attendees', []) or
                                    []
                                )

                                # Also get meeting_attendees and analytics
                                meeting_attendees = transcript_data.get('meeting_attendees', []) or []
                                analytics = transcript_data.get('analytics', {})
                                analytics_speakers = []
                                if isinstance(analytics, dict):
                                    analytics_speakers = analytics.get('speakers', []) or analytics.get('speaker_analytics', []) or []

                                logger.info(f"[HTTP] speakers_info count: {len(speakers_info)}, participants count: {len(participants)}, meeting_attendees: {len(meeting_attendees)}, analytics_speakers: {len(analytics_speakers)}")
                                if speakers_info:
                                    logger.info(f"[HTTP] speakers_info: {speakers_info}")
                                if analytics_speakers:
                                    logger.info(f"[HTTP] analytics_speakers: {analytics_speakers}")

                                speaker_map = {}

                                # Source 1: speakers list
                                for sp in speakers_info:
                                    sp_id = sp.get('id') or sp.get('speaker_id') or sp.get('speakerId')
                                    sp_name = sp.get('name') or sp.get('displayName') or sp.get('speaker_name')
                                    sp_email = sp.get('email')
                                    if sp_id is not None:
                                        speaker_map[str(sp_id)] = f"{sp_name} ({sp_email})" if sp_name and sp_email else (sp_name or f"Speaker {sp_id}")
                                    if sp_name:
                                        speaker_map[sp_name] = f"{sp_name} ({sp_email})" if sp_email else sp_name

                                # Source 2: analytics speakers - also extract statistics
                                http_fireflies_stats = []
                                http_total_talk_time = 0
                                for asp in analytics_speakers:
                                    asp_id = asp.get('speaker_id') or asp.get('speakerId') or asp.get('id')
                                    asp_name = asp.get('name') or asp.get('displayName')
                                    if asp_id is not None and asp_name and asp_name != 'Speaker':
                                        if str(asp_id) not in speaker_map:
                                            speaker_map[str(asp_id)] = asp_name

                                    # Extract statistics
                                    if asp_name and asp_name != 'Speaker':
                                        talk_time = asp.get('talk_time') or asp.get('talkTime') or asp.get('duration') or asp.get('talk_time_seconds') or 0
                                        http_total_talk_time += talk_time if isinstance(talk_time, (int, float)) else 0

                                # Calculate percentages and build stats for HTTP path
                                for asp in analytics_speakers:
                                    asp_name = asp.get('name') or asp.get('displayName')
                                    if asp_name and asp_name != 'Speaker':
                                        talk_time = asp.get('talk_time') or asp.get('talkTime') or asp.get('duration') or asp.get('talk_time_seconds') or 0
                                        word_count = asp.get('word_count') or asp.get('wordCount') or asp.get('words') or 0
                                        wpm = asp.get('wpm') or asp.get('wordsPerMinute') or asp.get('words_per_minute') or 0

                                        if not wpm and word_count and talk_time:
                                            talk_mins = talk_time / 60 if talk_time > 60 else talk_time
                                            if talk_mins > 0:
                                                wpm = int(word_count / talk_mins)

                                        talktime_pct = asp.get('percentage') or asp.get('talkTimePercentage') or asp.get('talk_time_percentage') or 0
                                        if not talktime_pct and http_total_talk_time > 0 and talk_time:
                                            talktime_pct = int(talk_time * 100 / http_total_talk_time)

                                        if wpm or talktime_pct:
                                            http_fireflies_stats.append({
                                                'name': asp_name,
                                                'wpm': int(wpm) if wpm else None,
                                                'talktimePercent': int(talktime_pct) if talktime_pct else None,
                                                'talktimeSeconds': int(talk_time) if talk_time else None
                                            })
                                            logger.info(f"[HTTP] Extracted stats from analytics for '{asp_name}': wpm={wpm}, talktime={talktime_pct}%, talk_time={talk_time}s")

                                if http_fireflies_stats:
                                    logger.info(f"[HTTP] Fireflies analytics speaker stats: {http_fireflies_stats}")
                                    if not hasattr(call, '_fireflies_speaker_stats'):
                                        call._fireflies_speaker_stats = http_fireflies_stats
                                    else:
                                        call._fireflies_speaker_stats.extend(http_fireflies_stats)

                                # Source 3: meeting_attendees
                                for idx, att in enumerate(meeting_attendees):
                                    if isinstance(att, dict):
                                        att_name = att.get('displayName') or att.get('name') or att.get('email')
                                        att_email = att.get('email')
                                        if att_name and str(idx) not in speaker_map:
                                            speaker_map[str(idx)] = f"{att_name} ({att_email})" if att_email and att_email != att_name else att_name

                                # Source 4: participants
                                for i, p in enumerate(participants):
                                    if isinstance(p, dict):
                                        p_id = p.get('id') or p.get('participantId') or str(i)
                                        p_name = p.get('name') or p.get('displayName') or p.get('email', f'Participant {i+1}')
                                        p_email = p.get('email')
                                        if str(p_id) not in speaker_map:
                                            speaker_map[str(p_id)] = f"{p_name} ({p_email})" if p_email and not p_name.endswith(')') else p_name
                                    elif isinstance(p, str):
                                        if str(i) not in speaker_map:
                                            speaker_map[str(i)] = p

                                logger.info(f"[HTTP] Built speaker_map: {speaker_map}")

                                # FALLBACK: Try to extract name from meeting title
                                if not speaker_map and title:
                                    clean_title = title
                                    for suffix in [' - Meeting recording', ' - Запись встречи', ' meeting', ' Meeting', ' call', ' Call']:
                                        if clean_title.endswith(suffix):
                                            clean_title = clean_title[:-len(suffix)]
                                    if clean_title and len(clean_title) < 50 and not any(c in clean_title for c in ['http', '/', '@', '#']):
                                        speaker_map['0'] = clean_title.strip()
                                        logger.info(f"[HTTP] Using meeting title as speaker name: '{clean_title}'")

                                if sentences:
                                    # Log first sentence for debugging
                                    logger.info(f"[HTTP] First sentence keys: {list(sentences[0].keys())}")
                                    logger.info(f"[HTTP] First sentence data: {sentences[0]}")
                                    lines = []
                                    speakers = []
                                    for s in sentences:
                                        # Get speaker name with mapping (same logic as Playwright path)
                                        speaker_name = None

                                        # 1. Try direct name fields
                                        for name_key in ['speaker_name', 'speakerName', 'name', 'speaker', 'user_name', 'userName']:
                                            val = s.get(name_key)
                                            if val and val != 'Speaker' and not str(val).startswith('Speaker '):
                                                speaker_name = val
                                                break

                                        # 2. Try nested objects
                                        if not speaker_name or speaker_name == 'Speaker':
                                            for obj_key in ['user', 'speaker', 'participant']:
                                                obj = s.get(obj_key)
                                                if isinstance(obj, dict):
                                                    speaker_name = obj.get('name') or obj.get('displayName') or obj.get('email')
                                                    if speaker_name and speaker_name != 'Speaker':
                                                        break

                                        # 3. Try speaker ID mapping
                                        if not speaker_name or speaker_name == 'Speaker':
                                            for id_key in ['speaker_id', 'speakerId', 'speaker_index', 'speakerIndex']:
                                                sp_id = s.get(id_key)
                                                if sp_id is not None and str(sp_id) in speaker_map:
                                                    speaker_name = speaker_map[str(sp_id)]
                                                    break

                                        # 4. Try index lookup in speakers_info
                                        if not speaker_name or speaker_name == 'Speaker':
                                            sp_idx = s.get('speaker_id') or s.get('speaker_index')
                                            if sp_idx is not None:
                                                try:
                                                    idx = int(sp_idx)
                                                    if speakers_info and 0 <= idx < len(speakers_info):
                                                        sp_info = speakers_info[idx]
                                                        speaker_name = sp_info.get('name') or sp_info.get('displayName')
                                                except (ValueError, TypeError):
                                                    pass

                                        speaker_name = speaker_name or 'Speaker'

                                        text = s.get('text', s.get('raw_text', ''))
                                        if text:
                                            lines.append(f"{speaker_name}: {text}")

                                        # Get timestamps with fallbacks
                                        # Note: 0 is a valid timestamp (start of recording)
                                        start = None
                                        for key in ["start_time", "startTime", "start", "s"]:
                                            val = s.get(key)
                                            if val is not None:
                                                try:
                                                    start = float(val)
                                                    break  # Found a value
                                                except (ValueError, TypeError):
                                                    pass
                                        if start is None and s.get("start_ms"):
                                            try:
                                                start = float(s.get("start_ms")) / 1000
                                            except (ValueError, TypeError):
                                                pass
                                        start = start if start is not None else 0

                                        end = None
                                        for key in ["end_time", "endTime", "end", "e"]:
                                            val = s.get(key)
                                            if val is not None:
                                                try:
                                                    end = float(val)
                                                    break  # Found a value
                                                except (ValueError, TypeError):
                                                    pass
                                        if end is None and s.get("end_ms"):
                                            try:
                                                end = float(s.get("end_ms")) / 1000
                                            except (ValueError, TypeError):
                                                pass
                                        end = end if end is not None else 0

                                        speakers.append({
                                            "speaker": speaker_name,
                                            "start": start,
                                            "end": end,
                                            "text": text
                                        })

                                    transcript_text = "\n".join(lines)
                                    call.speakers = speakers
                                    # Duration from Fireflies API - check if it's in minutes or seconds
                                    raw_duration = transcript_data.get('duration') or transcript_data.get('duration_seconds') or transcript_data.get('duration_sec')
                                    if raw_duration:
                                        # Fireflies 'duration' is typically in minutes, 'duration_seconds' is in seconds
                                        # If value is small (< 300) and we got it from 'duration' field, it's likely minutes
                                        if transcript_data.get('duration') and not transcript_data.get('duration_seconds') and raw_duration < 300:
                                            call.duration_seconds = int(raw_duration * 60)
                                            logger.info(f"HTTP fallback: Converted duration from minutes to seconds: {raw_duration} min -> {call.duration_seconds} sec")
                                        else:
                                            call.duration_seconds = int(raw_duration)

                                    has_timestamps = any(sp['start'] > 0 or sp['end'] > 0 for sp in speakers)
                                    logger.info(f"HTTP fallback extracted {len(transcript_text)} chars from Fireflies (has_timestamps={has_timestamps})")
                                else:
                                    logger.warning("No sentences found in Fireflies transcript_data")
                            else:
                                logger.warning("No transcript_data found in Fireflies pageProps")

                        except json.JSONDecodeError as e:
                            logger.warning(f"Failed to parse __NEXT_DATA__: {e}")
                    else:
                        logger.warning("No __NEXT_DATA__ found in Fireflies page - transcript may require JavaScript rendering")

                except aiohttp.ClientError as e:
                    logger.error(f"HTTP request to Fireflies failed: {e}")
                except asyncio.TimeoutError:
                    logger.error("HTTP request to Fireflies timed out")
                except Exception as e:
                    logger.error(f"Unexpected error in Fireflies HTTP fallback: {type(e).__name__}: {e}")

            # Lower minimum to 20 chars to handle short meetings
            if not transcript_text or len(transcript_text) < 20:
                logger.warning(f"Fireflies transcript too short or empty: {len(transcript_text) if transcript_text else 0} chars")
                call.status = CallStatus.failed
                call.error_message = (
                    "Could not extract transcript from Fireflies. Please check:\n"
                    "1. The link is publicly shared (click 'Share' in Fireflies and enable 'Anyone with link')\n"
                    "2. The meeting has a transcript (not just a scheduled meeting)\n"
                    "3. The link is valid and not expired\n"
                    "If issue persists, check server logs for details."
                )
                return call

            # Update call with extracted data
            if title and (not call.title or call.title.startswith("External Recording") or call.title.startswith("Auto-imported")):
                call.title = title

            call.transcript = transcript_text

            # Save speakers data if extracted
            if speakers and not call.speakers:
                call.speakers = speakers
                logger.info(f"Saved {len(speakers)} speaker segments")

            logger.info(f"Fireflies transcript extracted: {len(transcript_text)} chars")

            # Progress: Starting AI analysis
            if call_id:
                await self._update_progress(call_id, 70, "AI анализ транскрипта...")

            # Run AI analysis
            try:
                call.status = CallStatus.analyzing
                call_processor._init_clients()
                analysis = await call_processor._analyze(call.transcript)
                if analysis:
                    call.summary = analysis.get("summary")
                    call.action_items = analysis.get("action_items")
                    call.key_points = analysis.get("key_points")
                    logger.info("Fireflies AI analysis complete")

                    # Progress: AI analysis complete
                    if call_id:
                        await self._update_progress(call_id, 95, "Сохранение результатов...")
                else:
                    logger.warning("Fireflies AI analysis returned None")
            except Exception as e:
                logger.error(f"Fireflies AI analysis failed: {type(e).__name__}: {e}")
                # Don't fail the whole process - we still have the transcript
                call.summary = None
                call.action_items = None
                call.key_points = None

            call.status = CallStatus.done
            call.processed_at = datetime.utcnow()

            # Calculate speaker stats and participant roles for AI context
            if call.speakers:
                from .call_processor import calculate_speaker_stats, identify_participant_roles
                call.speaker_stats = calculate_speaker_stats(call.speakers, call.duration_seconds)
                logger.info(f"Calculated speaker stats for {len(call.speaker_stats)} speakers")

                # If we have Fireflies speaker stats with WPM and talktime, merge them
                fireflies_stats = getattr(call, '_fireflies_speaker_stats', None)
                if fireflies_stats:
                    logger.info(f"Merging Fireflies speaker stats: {fireflies_stats}")
                    total_duration = call.duration_seconds or 0
                    # Create a new dict to ensure SQLAlchemy detects the change
                    updated_stats = dict(call.speaker_stats)
                    for ff_stat in fireflies_stats:
                        ff_name = ff_stat.get('name', '').lower()
                        # Find matching speaker in calculated stats
                        for speaker_name, stats in updated_stats.items():
                            if ff_name and (ff_name in speaker_name.lower() or speaker_name.lower() in ff_name):
                                # Update with Fireflies data
                                if ff_stat.get('wpm'):
                                    stats['wpm'] = ff_stat['wpm']
                                if ff_stat.get('talktimePercent'):
                                    stats['talktime_percent'] = ff_stat['talktimePercent']
                                # Use talktimeSeconds directly if available, otherwise calculate from percent
                                if ff_stat.get('talktimeSeconds'):
                                    stats['talktime_seconds'] = ff_stat['talktimeSeconds']
                                    logger.info(f"Updated speaker '{speaker_name}' with Fireflies stats: wpm={ff_stat.get('wpm')}, talktime={ff_stat.get('talktimePercent')}% ({stats['talktime_seconds']}s from analytics)")
                                elif ff_stat.get('talktimePercent') and total_duration > 0:
                                    stats['talktime_seconds'] = int(total_duration * ff_stat['talktimePercent'] / 100)
                                    logger.info(f"Updated speaker '{speaker_name}' with Fireflies stats: wpm={ff_stat.get('wpm')}, talktime={ff_stat.get('talktimePercent')}% ({stats['talktime_seconds']}s calculated)")
                                else:
                                    logger.info(f"Updated speaker '{speaker_name}' with Fireflies stats: wpm={ff_stat.get('wpm')}, talktime={ff_stat.get('talktimePercent')}%")
                                break
                    # Reassign to ensure SQLAlchemy marks the column as modified
                    call.speaker_stats = updated_stats
                    logger.info(f"Speaker stats after Fireflies merge: {call.speaker_stats}")

            logger.info(f"Fireflies transcript processed successfully: {len(call.transcript)} chars")

        except Exception as e:
            logger.error(f"Error processing Fireflies: {e}", exc_info=True)
            call.status = CallStatus.failed
            call.error_message = str(e)
            # Update progress to show error state
            if call_id:
                await self._update_progress(call_id, 0, f"Ошибка: {str(e)[:50]}")

        return call

    async def _process_google_doc(self, call: CallRecording, url: str) -> CallRecording:
        """
        Process Google Docs document as a transcript.
        Parses the document text and runs AI analysis.
        """
        try:
            # Parse document using google_docs_service
            result = await google_docs_service.parse_from_url(url)

            if not result or not result.content:
                call.status = CallStatus.failed
                error_msg = result.error if result and result.error else "document may not be public"
                call.error_message = f"Failed to parse Google Doc - {error_msg}"
                return call

            # Store document text as transcript
            call.transcript = result.content
            if result.metadata and result.metadata.get('title'):
                call.title = result.metadata.get('title')

            # Run AI analysis
            call.status = CallStatus.analyzing
            call_processor._init_clients()
            analysis = await call_processor._analyze(call.transcript)
            if analysis:
                call.summary = analysis.get("summary")
                call.action_items = analysis.get("action_items")
                call.key_points = analysis.get("key_points")

            call.status = CallStatus.done
            call.processed_at = datetime.utcnow()

            logger.info(f"Google Doc processed: {len(call.transcript)} chars")

        except Exception as e:
            logger.error(f"Error processing Google Doc: {e}")
            call.status = CallStatus.failed
            call.error_message = str(e)

        return call

    async def _process_google_sheet(self, call: CallRecording, url: str) -> CallRecording:
        """
        Process Google Sheets as text data.
        Exports the spreadsheet as CSV/text and runs AI analysis.
        """
        try:
            # Extract sheet ID
            match = re.search(r'spreadsheets/d/([a-zA-Z0-9_-]+)', url)
            if not match:
                call.status = CallStatus.failed
                call.error_message = "Invalid Google Sheets URL"
                return call

            sheet_id = match.group(1)

            # Try to export as CSV (public sheet)
            export_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"

            session = await self._get_session()
            async with session.get(export_url, allow_redirects=True) as response:
                if response.status != 200:
                    call.status = CallStatus.failed
                    call.error_message = "Failed to export Google Sheet - document may not be public"
                    return call

                text = await response.text()

            if not text.strip():
                call.status = CallStatus.failed
                call.error_message = "Google Sheet is empty"
                return call

            # Store CSV text as transcript
            call.transcript = text
            call.title = call.title or f"Google Sheet - {sheet_id[:8]}"

            # Run AI analysis
            call.status = CallStatus.analyzing
            call_processor._init_clients()
            analysis = await call_processor._analyze(call.transcript)
            if analysis:
                call.summary = analysis.get("summary")
                call.action_items = analysis.get("action_items")
                call.key_points = analysis.get("key_points")

            call.status = CallStatus.done
            call.processed_at = datetime.utcnow()

            logger.info(f"Google Sheet processed: {len(call.transcript)} chars")

        except Exception as e:
            logger.error(f"Error processing Google Sheet: {e}")
            call.status = CallStatus.failed
            call.error_message = str(e)

        return call

    async def _process_google_form(self, call: CallRecording, url: str) -> CallRecording:
        """
        Process Google Forms responses as text data.
        Fetches form data and runs AI analysis.
        """
        try:
            # Extract form ID
            match = re.search(r'forms/d/([a-zA-Z0-9_-]+)', url)
            if not match:
                # Try e/ format for published forms
                match = re.search(r'forms/d/e/([a-zA-Z0-9_-]+)', url)

            if not match:
                call.status = CallStatus.failed
                call.error_message = "Invalid Google Forms URL"
                return call

            form_id = match.group(1)

            # Fetch the form page
            session = await self._get_session()
            async with session.get(url, allow_redirects=True) as response:
                if response.status != 200:
                    call.status = CallStatus.failed
                    call.error_message = "Failed to fetch Google Form - may not be accessible"
                    return call

                html = await response.text()

            # Parse form content
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')

            # Extract text content
            text_parts = []

            # Get form title
            title_elem = soup.find('div', {'class': 'freebirdFormviewerViewHeaderTitle'})
            if title_elem:
                text_parts.append(f"Title: {title_elem.get_text(strip=True)}")

            # Get form description
            desc_elem = soup.find('div', {'class': 'freebirdFormviewerViewHeaderDescription'})
            if desc_elem:
                text_parts.append(f"Description: {desc_elem.get_text(strip=True)}")

            # Get all text from questions
            for elem in soup.find_all(['div', 'span'], string=True):
                text = elem.get_text(strip=True)
                if text and len(text) > 3:
                    text_parts.append(text)

            if not text_parts:
                call.status = CallStatus.failed
                call.error_message = "Could not extract text from Google Form"
                return call

            call.transcript = "\n".join(text_parts)
            call.title = call.title or f"Google Form - {form_id[:8]}"

            # Run AI analysis
            call.status = CallStatus.analyzing
            call_processor._init_clients()
            analysis = await call_processor._analyze(call.transcript)
            if analysis:
                call.summary = analysis.get("summary")
                call.action_items = analysis.get("action_items")
                call.key_points = analysis.get("key_points")

            call.status = CallStatus.done
            call.processed_at = datetime.utcnow()

            logger.info(f"Google Form processed: {len(call.transcript)} chars")

        except Exception as e:
            logger.error(f"Error processing Google Form: {e}")
            call.status = CallStatus.failed
            call.error_message = str(e)

        return call

    async def _process_google_drive(self, call: CallRecording, url: str) -> CallRecording:
        """
        Process file from Google Drive.
        Downloads the file and processes like regular audio.
        """
        try:
            file_id = self._extract_gdrive_file_id(url)
            if not file_id:
                call.status = CallStatus.failed
                call.error_message = "Invalid Google Drive URL"
                return call

            # Download file
            download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
            file_path = await self._download_file(download_url, f"gdrive_{file_id}")

            if not file_path:
                call.status = CallStatus.failed
                call.error_message = "Failed to download file from Google Drive"
                return call

            call.audio_file_path = file_path

            # Let call_processor handle the rest
            return call

        except Exception as e:
            logger.error(f"Error processing Google Drive: {e}")
            call.status = CallStatus.failed
            call.error_message = str(e)

        return call

    async def _process_direct_media(self, call: CallRecording, url: str) -> CallRecording:
        """
        Process direct media URL.
        Downloads the file and sets up for processing.
        """
        try:
            parsed = urlparse(url)
            filename = os.path.basename(parsed.path) or "media_file"

            file_path = await self._download_file(url, filename)

            if not file_path:
                call.status = CallStatus.failed
                call.error_message = "Failed to download media file"
                return call

            call.audio_file_path = file_path

            # The call will be processed by call_processor after save
            return call

        except Exception as e:
            logger.error(f"Error processing direct media: {e}")
            call.status = CallStatus.failed
            call.error_message = str(e)

        return call

    async def _process_unknown(self, call: CallRecording, url: str) -> CallRecording:
        """
        Try to process unknown URL type.
        First try to download and detect content type.
        """
        try:
            session = await self._get_session()
            async with session.head(url, allow_redirects=True) as response:
                content_type = response.headers.get('Content-Type', '')

                # Check if it's audio/video
                if any(t in content_type.lower() for t in ['audio', 'video']):
                    return await self._process_direct_media(call, url)

                # Check if it's text/html (might be a document)
                if 'text' in content_type.lower():
                    call.status = CallStatus.failed
                    call.error_message = "URL appears to be a web page, not a media file. Use Google Docs links for documents."
                    return call

            call.status = CallStatus.failed
            call.error_message = f"Unsupported URL type. Supported: Google Docs, Google Drive, or direct media links."

        except Exception as e:
            logger.error(f"Error processing unknown URL: {e}")
            call.status = CallStatus.failed
            call.error_message = str(e)

        return call

    async def _download_file(self, url: str, filename: str) -> Optional[str]:
        """
        Download file from URL to temp directory.

        Returns:
            Path to downloaded file, or None on failure
        """
        try:
            session = await self._get_session()

            # Get content type to determine extension
            async with session.get(url, allow_redirects=True) as response:
                if response.status != 200:
                    logger.error(f"Download failed: HTTP {response.status}")
                    return None

                content_type = response.headers.get('Content-Type', '')

                # Determine extension
                ext = self._content_type_to_ext(content_type)
                if not ext:
                    ext = os.path.splitext(filename)[1] or '.tmp'

                # Create temp file
                file_path = os.path.join(self.temp_dir, f"{filename}{ext}")

                # Download with non-blocking I/O
                async with aiofiles.open(file_path, 'wb') as f:
                    async for chunk in response.content.iter_chunked(8192):
                        await f.write(chunk)

                file_size = os.path.getsize(file_path)
                logger.info(f"Downloaded file: {file_path} ({file_size} bytes)")

                return file_path

        except Exception as e:
            logger.error(f"Error downloading file: {e}")
            return None

    def _content_type_to_ext(self, content_type: str) -> str:
        """Convert Content-Type to file extension."""
        content_type = content_type.lower().split(';')[0].strip()

        mapping = {
            'audio/mpeg': '.mp3',
            'audio/mp3': '.mp3',
            'audio/wav': '.wav',
            'audio/x-wav': '.wav',
            'audio/mp4': '.m4a',
            'audio/x-m4a': '.m4a',
            'audio/ogg': '.ogg',
            'audio/webm': '.webm',
            'video/mp4': '.mp4',
            'video/webm': '.webm',
            'video/x-matroska': '.mkv',
            'video/quicktime': '.mov',
        }

        return mapping.get(content_type, '')

    async def process_call_audio(self, call_id: int):
        """
        Process downloaded audio file for a call.
        This is called after the CallRecording is saved with audio_file_path.
        """
        await call_processor.process_call(call_id)

    async def create_pending_call(
        self,
        url: str,
        organization_id: int,
        owner_id: int,
        source_type: CallSource,
        entity_id: Optional[int] = None,
        title: Optional[str] = None
    ) -> CallRecording:
        """
        Create a CallRecording with pending status (for async processing).
        Returns immediately so the client gets a fast response.
        """
        from ..database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            call = CallRecording(
                org_id=organization_id,
                owner_id=owner_id,
                entity_id=entity_id,
                source_url=url,
                source_type=source_type,
                title=title or f"External Recording - {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}",
                status=CallStatus.pending,
                created_at=datetime.utcnow()
            )
            db.add(call)
            await db.commit()
            await db.refresh(call)
            logger.info(f"Created pending CallRecording {call.id} for async processing")
            return call

    async def _update_progress(self, call_id: int, progress: int, stage: str, org_id: int = None):
        """Update progress for a call in the database and broadcast via WebSocket."""
        from ..database import AsyncSessionLocal
        from sqlalchemy import update, select
        from ..routes.realtime import broadcast_call_progress

        async with AsyncSessionLocal() as db:
            # Update progress in database
            await db.execute(
                update(CallRecording)
                .where(CallRecording.id == call_id)
                .values(progress=progress, progress_stage=stage)
            )
            await db.commit()
            logger.debug(f"Call {call_id} progress: {progress}% - {stage}")

            # Get org_id if not provided
            if org_id is None:
                result = await db.execute(
                    select(CallRecording.org_id).where(CallRecording.id == call_id)
                )
                org_id = result.scalar_one_or_none()

            # Broadcast progress update via WebSocket
            if org_id:
                try:
                    await broadcast_call_progress(org_id, {
                        "id": call_id,
                        "progress": progress,
                        "progress_stage": stage,
                        "status": "processing"
                    })
                except Exception as e:
                    logger.debug(f"Failed to broadcast progress for call {call_id}: {e}")

    async def process_fireflies_async(self, call_id: int):
        """
        Process Fireflies URL in background.
        Called as a background task after create_pending_call.
        Reports progress at each stage and broadcasts real-time updates via WebSocket.
        """
        from ..database import AsyncSessionLocal
        from sqlalchemy import select
        from ..routes.realtime import broadcast_call_completed, broadcast_call_failed

        logger.info(f"Starting background Fireflies processing for call {call_id}")

        # Stage 1: Starting
        await self._update_progress(call_id, 5, "Запуск обработки...")

        async with AsyncSessionLocal() as db:
            # Get the call record
            result = await db.execute(
                select(CallRecording).where(CallRecording.id == call_id)
            )
            call = result.scalar_one_or_none()

            if not call:
                logger.error(f"Call {call_id} not found for Fireflies processing")
                return

            # Store org_id for broadcasts
            org_id = call.org_id

            if not call.source_url:
                logger.error(f"Call {call_id} has no source_url")
                call.status = CallStatus.failed
                call.error_message = "No source URL"
                call.progress = 0
                call.progress_stage = "Ошибка"
                await db.commit()
                # Broadcast failure
                await self._broadcast_call_failed_safe(org_id, call_id, "No source URL")
                return

            try:
                # Stage 2: Loading page
                await self._update_progress(call_id, 10, "Загрузка страницы Fireflies...", org_id)

                # Process Fireflies with a global timeout (5 minutes max)
                # The _process_fireflies method will update progress internally
                try:
                    call = await asyncio.wait_for(
                        self._process_fireflies(call, call.source_url, call_id),
                        timeout=300  # 5 minutes max
                    )
                except asyncio.TimeoutError:
                    logger.error(f"Fireflies processing timed out for call {call_id}")
                    call.status = CallStatus.failed
                    call.error_message = "Обработка заняла слишком много времени. Попробуйте загрузить транскрипт как текстовый файл."
                    call.progress = 0
                    call.progress_stage = "Таймаут"
                    await db.commit()
                    await self._broadcast_call_failed_safe(org_id, call_id, call.error_message)
                    return

                # Identify participant roles (evaluator, target, others)
                if call.speakers and call.status == CallStatus.done:
                    try:
                        from .call_processor import identify_participant_roles
                        call.participant_roles = await identify_participant_roles(call, db)
                        logger.info(f"Identified participant roles: {call.participant_roles}")
                    except Exception as e:
                        logger.warning(f"Failed to identify participant roles: {e}")

                # Stage 5: Complete
                call.progress = 100
                call.progress_stage = "Готово"

                # Auto-link call to candidate by name if not already linked
                if not call.entity_id and call.status == CallStatus.done:
                    try:
                        from .call_processor import auto_link_call_to_entity
                        await auto_link_call_to_entity(call_id)
                        # Refresh call to get updated entity_id
                        await db.refresh(call)
                    except Exception as e:
                        logger.warning(f"Auto-link failed for Fireflies call {call_id}: {e}")

                # Save the updated call
                await db.commit()
                logger.info(f"Background Fireflies processing complete for call {call_id}")

                # Broadcast completion via WebSocket
                try:
                    await broadcast_call_completed(org_id, {
                        "id": call_id,
                        "title": call.title,
                        "status": "done",
                        "has_summary": bool(call.summary),
                        "has_transcript": bool(call.transcript),
                        "duration_seconds": call.duration_seconds,
                        "speaker_stats": call.speaker_stats,
                        "progress": 100,
                        "progress_stage": "Готово"
                    })
                except Exception as e:
                    logger.debug(f"Failed to broadcast completion for call {call_id}: {e}")

            except Exception as e:
                logger.error(f"Background Fireflies processing failed for call {call_id}: {e}", exc_info=True)
                call.status = CallStatus.failed
                call.error_message = f"Processing error: {str(e)}"
                call.progress = 0
                call.progress_stage = "Ошибка"
                await db.commit()
                # Broadcast failure
                await self._broadcast_call_failed_safe(org_id, call_id, str(e))

    async def _broadcast_call_failed_safe(self, org_id: int, call_id: int, error_message: str):
        """Safely broadcast call failure, catching any exceptions."""
        try:
            from ..routes.realtime import broadcast_call_failed
            await broadcast_call_failed(org_id, {
                "id": call_id,
                "status": "failed",
                "error_message": error_message,
                "progress": 0,
                "progress_stage": "Ошибка"
            })
        except Exception as e:
            logger.debug(f"Failed to broadcast failure for call {call_id}: {e}")


# Singleton instance
external_link_processor = ExternalLinkProcessor()
