"""Cumpiler utilities."""

import sys

EXIT_SUCCESS: int = 0
EXIT_ERROR: int = 1


def log(*args, file=sys.stderr, **kwargs):
    """Prints log messages to stderr."""
    # Note that stderr is unbuffered: always flush.
    print(file=sys.stderr, *args, **kwargs)


def log_info(message: str = "", *args, file=sys.stderr, **kwargs):
    """Prints an informational message to stderr in terminal blue-tint."""
    # Note that stderr is unbuffered: always flush.
    print(f"\033[34m{message}\033[m", *args, file=file, **kwargs)


def log_warning(message: str = "", *args, file=sys.stderr, **kwargs):
    """Prints a warning message to stderr in terminal yellow-tint."""
    # Note that stderr is unbuffered: always flush.
    print(f"\033[33m{message}\033[m", *args, file=file, **kwargs)


def log_success(message: str = "", *args, file=sys.stderr, **kwargs):
    """Prints a success message to stderr in terminal green-tint."""
    # Note that stderr is unbuffered: always flush.
    print(f"\033[32m{message}\033[m", *args, file=file, **kwargs)


def log_error(message: str = "", *args, file=sys.stderr, **kwargs):
    """Prints an error message to stderr in terminal red-tint."""
    # Note that stderr is unbuffered: always flush.
    print(f"\033[31m{message}\033[m", *args, file=file, **kwargs)
