# AIOS - AI-powered Operating System Interface
# Debian-based Docker image with Ansible support

FROM debian:trixie-slim

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Install Python, sudo, system dependencies, Node.js, and Ansible prerequisites
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    sudo \
    curl \
    wget \
    git \
    procps \
    nodejs \
    npm \
    openssh-client \
    sshpass \
    libffi-dev \
    libssl-dev \
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

# Install Ansible and network automation collections
RUN /app/venv/bin/pip install --no-cache-dir \
    ansible-core>=2.15 \
    paramiko \
    netaddr \
    jmespath \
    && mkdir -p /usr/share/ansible/collections \
    && /app/venv/bin/ansible-galaxy collection install \
    ansible.netcommon \
    ansible.posix \
    community.general \
    cisco.ios \
    junipernetworks.junos \
    arista.eos \
    -p /usr/share/ansible/collections \
    --force

# Copy application code
COPY aios/ ./aios/
COPY skills/ ./skills/
COPY setup.py .
COPY pyproject.toml .
COPY README.md .

# Install the application (config/ is not copied to avoid setuptools package discovery issues)
# The default.toml is included as package data in aios/data/default.toml
RUN /app/venv/bin/pip install --no-cache-dir -e .

# Copy skills to system-wide location for all users
RUN mkdir -p /etc/aios/skills \
    && cp -r /app/skills/* /etc/aios/skills/ 2>/dev/null || true

# Change ownership to non-root user
RUN chown -R aios:aios /app

# Create config directories with proper ownership
RUN mkdir -p /home/aios/.config/aios/history \
    /home/aios/.config/aios/skills \
    /home/aios/.ansible \
    /home/aios/.ssh \
    && chown -R aios:aios /home/aios/.config \
    && chown -R aios:aios /home/aios/.ansible \
    && chown -R aios:aios /home/aios/.ssh \
    && chmod 700 /home/aios/.ssh

# Switch to non-root user
USER aios

# Add venv to PATH
ENV PATH="/app/venv/bin:$PATH"

# Ansible configuration
ENV ANSIBLE_HOST_KEY_CHECKING=False
ENV ANSIBLE_RETRY_FILES_ENABLED=False
# Use default callback with yaml result format (community.general.yaml was removed in v12.0.0)
ENV ANSIBLE_STDOUT_CALLBACK=default
ENV ANSIBLE_RESULT_FORMAT=yaml

# Anthropic API key must be provided at runtime via: docker run -e ANTHROPIC_API_KEY=sk-...
# For Ansible network automation, mount your inventory and SSH keys:
#   docker run -v ~/.ssh:/home/aios/.ssh:ro -v ./inventory:/home/aios/inventory:ro ...

# Default command
CMD ["aios"]
