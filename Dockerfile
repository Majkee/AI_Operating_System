# AIOS - AI-powered Operating System Interface
# Debian-based Docker image

FROM debian:trixie-slim

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Install Python, sudo, system dependencies, and Node.js
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    sudo \
    curl \
    wget \
    git \
    procps \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Install Claude Code CLI globally
RUN npm install -g @anthropic-ai/claude-code

# Create non-root user with sudo privileges
RUN useradd -m -s /bin/bash aios \
    && echo "aios ALL=(ALL) NOPASSWD: ALL" > /etc/sudoers.d/aios \
    && chmod 0440 /etc/sudoers.d/aios

# Set working directory
WORKDIR /app

# Copy requirements first for better layer caching
COPY requirements.txt .

# Create virtual environment and install dependencies
RUN python3 -m venv /app/venv \
    && /app/venv/bin/pip install --no-cache-dir --upgrade pip \
    && /app/venv/bin/pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY aios/ ./aios/
COPY setup.py .
COPY pyproject.toml .
COPY README.md .

# Install the application (config/ is not copied to avoid setuptools package discovery issues)
# The default.toml is included as package data in aios/data/default.toml
RUN /app/venv/bin/pip install --no-cache-dir -e .

# Change ownership to non-root user
RUN chown -R aios:aios /app

# Create config directories with proper ownership
RUN mkdir -p /home/aios/.config/aios/history \
    /home/aios/.config/aios/plugins \
    && chown -R aios:aios /home/aios/.config

# Switch to non-root user
USER aios

# Add venv to PATH
ENV PATH="/app/venv/bin:$PATH"

# Environment variable for Anthropic API key (must be provided at runtime)
ENV ANTHROPIC_API_KEY=""

# Default command
CMD ["aios"]
