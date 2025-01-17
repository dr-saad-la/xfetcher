"""Data downloading functionality for handling file downloads and ZIP archives.

This module provides utilities for downloading files from URLs and handling
ZIP archives with progress tracking.
"""

from __future__ import annotations

import os
import shutil
import zipfile
from pathlib import Path
from typing import List
from typing import Optional
from typing import Tuple
from typing import TypeVar
from typing import Union

from tqdm import tqdm

import requests

from .utils import get_filename_from_url

P = TypeVar("P", str, Path)


class DownloaderError(Exception):
    """Base exception for downloader-related errors."""

    # pass


class DownloadCancelled(DownloaderError):
    """Raised when a download operation is cancelled."""

    # pass


class Downloader:
    """Handles downloading and extracting files, particularly ZIP archives.

    Attributes:
        save_dir (Path): Directory where downloaded files will be saved
        keep_zip (bool): Whether to keep ZIP files after extraction

    Example:
        >>> downloader = Downloader(save_dir="downloads")
        >>> downloader.download_file("https://example.com/file.zip")
    """

    def __init__(
        self, save_dir: Union[str, Path] = "downloads", keep_zip: bool = False
    ):
        """
        Initialize the Downloader.

        Args:
            save_dir (Union[str, Path]): Directory to save downloaded files
            keep_zip (bool): If True, keeps ZIP files after extraction
        """
        self.save_dir = Path(save_dir)
        self.keep_zip = keep_zip
        self.save_dir.mkdir(parents=True, exist_ok=True)

        if not os.access(self.save_dir, os.W_OK):
            raise PermissionError(f"No write permission in directory: {self.save_dir}")

    def __enter__(self):
        """Context manager entry point."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit point - cleanup temporary files."""
        if not self.keep_zip:
            for zip_file in self.save_dir.glob("*.zip"):
                zip_file.unlink(missing_ok=True)

    @staticmethod
    def _is_safe_path(path: str) -> bool:
        """
        Check if a path is safe (no directory traversal or absolute paths).

        Args:
            path (str): Path to check

        Returns:
            bool: True if path is safe, False otherwise
        """
        return not any(
            part.startswith("\\")  # Windows absolute path
            or part.startswith("/")  # Unix absolute path
            or ".." in part  # Parent directory traversal
            or ":" in part  # Windows drive letter
            for part in Path(path).parts
        )

    def download_file(
        self, url: str, filename: Optional[str] = None, chunk_size: int = 8192
    ) -> Path:
        """
        Download a file from the given URL with progress bar.

        Args:
            url (str): URL to download from
            filename (Optional[str]): Custom filename for saving
            chunk_size (int): Size of chunks to download

        Returns:
            Path: Path to the downloaded file

        Raises:
            ConnectionError: If connection to URL fails
            TimeoutError: If download times out
            FileExistsError: If file already exists
            UserCancelled: If user cancels large download
            Exception: For other download failures
        """
        if not filename:
            filename = get_filename_from_url(url)

        file_path = self.save_dir / filename

        if file_path.exists():
            raise FileExistsError(f"File already exists: {file_path}")

        try:
            response = requests.get(url, stream=True, timeout=(3.05, 27))
            response.raise_for_status()

            total_size = int(response.headers.get("content-length", 0))

            # Check file size for large downloads
            if total_size > 1024 * 1024 * 1024:  # 1GB
                response = input(
                    f"File size is {self._humanize_size(total_size)}. Continue? (y/n): "
                )
                if response.lower() != "y":
                    raise DownloadCancelled("Download cancelled by user")

            with open(file_path, "wb") as f:
                with tqdm(
                    total=total_size,
                    unit="iB",
                    unit_scale=True,
                    desc=f"Downloading {filename}",
                ) as pbar:
                    for data in response.iter_content(chunk_size):
                        size = f.write(data)
                        pbar.update(size)

        except requests.ConnectionError:
            if file_path.exists():
                file_path.unlink()
            raise ConnectionError(f"Failed to connect to {url}")

        except requests.Timeout:
            if file_path.exists():
                file_path.unlink()
            raise TimeoutError(f"Download timed out for {url}")

        except requests.RequestException as e:
            if file_path.exists():
                file_path.unlink()
            raise Exception(f"Download failed: {str(e)}") from e
        finally:
            response.close()

        return file_path

    def extract_zip(
        self,
        zip_path: Union[str, Path],
        extract_path: Optional[Union[str, Path]] = None,
    ) -> Path:
        """
        Extract a ZIP file, including nested ZIP files.

        Args:
            zip_path (Union[str, Path]): Path to the ZIP file
            extract_path (Optional[Union[str, Path]]): Custom extraction path

        Returns:
            Path: Path to the extraction directory

        Raises:
            ValueError: If ZIP file is invalid or contains unsafe paths
            zipfile.BadZipFile: If ZIP file is corrupted
        """
        zip_path = Path(zip_path)
        if not zipfile.is_zipfile(zip_path):
            raise ValueError(f"Not a valid ZIP file: {zip_path}")

        if extract_path is None:
            extract_path = self.save_dir / zip_path.stem
        else:
            extract_path = Path(extract_path)

        extract_path.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            # Check for dangerous paths
            unsafe_paths = [
                name for name in zip_ref.namelist() if not self._is_safe_path(name)
            ]
            if unsafe_paths:
                raise ValueError(f"Potentially dangerous paths in zip: {unsafe_paths}")

            # Extract with progress bar
            total_files = len(zip_ref.namelist())
            with tqdm(total=total_files, desc="Extracting files") as pbar:
                for member in zip_ref.namelist():
                    zip_ref.extract(member, extract_path)
                    pbar.update(1)

                    # Handle nested ZIP files
                    if member.lower().endswith(".zip"):
                        nested_path = extract_path / member
                        nested_extract_path = extract_path / Path(member).stem
                        try:
                            self.extract_zip(nested_path, nested_extract_path)
                        finally:
                            if not self.keep_zip:
                                nested_path.unlink(missing_ok=True)

        if not self.keep_zip:
            zip_path.unlink(missing_ok=True)

        return extract_path

    def _format_extracted_files(self, base_dir: Path, files: List[Path]) -> List[str]:
        """
        Format extracted files list with relative paths and sizes.

        Args:
            base_dir (Path): Base directory to calculate relative paths from
            files (List[Path]): List of file paths

        Returns:
            List[str]: Formatted strings with relative paths and sizes
        """
        formatted_files = []
        for file_path in sorted(files):
            if file_path.is_file():  # Only include files, not directories
                try:
                    relative_path = file_path.relative_to(base_dir)
                    size = file_path.stat().st_size
                    formatted_files.append(
                        f"{relative_path} ({self._humanize_size(size)})"
                    )
                except (OSError, ValueError):
                    continue  # Skip files that can't be accessed or have invalid paths
        return formatted_files

    def download_and_extract(
        self, url: str, extract_path: Optional[Union[str, Path]] = None
    ) -> Tuple[str, List[str]]:
        """
        Download a ZIP file and extract its contents.

        Args:
            url (str): URL of the ZIP file
            extract_path (Optional[Union[str, Path]]): Custom extraction path

        Returns:
            Tuple[Path, List[Path]]: Extraction directory path and list of extracted files
        """
        try:
            # Download the file
            zip_path = self.download_file(url)

            # Extract the ZIP file
            extract_dir = self.extract_zip(zip_path, extract_path)

            # Get list of extracted files
            extracted_files = list(extract_dir.rglob("*"))

            # Format the file list
            formatted_files = self._format_extracted_files(extract_dir, extracted_files)

            # Print the formatted list
            print("\nExtracted files:")
            for file_info in formatted_files:
                print("    ", file_info)

            return str(extract_dir), [str(f) for f in formatted_files]

        except Exception as e:
            # Cleanup any partially downloaded/extracted files
            if "zip_path" in locals():
                Path(zip_path).unlink(missing_ok=True)
            if "extract_dir" in locals():
                shutil.rmtree(extract_dir, ignore_errors=True)
            raise Exception(f"Failed to download and extract: {str(e)}") from e

    def list_contents(self, directory: Optional[Union[str, Path]] = None) -> None:
        """
        List all files in the specified directory or save_dir.

        Args:
            directory (Optional[Union[str, Path]]): Directory to list contents from
        """
        dir_to_list = Path(directory) if directory else self.save_dir

        if not dir_to_list.exists():
            print(f"Directory does not exist: {dir_to_list}")
            return

        print(f"\nContents of {dir_to_list}:")
        try:
            for item in dir_to_list.rglob("*"):
                if item.is_file():
                    relative_path = item.relative_to(dir_to_list)
                    size = item.stat().st_size
                    print(f"{relative_path} ({self._humanize_size(size)})")
        except PermissionError:
            print(f"Permission denied while accessing some files in {dir_to_list}")

    @staticmethod
    def _humanize_size(size: int) -> str:
        """
        Convert size in bytes to human-readable format.

        Args:
            size (int): Size in bytes

        Returns:
            str: Human readable size string
        """
        current_size = float(size)
        for unit in ["B", "KB", "MB", "GB"]:
            if current_size < 1024:
                return f"{size:.1f}{unit}"
            current_size /= 1024
        return f"{size:.1f}TB"
