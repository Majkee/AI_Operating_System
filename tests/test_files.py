"""Tests for file operations."""

import os
import tempfile
from pathlib import Path

import pytest

from aios.executor.files import (
    FileHandler,
    FileInfo,
    FileResult,
    SearchResult,
)


class TestFileInfo:
    """Test FileInfo dataclass."""

    def test_user_friendly_directory(self):
        """Test directory formatting."""
        info = FileInfo(
            path=Path("/home/test"),
            name="test",
            is_directory=True,
            size=0,
            modified=None,
            permissions="755",
            is_hidden=False,
        )
        assert "📁" in info.to_user_friendly()
        assert "test" in info.to_user_friendly()

    def test_user_friendly_text_file(self):
        """Test text file formatting."""
        info = FileInfo(
            path=Path("/home/test.txt"),
            name="test.txt",
            is_directory=False,
            size=1024,
            modified=None,
            permissions="644",
            is_hidden=False,
            mime_type="text/plain",
        )
        result = info.to_user_friendly()
        assert "📝" in result
        assert "test.txt" in result
        assert "KB" in result

    def test_user_friendly_image_file(self):
        """Test image file formatting."""
        info = FileInfo(
            path=Path("/home/photo.jpg"),
            name="photo.jpg",
            is_directory=False,
            size=2048000,
            modified=None,
            permissions="644",
            is_hidden=False,
            mime_type="image/jpeg",
        )
        result = info.to_user_friendly()
        assert "🖼️" in result
        assert "MB" in result

    def test_format_size_bytes(self):
        """Test size formatting for bytes."""
        info = FileInfo(
            path=Path("/test"),
            name="test",
            is_directory=False,
            size=500,
            modified=None,
            permissions="644",
            is_hidden=False,
        )
        assert "B" in info._format_size(500)

    def test_format_size_kilobytes(self):
        """Test size formatting for KB."""
        info = FileInfo(
            path=Path("/test"),
            name="test",
            is_directory=False,
            size=0,
            modified=None,
            permissions="644",
            is_hidden=False,
        )
        assert "KB" in info._format_size(2048)

    def test_format_size_megabytes(self):
        """Test size formatting for MB."""
        info = FileInfo(
            path=Path("/test"),
            name="test",
            is_directory=False,
            size=0,
            modified=None,
            permissions="644",
            is_hidden=False,
        )
        assert "MB" in info._format_size(2 * 1024 * 1024)

    def test_format_size_gigabytes(self):
        """Test size formatting for GB."""
        info = FileInfo(
            path=Path("/test"),
            name="test",
            is_directory=False,
            size=0,
            modified=None,
            permissions="644",
            is_hidden=False,
        )
        assert "GB" in info._format_size(2 * 1024 * 1024 * 1024)


class TestFileHandler:
    """Test FileHandler class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.handler = FileHandler()
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        """Clean up temp files."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_read_file_success(self):
        """Test reading an existing file."""
        test_file = Path(self.temp_dir) / "test.txt"
        test_file.write_text("Hello, World!")

        result = self.handler.read_file(str(test_file))
        assert result.success is True
        assert result.data == "Hello, World!"
        assert "13 characters" in result.message

    def test_read_file_not_found(self):
        """Test reading a non-existent file."""
        result = self.handler.read_file(str(Path(self.temp_dir) / "nonexistent.txt"))
        assert result.success is False
        assert "not found" in result.error.lower()

    def test_read_file_directory(self):
        """Test reading a directory returns error."""
        result = self.handler.read_file(self.temp_dir)
        assert result.success is False
        assert "folder" in result.error.lower()

    def test_read_file_too_large(self):
        """Test reading a file that exceeds size limit."""
        test_file = Path(self.temp_dir) / "large.txt"
        # Create a file larger than MAX_READ_SIZE
        test_file.write_bytes(b"x" * (FileHandler.MAX_READ_SIZE + 1))

        result = self.handler.read_file(str(test_file))
        assert result.success is False
        assert "too large" in result.error.lower()

    def test_write_file_success(self):
        """Test writing a new file."""
        test_file = Path(self.temp_dir) / "new_file.txt"

        result = self.handler.write_file(str(test_file), "New content")
        assert result.success is True
        assert test_file.exists()
        assert test_file.read_text() == "New content"

    def test_write_file_creates_backup(self):
        """Test that writing creates a backup of existing file."""
        test_file = Path(self.temp_dir) / "existing.txt"
        test_file.write_text("Original content")

        result = self.handler.write_file(str(test_file), "Updated content")
        assert result.success is True
        assert result.backup_path is not None
        assert result.backup_path.exists()
        assert result.backup_path.read_text() == "Original content"
        assert test_file.read_text() == "Updated content"

    def test_write_file_creates_directories(self):
        """Test that writing creates parent directories."""
        test_file = Path(self.temp_dir) / "subdir" / "deep" / "file.txt"

        result = self.handler.write_file(str(test_file), "Content")
        assert result.success is True
        assert test_file.exists()

    def test_write_file_no_backup(self):
        """Test writing without backup."""
        test_file = Path(self.temp_dir) / "no_backup.txt"
        test_file.write_text("Original")

        result = self.handler.write_file(
            str(test_file), "Updated", create_backup=False
        )
        assert result.success is True
        assert result.backup_path is None

    def test_delete_file_success(self):
        """Test deleting a file."""
        test_file = Path(self.temp_dir) / "to_delete.txt"
        test_file.write_text("Delete me")

        result = self.handler.delete_file(str(test_file))
        assert result.success is True
        assert not test_file.exists()
        assert result.backup_path is not None

    def test_delete_file_not_found(self):
        """Test deleting a non-existent file."""
        result = self.handler.delete_file(
            str(Path(self.temp_dir) / "nonexistent.txt")
        )
        assert result.success is False
        assert "not found" in result.error.lower()

    def test_list_directory_success(self):
        """Test listing directory contents."""
        # Create some test files
        (Path(self.temp_dir) / "file1.txt").write_text("content")
        (Path(self.temp_dir) / "file2.txt").write_text("content")
        (Path(self.temp_dir) / "subdir").mkdir()

        result = self.handler.list_directory(self.temp_dir)
        assert result.total_count == 3
        assert len(result.files) == 3

    def test_list_directory_hides_hidden_files(self):
        """Test that hidden files are excluded by default."""
        (Path(self.temp_dir) / "visible.txt").write_text("content")
        (Path(self.temp_dir) / ".hidden.txt").write_text("content")

        result = self.handler.list_directory(self.temp_dir, show_hidden=False)
        names = [f.name for f in result.files]
        assert "visible.txt" in names
        assert ".hidden.txt" not in names

    def test_list_directory_shows_hidden_files(self):
        """Test that hidden files can be shown."""
        (Path(self.temp_dir) / "visible.txt").write_text("content")
        (Path(self.temp_dir) / ".hidden.txt").write_text("content")

        result = self.handler.list_directory(self.temp_dir, show_hidden=True)
        names = [f.name for f in result.files]
        assert "visible.txt" in names
        assert ".hidden.txt" in names

    def test_list_directory_sorts_correctly(self):
        """Test that directories come before files."""
        (Path(self.temp_dir) / "b_file.txt").write_text("content")
        (Path(self.temp_dir) / "a_dir").mkdir()
        (Path(self.temp_dir) / "c_file.txt").write_text("content")

        result = self.handler.list_directory(self.temp_dir)
        # First should be directory
        assert result.files[0].is_directory is True
        assert result.files[0].name == "a_dir"

    def test_search_files_by_filename(self):
        """Test searching files by filename."""
        (Path(self.temp_dir) / "test_file.txt").write_text("content")
        (Path(self.temp_dir) / "other.txt").write_text("content")
        subdir = Path(self.temp_dir) / "subdir"
        subdir.mkdir()
        (subdir / "test_nested.txt").write_text("content")

        result = self.handler.search_files("test", self.temp_dir, "filename")
        assert result.total_count == 2
        names = [f.name for f in result.files]
        assert "test_file.txt" in names
        assert "test_nested.txt" in names

    def test_search_files_by_content(self):
        """Test searching files by content."""
        (Path(self.temp_dir) / "match.txt").write_text("This contains the keyword")
        (Path(self.temp_dir) / "nomatch.txt").write_text("Nothing here")

        result = self.handler.search_files("keyword", self.temp_dir, "content")
        assert result.total_count == 1
        assert result.files[0].name == "match.txt"

    def test_search_files_case_insensitive(self):
        """Test that search is case insensitive."""
        (Path(self.temp_dir) / "TestFile.TXT").write_text("content")

        result = self.handler.search_files("testfile", self.temp_dir, "filename")
        assert result.total_count == 1

    def test_search_files_respects_limit(self):
        """Test that search respects MAX_SEARCH_RESULTS."""
        # Create many files
        for i in range(150):
            (Path(self.temp_dir) / f"file_{i}.txt").write_text("content")

        result = self.handler.search_files("file", self.temp_dir, "filename")
        assert result.total_count == FileHandler.MAX_SEARCH_RESULTS
        assert result.truncated is True

    def test_get_file_info_exists(self):
        """Test getting info for existing file."""
        test_file = Path(self.temp_dir) / "info_test.txt"
        test_file.write_text("content")

        info = self.handler.get_file_info(str(test_file))
        assert info is not None
        assert info.name == "info_test.txt"
        assert info.is_directory is False

    def test_get_file_info_not_exists(self):
        """Test getting info for non-existent file."""
        info = self.handler.get_file_info(str(Path(self.temp_dir) / "nonexistent"))
        assert info is None

    def test_restore_backup_success(self):
        """Test restoring from backup."""
        original = Path(self.temp_dir) / "original.txt"
        backup = Path(self.temp_dir) / "backup.txt"

        backup.write_text("Backup content")
        original.write_text("Current content")

        result = self.handler.restore_backup(str(backup), str(original))
        assert result.success is True
        assert original.read_text() == "Backup content"

    def test_restore_backup_not_found(self):
        """Test restoring from non-existent backup."""
        result = self.handler.restore_backup(
            str(Path(self.temp_dir) / "nonexistent"),
            str(Path(self.temp_dir) / "target")
        )
        assert result.success is False
        assert "not found" in result.error.lower()
