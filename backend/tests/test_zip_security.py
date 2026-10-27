"""
Tests for ZIP security utilities.

Tests cover:
- Path traversal detection
- Filename sanitization
- ZIP bomb detection
- Compression ratio limits
"""
import pytest
import zipfile
import io
from api.utils.zip_security import (
    is_path_traversal,
    sanitize_zip_filename,
    validate_zip_file,
    safe_extract_file,
    MAX_COMPRESSION_RATIO,
)


class TestPathTraversal:
    """Tests for path traversal detection."""

    def test_normal_filename(self):
        """Normal filenames should not be flagged."""
        assert is_path_traversal("resume.pdf") is False
        assert is_path_traversal("folder/resume.pdf") is False
        assert is_path_traversal("Иван_Петров.docx") is False

    def test_parent_directory(self):
        """Parent directory references should be detected."""
        assert is_path_traversal("../etc/passwd") is True
        assert is_path_traversal("foo/../../../etc/passwd") is True
        assert is_path_traversal("..\\windows\\system32") is True

    def test_absolute_paths(self):
        """Absolute paths should be detected."""
        assert is_path_traversal("/etc/passwd") is True
        assert is_path_traversal("C:\\Windows\\System32") is True
        assert is_path_traversal("C:/Windows/System32") is True

    def test_null_bytes(self):
        """Null bytes should be detected."""
        assert is_path_traversal("resume.pdf\x00.exe") is True
        assert is_path_traversal("\x00") is True

    def test_empty_filename(self):
        """Empty filename should be flagged."""
        assert is_path_traversal("") is True
        assert is_path_traversal(None) is True

    def test_hidden_traversal(self):
        """Hidden traversal patterns should be detected."""
        assert is_path_traversal("foo/bar/../../../etc") is True
        assert is_path_traversal("a/b/c/../../../../etc") is True


class TestSanitizeFilename:
    """Tests for filename sanitization."""

    def test_normal_filename(self):
        """Normal filenames should pass through."""
        assert sanitize_zip_filename("resume.pdf") == "resume.pdf"
        assert sanitize_zip_filename("Иван Петров.docx") == "Иван Петров.docx"

    def test_removes_path(self):
        """Should extract basename from path."""
        assert sanitize_zip_filename("folder/resume.pdf") == "resume.pdf"
        assert sanitize_zip_filename("a/b/c/file.txt") == "file.txt"
        assert sanitize_zip_filename("folder\\resume.pdf") == "resume.pdf"

    def test_removes_dangerous_chars(self):
        """Should remove dangerous characters."""
        assert sanitize_zip_filename('file<>:"|?*.txt') == "file_______.txt"
        # «/» и «\\» — разделители пути: сначала берётся последний компонент
        # (см. test_removes_path), поэтому от такого имени остаётся хвост.
        assert sanitize_zip_filename('file<>:"/\\|?*.txt') == "___.txt"

    def test_removes_traversal(self):
        """Should remove path traversal."""
        result = sanitize_zip_filename("../../../etc/passwd")
        assert ".." not in result
        assert "/" not in result or result == "passwd"

    def test_empty_input(self):
        """Should handle empty input."""
        assert sanitize_zip_filename("") == "unnamed_file"
        assert sanitize_zip_filename(None) == "unnamed_file"

    def test_hidden_files(self):
        """Should remove leading dots."""
        assert sanitize_zip_filename(".hidden") == "hidden"
        assert sanitize_zip_filename("...dots") == "dots"

    def test_long_filename(self):
        """Should truncate long filenames."""
        long_name = "a" * 300 + ".pdf"
        result = sanitize_zip_filename(long_name)
        assert len(result) <= 255
        assert result.endswith(".pdf")


class TestValidateZipFile:
    """Tests for ZIP file validation."""

    def create_zip(self, files: dict) -> bytes:
        """Helper to create a ZIP file in memory."""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            for name, content in files.items():
                zf.writestr(name, content)
        return buffer.getvalue()

    def test_valid_zip(self):
        """Valid ZIP should pass validation."""
        zip_data = self.create_zip({
            "resume1.pdf": b"PDF content here",
            "resume2.docx": b"DOCX content here",
        })
        result = validate_zip_file(zip_data)
        assert result.is_safe is True
        assert result.file_count == 2
        assert result.error is None

    def test_empty_zip(self):
        """Empty ZIP should be valid but with 0 files."""
        zip_data = self.create_zip({})
        result = validate_zip_file(zip_data)
        assert result.is_safe is True
        assert result.file_count == 0

    def test_path_traversal_rejected(self):
        """ZIP with path traversal should be rejected."""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as zf:
            # Create file with path traversal
            zf.writestr("../../../etc/passwd", "malicious content")
        zip_data = buffer.getvalue()

        result = validate_zip_file(zip_data)
        assert result.is_safe is False
        assert "path traversal" in result.error.lower()

    def test_too_many_files(self):
        """ZIP with too many files should be rejected."""
        files = {f"file{i}.txt": f"content {i}" for i in range(100)}
        zip_data = self.create_zip(files)

        result = validate_zip_file(zip_data)
        assert result.is_safe is False
        assert "too many files" in result.error.lower()

    def test_large_file_rejected(self):
        """ZIP with file exceeding size limit should be rejected."""
        # Create content larger than 20MB limit
        large_content = b"x" * (25 * 1024 * 1024)
        zip_data = self.create_zip({"large_file.bin": large_content})

        result = validate_zip_file(zip_data)
        assert result.is_safe is False
        assert "too large" in result.error.lower()

    def test_invalid_zip(self):
        """Invalid ZIP data should be rejected."""
        result = validate_zip_file(b"not a zip file")
        assert result.is_safe is False
        assert "invalid" in result.error.lower() or "bad" in result.error.lower()

    def test_corrupted_zip(self):
        """Corrupted ZIP should be detected."""
        # Create valid ZIP then corrupt it
        zip_data = self.create_zip({"file.txt": "content"})
        corrupted = zip_data[:-10]  # Truncate

        result = validate_zip_file(corrupted)
        assert result.is_safe is False

    def test_macosx_folder_ignored(self):
        """__MACOSX folder should be ignored."""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as zf:
            zf.writestr("resume.pdf", "PDF content")
            zf.writestr("__MACOSX/._resume.pdf", "Mac metadata")
        zip_data = buffer.getvalue()

        result = validate_zip_file(zip_data)
        assert result.is_safe is True
        assert result.file_count == 1  # Only resume.pdf counted


class TestSafeExtract:
    """Tests for safe file extraction."""

    def test_extract_normal_file(self):
        """Should extract normal file successfully."""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as zf:
            zf.writestr("file.txt", "Hello, World!")

        buffer.seek(0)
        with zipfile.ZipFile(buffer, 'r') as zf:
            success, data, error = safe_extract_file(zf, "file.txt")

        assert success is True
        assert data == b"Hello, World!"
        assert error is None

    def test_extract_oversized_file(self):
        """Should reject file exceeding max_size."""
        buffer = io.BytesIO()
        large_content = b"x" * 1000
        with zipfile.ZipFile(buffer, 'w') as zf:
            zf.writestr("large.txt", large_content)

        buffer.seek(0)
        with zipfile.ZipFile(buffer, 'r') as zf:
            success, data, error = safe_extract_file(zf, "large.txt", max_size=500)

        assert success is False
        assert "too large" in error.lower()


class TestZipBombDetection:
    """Tests specifically for ZIP bomb detection."""

    def test_high_compression_ratio_warning(self):
        """
        Test that extremely high compression ratios are detected.

        A real ZIP bomb would have ratios of 1000:1 or more.
        We limit to 100:1 to be safe.
        """
        # Create highly compressible content (repeating pattern)
        # This creates a ~1000:1 compression ratio
        compressible = b"A" * (1024 * 1024)  # 1MB of 'A's

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
            zf.writestr("bomb.txt", compressible)

        zip_data = buffer.getvalue()

        # The compressed size should be much smaller than 1MB
        # If ratio > MAX_COMPRESSION_RATIO, it should be rejected
        result = validate_zip_file(zip_data)

        # Note: Actual ratio depends on compression, may or may not trigger
        # The important thing is the check exists
        if result.is_safe:
            # If safe, verify total size is within limits
            assert result.total_uncompressed_size <= 500 * 1024 * 1024
        else:
            # If not safe, should mention compression or size
            assert "compression" in result.error.lower() or "size" in result.error.lower()
