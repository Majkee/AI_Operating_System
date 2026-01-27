"""
AIOS - AI-powered Operating System Interface

Setup script for installation.
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read README
readme_path = Path(__file__).parent / "README.md"
long_description = ""
if readme_path.exists():
    long_description = readme_path.read_text(encoding="utf-8")

# Read requirements
requirements_path = Path(__file__).parent / "requirements.txt"
requirements = []
if requirements_path.exists():
    requirements = [
        line.strip()
        for line in requirements_path.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]

setup(
    name="aios",
    version="0.2.0",
    author="AIOS Team",
    author_email="aios@example.com",
    description="AI-powered Operating System Interface - Natural language interface for Linux",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/your-org/aios",
    packages=find_packages(),
    include_package_data=True,
    package_data={
        "aios": ["../config/*.toml"],
    },
    python_requires=">=3.10",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "aios=aios.main:main",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Environment :: Console",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: System :: Operating System",
        "Topic :: Utilities",
    ],
    keywords="ai assistant linux natural-language claude",
)
