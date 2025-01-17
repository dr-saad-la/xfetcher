"""
    Data download utility functions.
"""
from urllib.parse import urlparse, unquote
import os
from pathlib import Path
from typing import Union, Optional


def get_filename_from_url(url: str) -> str:
    """
    Extract and decode the filename from a URL, handling URL-encoded characters.

    This function parses a URL to extract its filename component, decodes any URL-encoded
    characters, and provides a default filename if none is found in the URL.

    Args:
        url (str): The URL to extract the filename from. Can be a complete URL
                  (e.g., 'https://example.com/path/file.zip') or a partial URL path.

    Returns:
        str: The decoded filename from the URL. If no filename is found, returns
             'downloaded_file.zip' as a default value.

    Examples:
        >>> get_filename_from_url('https://example.com/path/my%20file.zip')
        'my file.zip'

        >>> get_filename_from_url('https://example.com/path/')
        'downloaded_file.zip'

        >>> get_filename_from_url('https://example.com/path/report%20%282023%29.pdf')
        'report (2023).pdf'

    Notes:
        - The function handles URL-encoded characters (e.g., %20 for spaces)
        - It extracts only the filename, not the full path
        - Special characters in the filename will be properly decoded
        - If the URL ends with a slash or has no filename, returns the default

    Raises:
        ValueError: If the URL is malformed or cannot be parsed
        TypeError: If the URL is not a string
    """
    try:
        parsed_url = urlparse(url)
        filename = os.path.basename(parsed_url.path)
        decoded_filename = unquote(filename)

        # Return the decoded filename or default if empty
        return decoded_filename if decoded_filename else 'downloaded_file.zip'

    except TypeError as e:
        raise TypeError(f"URL must be a string, got {type(url).__name__}") from e
    except Exception as e:
        raise ValueError(f"Failed to parse URL: {str(e)}") from e















