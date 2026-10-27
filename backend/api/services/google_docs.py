"""
Google Docs parsing service.

Parses Google Docs documents from public URLs.
Supports both public docs and OAuth-authenticated private docs.
"""
import re
import logging
import aiohttp
from typing import Optional, Tuple
from bs4 import BeautifulSoup

from ..config import settings
from .documents import DocumentParseResult

logger = logging.getLogger("hr-analyzer.google_docs")


class GoogleDocsService:
    """Service for parsing Google Docs by URL."""

    # Regex patterns for Google Docs URLs
    DOC_ID_PATTERN = re.compile(
        r'docs\.google\.com/document/d/([a-zA-Z0-9_-]+)'
    )

    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def close(self):
        """Close the aiohttp session."""
        if self.session and not self.session.closed:
            await self.session.close()

    def extract_doc_id(self, url: str) -> Optional[str]:
        """
        Extract document ID from Google Docs URL.

        Supports formats:
        - https://docs.google.com/document/d/DOC_ID/edit
        - https://docs.google.com/document/d/DOC_ID/edit?tab=t.0
        - https://docs.google.com/document/d/DOC_ID/view
        """
        match = self.DOC_ID_PATTERN.search(url)
        if match:
            return match.group(1)
        return None

    def is_google_docs_url(self, url: str) -> bool:
        """Check if URL is a Google Docs document."""
        return bool(self.DOC_ID_PATTERN.search(url))

    async def parse_from_url(self, url: str) -> DocumentParseResult:
        """
        Parse Google Doc from URL.

        Strategy:
        1. Try to export as plain text (works for public docs)
        2. Try to export as HTML and convert to text
        3. Return error if document is private

        Args:
            url: Google Docs URL

        Returns:
            DocumentParseResult with extracted text
        """
        doc_id = self.extract_doc_id(url)
        if not doc_id:
            return DocumentParseResult(
                status="failed",
                error="Invalid Google Docs URL. Expected format: docs.google.com/document/d/{DOC_ID}/...",
                metadata={"url": url}
            )

        logger.info(f"Parsing Google Doc: {doc_id}")

        # Try plain text export first
        result = await self._export_as_text(doc_id)
        if result.status == "parsed":
            return result

        # Try HTML export as fallback
        result = await self._export_as_html(doc_id)
        if result.status == "parsed":
            return result

        # Document is likely private
        return DocumentParseResult(
            status="failed",
            error="Could not access document. Make sure it's shared as 'Anyone with the link can view'.",
            metadata={"doc_id": doc_id, "url": url}
        )

    async def _export_as_text(self, doc_id: str) -> DocumentParseResult:
        """Export Google Doc as plain text."""
        export_url = f"https://docs.google.com/document/d/{doc_id}/export?format=txt"

        try:
            session = await self._get_session()
            async with session.get(export_url, allow_redirects=True) as response:
                if response.status == 200:
                    content_type = response.headers.get('Content-Type', '')

                    # Check if we got actual text content
                    if 'text/plain' in content_type:
                        text = await response.text()

                        if text and len(text.strip()) > 0:
                            logger.info(f"Successfully exported doc {doc_id} as text ({len(text)} chars)")
                            return DocumentParseResult(
                                content=text.strip(),
                                status="parsed",
                                metadata={
                                    "doc_id": doc_id,
                                    "format": "text",
                                    "char_count": len(text)
                                }
                            )

                    # Might be HTML login page
                    return DocumentParseResult(
                        status="failed",
                        error="Document requires authentication",
                        metadata={"doc_id": doc_id}
                    )

                elif response.status == 404:
                    return DocumentParseResult(
                        status="failed",
                        error="Document not found",
                        metadata={"doc_id": doc_id}
                    )

                else:
                    return DocumentParseResult(
                        status="failed",
                        error=f"HTTP {response.status}: Could not access document",
                        metadata={"doc_id": doc_id, "status": response.status}
                    )

        except aiohttp.ClientError as e:
            logger.error(f"Network error fetching doc {doc_id}: {e}")
            return DocumentParseResult(
                status="failed",
                error=f"Network error: {str(e)}",
                metadata={"doc_id": doc_id}
            )

    async def _export_as_html(self, doc_id: str) -> DocumentParseResult:
        """Export Google Doc as HTML and convert to text."""
        export_url = f"https://docs.google.com/document/d/{doc_id}/export?format=html"

        try:
            session = await self._get_session()
            async with session.get(export_url, allow_redirects=True) as response:
                if response.status == 200:
                    html = await response.text()

                    # Check if it's actual document HTML or a login page
                    if '<html' in html.lower() and 'accounts.google.com' not in html:
                        soup = BeautifulSoup(html, 'html.parser')

                        # Remove script and style elements
                        for element in soup(['script', 'style', 'head', 'meta']):
                            element.decompose()

                        # Get text content
                        text = soup.get_text(separator='\n', strip=True)

                        if text and len(text.strip()) > 0:
                            logger.info(f"Successfully exported doc {doc_id} as HTML ({len(text)} chars)")
                            return DocumentParseResult(
                                content=text.strip(),
                                status="parsed",
                                metadata={
                                    "doc_id": doc_id,
                                    "format": "html",
                                    "char_count": len(text)
                                }
                            )

                return DocumentParseResult(
                    status="failed",
                    error="Could not extract text from document",
                    metadata={"doc_id": doc_id}
                )

        except aiohttp.ClientError as e:
            logger.error(f"Network error fetching doc {doc_id}: {e}")
            return DocumentParseResult(
                status="failed",
                error=f"Network error: {str(e)}",
                metadata={"doc_id": doc_id}
            )


# Singleton instance
google_docs_service = GoogleDocsService()
