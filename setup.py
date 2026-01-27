"""Thin shim — all metadata lives in pyproject.toml."""

from setuptools import setup, find_packages

if __name__ == "__main__":
    # Use find_packages but exclude config and other non-package directories
    # This prevents setuptools from treating config/ as a package
    setup(
        packages=find_packages(exclude=["config", "tests", "plugins", "workspace", "*.tests", "*.tests.*", "tests.*"]),
    )
