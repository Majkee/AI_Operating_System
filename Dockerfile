# AIOS - AI-powered Operating System Interface
# Debian-based Docker image

FROM debian:bookworm-slim

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Install Python and system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user for security
RUN useradd -m -s /bin/bash aios

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
COPY config/ ./config/
COPY setup.py .
COPY README.md .

# Install the application
RUN /app/venv/bin/pip install --no-cache-dir -e .

# Change ownership to non-root user
RUN chown -R aios:aios /app

# Switch to non-root user
USER aios

# Add venv to PATH
ENV PATH="/app/venv/bin:$PATH"

# Environment variable for Anthropic API key (must be provided at runtime)
ENV ANTHROPIC_API_KEY=""

# Default command
CMD ["aios"]
