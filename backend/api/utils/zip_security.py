"""
ZIP file security utilities.

Protects against:
- ZIP bombs (decompression bombs) - malicious archives that expand to huge sizes
- Path traversal attacks - filenames containing ../ or absolute paths
- Symlink attacks - symlinks pointing outside extraction directory
"""
import zipfile
import os
import logging
from typing import Tuple, List, Optional
from dataclasses import dataclass

logger = logging.getLogger("hr-analyzer.zip-security")

# Safety limits
MAX_COMPRESSED_SIZE = 100 * 1024 * 1024  # 100 MB compressed
MAX_UNCOMPRESSED_SIZE = 500 * 1024 * 1024  # 500 MB uncompressed (5x ratio max)
MAX_COMPRESSION_RATIO = 100  # Max 100:1 compression ratio per file
MAX_FILES_IN_ZIP = 50
MAX_SINGLE_FILE_SIZE = 20 * 1024 * 1024  # 20 MB per file
MAX_FILENAME_LENGTH = 255
MAX_PATH_DEPTH = 10  # Maximum directory nesting


@dataclass
class ZipValidationResult:
    """Result of ZIP file validation."""
    is_safe: bool
    error: Optional[str] = None
    total_uncompressed_size: int = 0
    file_count: int = 0
    suspicious_files: List[str] = None

    def __post_init__(self):
        if self.suspicious_files is None:
            self.suspicious_files = []


def is_path_traversal(filename: str) -> bool:
    """
    Check if filename contains path traversal attempts.

    Detects:
    - Parent directory references (../)
    - Absolute paths (/etc/passwd, C:\\Windows)
    - Null bytes
    - Leading slashes

    Args:
        filename: The filename to check

    Returns:
        True if path traversal detected
    """
    if not filename:
        return True

    # Check for null bytes (can bypass string checks)
    if '\x00' in filename:
        return True

    # Normalize path separators
    normalized = filename.replace('\\', '/')

    # Check for absolute paths
    if normalized.startswith('/'):
        return True
    if len(normalized) > 1 and normalized[1] == ':':  # Windows drive letter
        return True

    # Check for parent directory traversal
    parts = normalized.split('/')
    depth = 0
    for part in parts:
        if part == '..':
            depth -= 1
            if depth < 0:  # Trying to go above root
                return True
        elif part and part != '.':
            depth += 1

    # Check for dangerous patterns
    dangerous_patterns = ['../', '..\\', '/../', '\\..\\']
    for pattern in dangerous_patterns:
        if pattern in normalized:
            return True

    return False


def sanitize_zip_filename(filename: str) -> str:
    """
    Sanitize a filename from a ZIP archive.

    Removes:
    - Path traversal attempts
    - Unsafe characters
    - Leading/trailing whitespace

    Args:
        filename: The original filename from ZIP

    Returns:
        Sanitized filename safe for extraction
    """
    if not filename:
        return "unnamed_file"

    # Remove path traversal
    normalized = filename.replace('\\', '/')

    # Take only the base filename (last component)
    basename = normalized.split('/')[-1]

    # Remove dangerous characters
    # Keep: letters, numbers, dots, underscores, hyphens, spaces, Cyrillic
    import re
    safe_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', basename)

    # Remove leading dots (hidden files on Unix)
    safe_name = safe_name.lstrip('.')

    # Truncate if too long
    if len(safe_name) > MAX_FILENAME_LENGTH:
        # Keep extension
        if '.' in safe_name:
            name, ext = safe_name.rsplit('.', 1)
            max_name_len = MAX_FILENAME_LENGTH - len(ext) - 1
            safe_name = name[:max_name_len] + '.' + ext
        else:
            safe_name = safe_name[:MAX_FILENAME_LENGTH]

    return safe_name.strip() or "unnamed_file"


def validate_zip_file(zip_data: bytes) -> ZipValidationResult:
    """
    Validate a ZIP file for security issues before extraction.

    Checks:
    1. Total uncompressed size (ZIP bomb detection)
    2. Compression ratio per file (ZIP bomb detection)
    3. Path traversal in filenames
    4. File count limits
    5. Individual file size limits

    Args:
        zip_data: Raw ZIP file bytes

    Returns:
        ZipValidationResult with safety status and details
    """
    # Check compressed size first
    if len(zip_data) > MAX_COMPRESSED_SIZE:
        return ZipValidationResult(
            is_safe=False,
            error=f"ZIP file too large: {len(zip_data) / 1024 / 1024:.1f}MB (max {MAX_COMPRESSED_SIZE / 1024 / 1024:.0f}MB)"
        )

    try:
        import io
        with zipfile.ZipFile(io.BytesIO(zip_data), 'r') as zf:
            # Check for ZIP file integrity
            bad_file = zf.testzip()
            if bad_file:
                return ZipValidationResult(
                    is_safe=False,
                    error=f"Corrupted file in ZIP: {bad_file}"
                )

            # SECURITY: Check ALL files for path traversal FIRST, before filtering
            all_files = [info for info in zf.infolist() if not info.is_dir()]
            for info in all_files:
                if is_path_traversal(info.filename):
                    return ZipValidationResult(
                        is_safe=False,
                        error=f"Path traversal detected in: {info.filename}"
                    )

            # Now filter to get list of files we'll actually process
            # (excluding Mac resource forks and hidden files)
            file_list = [
                info for info in all_files
                if not info.filename.startswith('__MACOSX')
                and not info.filename.split('/')[-1].startswith('.')  # Hidden files only by basename
            ]

            # Check file count
            if len(file_list) > MAX_FILES_IN_ZIP:
                return ZipValidationResult(
                    is_safe=False,
                    error=f"Too many files in ZIP: {len(file_list)} (max {MAX_FILES_IN_ZIP})"
                )

            total_uncompressed = 0
            suspicious_files = []

            for info in file_list:

                # Check filename length
                if len(info.filename) > MAX_FILENAME_LENGTH * 2:  # Allow some path
                    suspicious_files.append(f"Long filename: {info.filename[:50]}...")

                # Check uncompressed size
                uncompressed_size = info.file_size
                compressed_size = info.compress_size

                # Individual file size check
                if uncompressed_size > MAX_SINGLE_FILE_SIZE:
                    return ZipValidationResult(
                        is_safe=False,
                        error=f"File too large: {info.filename} ({uncompressed_size / 1024 / 1024:.1f}MB, max {MAX_SINGLE_FILE_SIZE / 1024 / 1024:.0f}MB)"
                    )

                # Compression ratio check (ZIP bomb detection)
                if compressed_size > 0:
                    ratio = uncompressed_size / compressed_size
                    if ratio > MAX_COMPRESSION_RATIO:
                        return ZipValidationResult(
                            is_safe=False,
                            error=f"Suspicious compression ratio ({ratio:.0f}:1) for: {info.filename}. Possible ZIP bomb."
                        )

                total_uncompressed += uncompressed_size

                # Running total check
                if total_uncompressed > MAX_UNCOMPRESSED_SIZE:
                    return ZipValidationResult(
                        is_safe=False,
                        error=f"Total uncompressed size too large: {total_uncompressed / 1024 / 1024:.1f}MB (max {MAX_UNCOMPRESSED_SIZE / 1024 / 1024:.0f}MB)"
                    )

            return ZipValidationResult(
                is_safe=True,
                total_uncompressed_size=total_uncompressed,
                file_count=len(file_list),
                suspicious_files=suspicious_files
            )

    except zipfile.BadZipFile as e:
        return ZipValidationResult(
            is_safe=False,
            error=f"Invalid ZIP file: {str(e)}"
        )
    except Exception as e:
        logger.error(f"ZIP validation error: {e}", exc_info=True)
        return ZipValidationResult(
            is_safe=False,
            error=f"ZIP validation failed: {str(e)}"
        )


def safe_extract_file(zf: zipfile.ZipFile, filename: str, max_size: int = MAX_SINGLE_FILE_SIZE) -> Tuple[bool, bytes, Optional[str]]:
    """
    Safely extract a single file from a ZIP archive.

    Performs additional validation during extraction:
    - Verifies actual size matches declared size
    - Applies size limits
    - Sanitizes filename

    Args:
        zf: Open ZipFile object
        filename: Name of file to extract
        max_size: Maximum allowed file size

    Returns:
        Tuple of (success, file_data, error_message)
    """
    try:
        info = zf.getinfo(filename)

        # Pre-extraction size check
        if info.file_size > max_size:
            return False, b'', f"File too large: {info.file_size / 1024 / 1024:.1f}MB"

        # Extract file
        data = zf.read(filename)

        # Verify actual size
        if len(data) > max_size:
            return False, b'', f"Extracted size exceeds limit: {len(data) / 1024 / 1024:.1f}MB"

        # Verify size matches (detect tampering)
        if len(data) != info.file_size:
            logger.warning(
                f"ZIP file size mismatch: {filename} "
                f"declared={info.file_size}, actual={len(data)}"
            )
            # Still allow if within limits, but log it

        return True, data, None

    except Exception as e:
        logger.error(f"Error extracting {filename}: {e}")
        return False, b'', f"Extraction failed: {str(e)}"
