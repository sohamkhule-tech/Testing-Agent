"""
Path Utilities

Provides utilities for file and path operations.
"""

import hashlib
from pathlib import Path
from typing import AsyncIterator

import aiofiles

from app.logging import get_logger

logger = get_logger("utils.path")


def ensure_directory(path: Path) -> Path:
    """
    Ensure directory exists.

    Args:
        path: Directory path

    Returns:
        Path object

    Example:
        >>> path = ensure_directory(Path("./storage/artifacts"))
    """
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_file_size(file_path: Path) -> int:
    """
    Get file size in bytes.

    Args:
        file_path: File path

    Returns:
        File size in bytes

    Example:
        >>> size = get_file_size(Path("data.json"))
    """
    return file_path.stat().st_size if file_path.exists() else 0


def get_file_hash(file_path: Path, algorithm: str = "sha256") -> str:
    """
    Calculate file hash.

    Args:
        file_path: File path
        algorithm: Hash algorithm (sha256, md5, etc.)

    Returns:
        Hex digest of file hash

    Example:
        >>> hash_val = get_file_hash(Path("data.json"))
    """
    hash_obj = hashlib.new(algorithm)
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hash_obj.update(chunk)
    return hash_obj.hexdigest()


async def read_file_async(file_path: Path) -> bytes:
    """
    Read file content asynchronously.

    Args:
        file_path: File path

    Returns:
        File content as bytes

    Example:
        >>> content = await read_file_async(Path("data.bin"))
    """
    async with aiofiles.open(file_path, "rb") as f:
        return await f.read()


async def write_file_async(file_path: Path, content: bytes) -> None:
    """
    Write content to file asynchronously.

    Args:
        file_path: File path
        content: Content to write

    Example:
        >>> await write_file_async(Path("output.bin"), b"data")
    """
    ensure_directory(file_path.parent)
    async with aiofiles.open(file_path, "wb") as f:
        await f.write(content)


async def copy_file_async(source: Path, destination: Path) -> None:
    """
    Copy file asynchronously.

    Args:
        source: Source file path
        destination: Destination file path

    Example:
        >>> await copy_file_async(Path("source.txt"), Path("dest.txt"))
    """
    content = await read_file_async(source)
    await write_file_async(destination, content)


async def read_chunks(
    file_path: Path, chunk_size: int = 8192
) -> AsyncIterator[bytes]:
    """
    Read file in chunks asynchronously.

    Args:
        file_path: File path
        chunk_size: Size of each chunk in bytes

    Yields:
        File chunks

    Example:
        >>> async for chunk in read_chunks(Path("large_file.bin")):
        ...     process(chunk)
    """
    async with aiofiles.open(file_path, "rb") as f:
        while True:
            chunk = await f.read(chunk_size)
            if not chunk:
                break
            yield chunk


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename by removing invalid characters.

    Args:
        filename: Original filename

    Returns:
        Sanitized filename

    Example:
        >>> clean = sanitize_filename("my file*.txt")
        >>> # "my_file.txt"
    """
    import re

    # Remove invalid characters
    clean = re.sub(r'[<>:"/\\|?*]', "_", filename)
    # Remove multiple underscores
    clean = re.sub(r"_+", "_", clean)
    # Remove leading/trailing spaces and dots
    clean = clean.strip(". ")
    return clean or "unnamed"


def get_relative_path(base: Path, target: Path) -> Path:
    """
    Get relative path from base to target.

    Args:
        base: Base path
        target: Target path

    Returns:
        Relative path

    Example:
        >>> rel = get_relative_path(Path("/a/b"), Path("/a/b/c/d"))
        >>> # Path("c/d")
    """
    try:
        return target.relative_to(base)
    except ValueError:
        return target
