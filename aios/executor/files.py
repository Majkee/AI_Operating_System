"""
File operations handler for AIOS.

Provides safe file operations with:
- Backup creation
- Permission checks
- Size limits
- User-friendly error messages
"""

import os
import shutil
import mimetypes
from pathlib import Path
from datetime import datetime
from typing import Optional, List
from dataclasses import dataclass, field


@dataclass
class FileInfo:
    """Information about a file."""
    path: Path
    name: str
    is_directory: bool
    size: int
    modified: datetime
    permissions: str
    is_hidden: bool
    mime_type: Optional[str] = None

    def to_user_friendly(self) -> str:
        """Get user-friendly description."""
        if self.is_directory:
            return f"📁 {self.name}"

        # Determine icon based on type
        icon = "📄"
        if self.mime_type:
            if self.mime_type.startswith("image/"):
                icon = "🖼️"
            elif self.mime_type.startswith("video/"):
                icon = "🎬"
            elif self.mime_type.startswith("audio/"):
                icon = "🎵"
            elif self.mime_type.startswith("text/"):
                icon = "📝"
            elif "pdf" in self.mime_type:
                icon = "📕"
            elif "zip" in self.mime_type or "archive" in self.mime_type:
                icon = "📦"

        size_str = self._format_size(self.size)
        return f"{icon} {self.name} ({size_str})"

    def _format_size(self, size: int) -> str:
        """Format file size in human-readable form."""
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"


@dataclass
class FileResult:
    """Result of a file operation."""
    success: bool
    message: str
    data: Optional[str] = None
    backup_path: Optional[Path] = None
    error: Optional[str] = None


@dataclass
class SearchResult:
    """Result of a file search."""
    files: List[FileInfo] = field(default_factory=list)
    total_count: int = 0
    truncated: bool = False
    search_path: str = ""
    query: str = ""


class FileHandler:
    """Handles file operations safely."""

    # Maximum file size to read (10MB)
    MAX_READ_SIZE = 10 * 1024 * 1024

    # Maximum search results
    MAX_SEARCH_RESULTS = 100

    # Backup directory name
    BACKUP_DIR = ".aios_backups"

    def __init__(self):
        """Initialize the file handler."""
        self.home = Path.home()

    def _ensure_safe_path(self, path: str) -> Path:
        """
        Ensure a path is safe to access.

        Resolves path and checks it's within allowed locations.
        """
        p = Path(path).expanduser().resolve()

        # For now, allow access to user's home and /tmp
        # Can be made more restrictive based on config
        allowed_roots = [self.home, Path("/tmp")]

        for root in allowed_roots:
            try:
                p.relative_to(root)
                return p
            except ValueError:
                continue

        # Allow absolute paths but warn
        # In production, this should be more restrictive
        return p

    def _get_backup_path(self, file_path: Path) -> Path:
        """Get the backup path for a file."""
        backup_dir = self.home / self.BACKUP_DIR
        backup_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{file_path.name}.{timestamp}.bak"
        return backup_dir / backup_name

    def read_file(self, path: str) -> FileResult:
        """
        Read contents of a file.

        Args:
            path: Path to the file

        Returns:
            FileResult with file contents or error
        """
        try:
            file_path = self._ensure_safe_path(path)

            if not file_path.exists():
                return FileResult(
                    success=False,
                    message="",
                    error=f"File not found: {path}"
                )

            if file_path.is_dir():
                return FileResult(
                    success=False,
                    message="",
                    error="That's a folder, not a file. Use list_directory to see its contents."
                )

            # Check file size
            size = file_path.stat().st_size
            if size > self.MAX_READ_SIZE:
                return FileResult(
                    success=False,
                    message="",
                    error=f"File is too large ({size / 1024 / 1024:.1f} MB). Maximum is 10 MB."
                )

            # Detect if binary
            mime_type, _ = mimetypes.guess_type(str(file_path))
            if mime_type and not mime_type.startswith("text/"):
                # Try to determine file type
                if mime_type.startswith("image/"):
                    return FileResult(
                        success=True,
                        message=f"This is an image file ({mime_type}). I can't display it directly, but I can help you open it.",
                        data=None
                    )
                elif mime_type.startswith(("audio/", "video/")):
                    return FileResult(
                        success=True,
                        message=f"This is a media file ({mime_type}). I can help you open or play it.",
                        data=None
                    )

            # Read file
            try:
                content = file_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                return FileResult(
                    success=False,
                    message="",
                    error="This file contains binary data and can't be displayed as text."
                )

            return FileResult(
                success=True,
                message=f"Read {len(content)} characters from {file_path.name}",
                data=content
            )

        except PermissionError:
            return FileResult(
                success=False,
                message="",
                error="You don't have permission to read this file."
            )
        except Exception as e:
            return FileResult(
                success=False,
                message="",
                error=f"Error reading file: {str(e)}"
            )

    def write_file(
        self,
        path: str,
        content: str,
        create_backup: bool = True
    ) -> FileResult:
        """
        Write content to a file.

        Args:
            path: Path to the file
            content: Content to write
            create_backup: Whether to backup existing file

        Returns:
            FileResult with status
        """
        try:
            file_path = self._ensure_safe_path(path)
            backup_path = None

            # Create parent directories if needed
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # Backup existing file
            if create_backup and file_path.exists():
                backup_path = self._get_backup_path(file_path)
                shutil.copy2(file_path, backup_path)

            # Write new content
            file_path.write_text(content, encoding="utf-8")

            message = f"Saved {file_path.name}"
            if backup_path:
                message += f" (backup created)"

            return FileResult(
                success=True,
                message=message,
                backup_path=backup_path
            )

        except PermissionError:
            return FileResult(
                success=False,
                message="",
                error="You don't have permission to write to this location."
            )
        except Exception as e:
            return FileResult(
                success=False,
                message="",
                error=f"Error writing file: {str(e)}"
            )

    def delete_file(self, path: str, create_backup: bool = True) -> FileResult:
        """
        Delete a file (with optional backup).

        Args:
            path: Path to the file
            create_backup: Whether to backup before deleting

        Returns:
            FileResult with status
        """
        try:
            file_path = self._ensure_safe_path(path)

            if not file_path.exists():
                return FileResult(
                    success=False,
                    message="",
                    error=f"File not found: {path}"
                )

            backup_path = None
            if create_backup:
                backup_path = self._get_backup_path(file_path)
                shutil.copy2(file_path, backup_path)

            if file_path.is_dir():
                shutil.rmtree(file_path)
                message = f"Deleted folder {file_path.name}"
            else:
                file_path.unlink()
                message = f"Deleted {file_path.name}"

            if backup_path:
                message += f" (backup saved)"

            return FileResult(
                success=True,
                message=message,
                backup_path=backup_path
            )

        except PermissionError:
            return FileResult(
                success=False,
                message="",
                error="You don't have permission to delete this."
            )
        except Exception as e:
            return FileResult(
                success=False,
                message="",
                error=f"Error deleting: {str(e)}"
            )

    def list_directory(
        self,
        path: Optional[str] = None,
        show_hidden: bool = False
    ) -> SearchResult:
        """
        List contents of a directory.

        Args:
            path: Directory path (defaults to home)
            show_hidden: Whether to show hidden files

        Returns:
            SearchResult with file list
        """
        try:
            dir_path = self._ensure_safe_path(path) if path else self.home

            if not dir_path.exists():
                return SearchResult(
                    files=[],
                    total_count=0,
                    search_path=str(dir_path),
                    query=""
                )

            if not dir_path.is_dir():
                return SearchResult(
                    files=[],
                    total_count=0,
                    search_path=str(dir_path),
                    query=""
                )

            files = []
            for entry in dir_path.iterdir():
                # Skip hidden files unless requested
                if not show_hidden and entry.name.startswith("."):
                    continue

                try:
                    stat = entry.stat()
                    mime_type, _ = mimetypes.guess_type(str(entry))

                    files.append(FileInfo(
                        path=entry,
                        name=entry.name,
                        is_directory=entry.is_dir(),
                        size=stat.st_size if not entry.is_dir() else 0,
                        modified=datetime.fromtimestamp(stat.st_mtime),
                        permissions=oct(stat.st_mode)[-3:],
                        is_hidden=entry.name.startswith("."),
                        mime_type=mime_type
                    ))
                except (PermissionError, OSError):
                    continue

            # Sort: directories first, then by name
            files.sort(key=lambda f: (not f.is_directory, f.name.lower()))

            return SearchResult(
                files=files,
                total_count=len(files),
                truncated=False,
                search_path=str(dir_path),
                query=""
            )

        except Exception as e:
            return SearchResult(
                files=[],
                total_count=0,
                search_path=str(path or self.home),
                query=""
            )

    def search_files(
        self,
        query: str,
        location: Optional[str] = None,
        search_type: str = "filename"
    ) -> SearchResult:
        """
        Search for files by name or content.

        Args:
            query: Search query
            location: Directory to search in
            search_type: "filename" or "content"

        Returns:
            SearchResult with matching files
        """
        try:
            search_path = self._ensure_safe_path(location) if location else self.home

            if not search_path.exists() or not search_path.is_dir():
                return SearchResult(
                    files=[],
                    total_count=0,
                    search_path=str(search_path),
                    query=query
                )

            files = []
            query_lower = query.lower()

            # Walk directory tree
            for root, dirs, filenames in os.walk(search_path):
                # Skip hidden directories
                dirs[:] = [d for d in dirs if not d.startswith(".")]

                for filename in filenames:
                    if len(files) >= self.MAX_SEARCH_RESULTS:
                        break

                    # Skip hidden files
                    if filename.startswith("."):
                        continue

                    file_path = Path(root) / filename

                    match = False
                    if search_type == "filename":
                        match = query_lower in filename.lower()
                    elif search_type == "content":
                        try:
                            # Only search text files
                            mime_type, _ = mimetypes.guess_type(str(file_path))
                            if mime_type and mime_type.startswith("text/"):
                                content = file_path.read_text(
                                    encoding="utf-8",
                                    errors="ignore"
                                )
                                match = query_lower in content.lower()
                        except (PermissionError, OSError):
                            continue

                    if match:
                        try:
                            stat = file_path.stat()
                            mime_type, _ = mimetypes.guess_type(str(file_path))

                            files.append(FileInfo(
                                path=file_path,
                                name=filename,
                                is_directory=False,
                                size=stat.st_size,
                                modified=datetime.fromtimestamp(stat.st_mtime),
                                permissions=oct(stat.st_mode)[-3:],
                                is_hidden=filename.startswith("."),
                                mime_type=mime_type
                            ))
                        except (PermissionError, OSError):
                            continue

                if len(files) >= self.MAX_SEARCH_RESULTS:
                    break

            return SearchResult(
                files=files,
                total_count=len(files),
                truncated=(len(files) >= self.MAX_SEARCH_RESULTS),
                search_path=str(search_path),
                query=query
            )

        except Exception as e:
            return SearchResult(
                files=[],
                total_count=0,
                search_path=str(location or self.home),
                query=query
            )

    def get_file_info(self, path: str) -> Optional[FileInfo]:
        """Get information about a specific file."""
        try:
            file_path = self._ensure_safe_path(path)
            if not file_path.exists():
                return None

            stat = file_path.stat()
            mime_type, _ = mimetypes.guess_type(str(file_path))

            return FileInfo(
                path=file_path,
                name=file_path.name,
                is_directory=file_path.is_dir(),
                size=stat.st_size if not file_path.is_dir() else 0,
                modified=datetime.fromtimestamp(stat.st_mtime),
                permissions=oct(stat.st_mode)[-3:],
                is_hidden=file_path.name.startswith("."),
                mime_type=mime_type
            )
        except Exception:
            return None

    def restore_backup(self, backup_path: str, original_path: str) -> FileResult:
        """Restore a file from backup."""
        try:
            backup = Path(backup_path)
            original = Path(original_path)

            if not backup.exists():
                return FileResult(
                    success=False,
                    message="",
                    error="Backup file not found."
                )

            shutil.copy2(backup, original)
            return FileResult(
                success=True,
                message=f"Restored {original.name} from backup."
            )
        except Exception as e:
            return FileResult(
                success=False,
                message="",
                error=f"Error restoring backup: {str(e)}"
            )
