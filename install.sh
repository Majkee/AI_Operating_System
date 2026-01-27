#!/usr/bin/env bash
# AIOS Installer — https://github.com/Majkee/AI_Operating_System
# Usage:  curl -fsSL https://raw.githubusercontent.com/Majkee/AI_Operating_System/master/install.sh | bash
#
# What this script does:
#   1. Checks that Python >= 3.10 is available
#   2. Creates a virtual environment at ~/.local/share/aios
#   3. Installs the "aiosys" package from PyPI
#   4. Symlinks the "aios" binary into ~/.local/bin
#   5. Ensures ~/.local/bin is on PATH
#   6. Optionally prompts for an Anthropic API key
#
# The script is idempotent — safe to re-run.

set -euo pipefail

# ── Colours (disabled when piped) ────────────────────────────────────────────
if [ -t 1 ]; then
    GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; BOLD='\033[1m'; RESET='\033[0m'
else
    GREEN=''; YELLOW=''; RED=''; BOLD=''; RESET=''
fi

info()  { printf "${GREEN}[aios]${RESET} %s\n" "$*"; }
warn()  { printf "${YELLOW}[aios]${RESET} %s\n" "$*"; }
error() { printf "${RED}[aios]${RESET} %s\n" "$*" >&2; }
die()   { error "$@"; exit 1; }

# ── Detect OS ────────────────────────────────────────────────────────────────
detect_os() {
    case "$(uname -s)" in
        Linux*)  OS="linux";;
        Darwin*) OS="macos";;
        *)       die "Unsupported operating system: $(uname -s). AIOS requires Linux or macOS.";;
    esac
    info "Detected OS: $OS"
}

# ── Check Python ─────────────────────────────────────────────────────────────
find_python() {
    for cmd in python3 python; do
        if command -v "$cmd" &>/dev/null; then
            PYTHON="$(command -v "$cmd")"
            break
        fi
    done

    if [ -z "${PYTHON:-}" ]; then
        die "Python not found. Please install Python 3.10+ first."
    fi

    # Verify version >= 3.10
    PY_VERSION="$("$PYTHON" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
    PY_MAJOR="$("$PYTHON" -c 'import sys; print(sys.version_info.major)')"
    PY_MINOR="$("$PYTHON" -c 'import sys; print(sys.version_info.minor)')"

    if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
        die "Python >= 3.10 is required (found $PY_VERSION). Please upgrade."
    fi

    info "Using $PYTHON ($PY_VERSION)"
}

# ── Install ──────────────────────────────────────────────────────────────────
INSTALL_DIR="${HOME}/.local/share/aios"
BIN_DIR="${HOME}/.local/bin"

install_aios() {
    info "Installing AIOS into ${INSTALL_DIR} ..."

    # Create / refresh virtual environment
    if [ -d "$INSTALL_DIR" ]; then
        info "Existing installation found — upgrading."
    fi
    "$PYTHON" -m venv "$INSTALL_DIR"

    # Upgrade pip inside the venv (suppress output)
    "$INSTALL_DIR/bin/pip" install --upgrade pip >/dev/null 2>&1

    # Install the package
    "$INSTALL_DIR/bin/pip" install --upgrade aiosys

    info "Package installed."
}

link_binary() {
    mkdir -p "$BIN_DIR"

    # Symlink (or overwrite)
    ln -sf "$INSTALL_DIR/bin/aios" "$BIN_DIR/aios"

    info "Linked aios -> $BIN_DIR/aios"
}

ensure_path() {
    case ":${PATH}:" in
        *":${BIN_DIR}:"*) return;;  # already on PATH
    esac

    warn "$BIN_DIR is not on your PATH."

    # Determine shell config file
    SHELL_RC=""
    case "${SHELL:-}" in
        */zsh)  SHELL_RC="$HOME/.zshrc";;
        */bash) SHELL_RC="$HOME/.bashrc";;
        *)
            if [ -f "$HOME/.bashrc" ]; then SHELL_RC="$HOME/.bashrc";
            elif [ -f "$HOME/.zshrc" ]; then SHELL_RC="$HOME/.zshrc";
            fi
            ;;
    esac

    if [ -n "$SHELL_RC" ]; then
        EXPORT_LINE='export PATH="${HOME}/.local/bin:${PATH}"'
        if ! grep -qF '.local/bin' "$SHELL_RC" 2>/dev/null; then
            printf '\n# Added by AIOS installer\n%s\n' "$EXPORT_LINE" >> "$SHELL_RC"
            info "Added $BIN_DIR to PATH in $SHELL_RC"
            warn "Run 'source $SHELL_RC' or open a new terminal for this to take effect."
        fi
    else
        warn "Could not detect shell config. Add this to your profile manually:"
        warn "  export PATH=\"\${HOME}/.local/bin:\${PATH}\""
    fi
}

prompt_api_key() {
    # Skip if stdin is not a terminal (piped install) or key already set
    if [ ! -t 0 ]; then return; fi
    if [ -n "${ANTHROPIC_API_KEY:-}" ]; then
        info "ANTHROPIC_API_KEY already set in environment."
        return
    fi

    CONFIG_DIR="${HOME}/.config/aios"
    CONFIG_FILE="${CONFIG_DIR}/config.toml"
    if [ -f "$CONFIG_FILE" ] && grep -q 'api_key' "$CONFIG_FILE" 2>/dev/null; then
        info "API key already configured in $CONFIG_FILE."
        return
    fi

    printf "\n"
    info "AIOS needs an Anthropic API key to work."
    info "Get one at: https://console.anthropic.com/"
    printf "\n"
    printf "${BOLD}Enter your API key (or press Enter to skip): ${RESET}"
    read -r API_KEY

    if [ -n "$API_KEY" ]; then
        mkdir -p "$CONFIG_DIR"
        printf '[api]\napi_key = "%s"\n\nsetup_complete = true\n' "$API_KEY" > "$CONFIG_FILE"
        chmod 600 "$CONFIG_FILE"
        info "API key saved to $CONFIG_FILE (permissions: 600)."
    else
        info "Skipped. Set ANTHROPIC_API_KEY or run 'aios --setup' later."
    fi
}

# ── Main ─────────────────────────────────────────────────────────────────────
main() {
    printf "\n${BOLD}AIOS Installer${RESET}\n\n"

    detect_os
    find_python
    install_aios
    link_binary
    ensure_path
    prompt_api_key

    printf "\n${GREEN}${BOLD}Installation complete!${RESET}\n"
    info "Run ${BOLD}aios${RESET} to start."
    printf "\n"
}

main "$@"
