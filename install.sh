#!/data/data/com.termux/files/usr/bin/bash
#
# Codey-OS — Full Installation Script
#
# Installs everything needed to run Codey-OS on Termux (Android) or Linux:
#   • System packages (pkg / apt / dnf / pacman)
#   • Python dependencies
#   • llama.cpp (built from source)
#   • Both models:
#       Qwen3.5-4B — the single model for every role (coder + planner,
#                    thinking mode replaces the old dedicated planner —
#                    see CODEY_MASTER_PLAN.md M1). Quantized by Unsloth
#                    (huggingface.co/unsloth/Qwen3.5-4B-GGUF) —
#                    confirmed 2026-08-23 via the on-device GGUF's own
#                    general.quantized_by/base_model.0.* metadata
#                    (gguf_dump.py --no-tensors) AND a live HTTP request
#                    (curl -I) against the resulting URL, which resolved
#                    (302 → HF's CDN) with the exact requested filename
#                    in the response's content-disposition header — not
#                    inferred from the model-family name alone (rule 12).
#       Embed      — nomic-embed-text-v1.5 Q4_K_M    (nomic-ai HF)
#   • PATH, executable bits, daemon directory
#
# Retired models NOT installed by this script (M1, 2026-08-23):
#   Qwen2.5-Coder-1.5B (former dedicated planner) — no code path loads it
#   anymore; core/planner_loader.py that used to load it is deleted.
#   Qwen2.5-Coder-7B (former single coder model) — no code path loads a
#   downloaded GGUF of this model anymore either. Its ModelArch constant
#   (core/resource_gate.py QWEN25_7B_ARCH) is kept in-code purely as a
#   legacy comparison fixture for tests/test_resource_gate.py — it has no
#   dependency on an on-disk model file, so nothing here needs to fetch
#   the file it once described.
#
# Usage:
#   ./install.sh           — interactive
#   ./install.sh --yes     — non-interactive (CI / automation)
#

set -e

# ── Colors ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# ── Paths ─────────────────────────────────────────────────────────────────────
CODEY_OS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LLAMA_CPP_DIR="$HOME/llama.cpp"
MODELS_DIR="$HOME/models"
PRIMARY_MODEL_DIR="$MODELS_DIR/qwen3.5-4b-instruct"
EMBED_MODEL_DIR="$MODELS_DIR/nomic-embed"

# Filenames — must match utils/config.py's MODEL_PATH/PLANNER_MODEL_PATH
# exactly (both now point at this same file, M1-B, 2026-08-23).
PRIMARY_MODEL_FILE="Qwen3.5-4B-Q4_K_M.gguf"
EMBED_MODEL_FILE="nomic-embed-text-v1.5.Q4_K_M.gguf"

# ── Model URLs ────────────────────────────────────────────────────────────────
# Qwen3.5-4B — the single model for every role. Verified 2026-08-23 (see
# comment at the top of this file for how): unsloth's GGUF repo,
# quantized_by=Unsloth, base model Qwen/Qwen3.5-4B.
PRIMARY_MODEL_URL="https://huggingface.co/unsloth/Qwen3.5-4B-GGUF/resolve/main/Qwen3.5-4B-Q4_K_M.gguf"

# Embedding model — nomic-ai HF
EMBED_MODEL_URL="https://huggingface.co/nomic-ai/nomic-embed-text-v1.5-GGUF/resolve/main/nomic-embed-text-v1.5.Q4_K_M.gguf"

# ── Helpers ───────────────────────────────────────────────────────────────────
print_status()  { echo -e "${BLUE}[INFO]${NC} $1"; }
print_success() { echo -e "${GREEN}[OK]${NC}   $1"; }
print_warning() { echo -e "${YELLOW}[WARN]${NC} $1"; }
print_error()   { echo -e "${RED}[ERR]${NC}  $1"; }
print_step()    { echo; echo -e "${CYAN}${BOLD}── $1 ──${NC}"; }

is_termux() { [ -d "/data/data/com.termux" ]; }

# ── 1. Environment check ──────────────────────────────────────────────────────
check_termux() {
    print_step "Environment"
    if is_termux; then
        print_success "Termux detected"
    else
        print_warning "Not Termux — continuing (some paths may need adjustment)"
    fi
}

# ── 2. System packages ────────────────────────────────────────────────────────
install_system_deps() {
    print_step "System packages"

    if is_termux; then
        # Termux pkg doesn't work as root
        if [ "$(id -u)" -eq 0 ]; then
            print_warning "Running as root in Termux — skipping pkg install (run as regular user for full install)"
        else
            pkg update -y
            pkg install -y python cmake ninja clang wget curl git golang sqlite age ruff
            # pyarrow & pandas must come from pkg on Termux (pip wheels fail on aarch64)
            pkg install -y python-pyarrow python-pandas 2>/dev/null \
                || print_warning "python-pyarrow/pandas pkg install failed — pipeline features may not work"
            # espeak (offline TTS engine) + termux-api (TTS/STT via Termux:API,
            # also the live path for core/sysmon.py's battery read — the
            # /sys/class/power_supply/battery/ sysfs path is permission-denied
            # under Termux without root, confirmed on-device Track 3 Phase 5a
            # / 7.4 sub-task A) — voice interface
            pkg install -y espeak termux-api 2>/dev/null \
                || print_warning "espeak/termux-api pkg install failed — voice interface may not work"
            # android-tools (adb) — used by tools/adb_confound_monitor.py
            # (NEW-195/NEW-197) to record screen/foreground-app state
            # during live-verify sessions, so future rounds can rule out
            # concurrent phone use as a confound rather than discover it
            # after the fact.
            pkg install -y android-tools 2>/dev/null \
                || print_warning "android-tools (adb) pkg install failed — live-verify confound monitoring will not work"
        fi
        print_success "Termux packages installed"
    elif command -v apt &>/dev/null; then
        if [ "$(id -u)" -eq 0 ]; then
            apt update -y
            apt install -y python3 python3-pip cmake ninja-build clang wget curl git espeak golang sqlite3 age
        else
            sudo apt update -y
            sudo apt install -y python3 python3-pip cmake ninja-build clang wget curl git espeak golang sqlite3 age
        fi
        print_success "apt packages installed"
    elif command -v dnf &>/dev/null; then
        if [ "$(id -u)" -eq 0 ]; then
            dnf install -y python3 python3-pip cmake ninja clang wget curl git espeak golang sqlite age
        else
            sudo dnf install -y python3 python3-pip cmake ninja clang wget curl git espeak golang sqlite age
        fi
        print_success "dnf packages installed"
    elif command -v pacman &>/dev/null; then
        if [ "$(id -u)" -eq 0 ]; then
            pacman -S --noconfirm python python-pip cmake ninja clang wget curl git espeak-ng go sqlite age
        else
            sudo pacman -S --noconfirm python python-pip cmake ninja clang wget curl git espeak-ng go sqlite age
        fi
        print_success "pacman packages installed"
    else
        print_warning "Package manager not detected — install manually: python3 pip cmake ninja clang wget curl git age"
    fi
}

# ── 3. Python dependencies ────────────────────────────────────────────────────
install_python_deps() {
    print_step "Python dependencies"

    # Upgrade pip (skip on Termux where it's forbidden)
    if ! is_termux; then
        if [ "$(id -u)" -eq 0 ] || [ -n "$SUDO_USER" ]; then
            pip3 install --upgrade pip --break-system-packages 2>/dev/null \
                || pip3 install --upgrade pip
        else
            pip3 install --upgrade pip 2>/dev/null \
                || pip3 install --upgrade pip --user
        fi
    fi

    cd "$CODEY_OS_DIR"

    # Install only what's needed for the core agent
    # (pipeline/training deps are optional — see requirements.txt for full list)
    PIP_INSTALL_ARGS=""
    if [ "$(id -u)" -eq 0 ] || [ -n "$SUDO_USER" ]; then
        PIP_INSTALL_ARGS="--break-system-packages"
    fi

    pip3 install $PIP_INSTALL_ARGS \
        "rich>=14.0.0" \
        "numpy>=1.24.0" \
        "watchdog>=3.0.0" \
        "requests>=2.31.0" \
        "httpx>=0.27.0" \
        "pyyaml>=6.0" \
        "filelock>=3.13.0" \
        "tqdm>=4.65.0" \
        "hnswlib>=0.7.0" \
        "pyttsx3>=2.90" \
        "python-multipart>=0.0.9" \
        "google-cloud-storage==2.11.0" \
        || print_warning "Some pip packages failed — Codey-OS may still work"

    print_success "Core Python packages installed"
    
    # Create documents storage directory
    mkdir -p "$HOME/.codeyOS/restoricon_documents"

    # Offer to install full pipeline deps
    if [ "$SKIP_CONFIRM" = false ]; then
        echo
        read -p "  Install pipeline/training extras? (large download, optional) [y/N] " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            pip3 install $PIP_INSTALL_ARGS -r "$CODEY_OS_DIR/requirements.txt" \
                || print_warning "Some pipeline packages may have failed (normal on Termux)"
        fi
    fi
}

# ── 4. llama.cpp ──────────────────────────────────────────────────────────────
install_llama_cpp() {
    print_step "llama.cpp"

    if [ -f "$LLAMA_CPP_DIR/build/bin/llama-server" ]; then
        print_success "llama-server already built — skipping"
        return 0
    fi

    if [ -d "$LLAMA_CPP_DIR" ]; then
        print_status "Updating existing llama.cpp clone..."
        cd "$LLAMA_CPP_DIR"
        git pull || print_warning "git pull failed — building from existing source"
    else
        print_status "Cloning llama.cpp (shallow)..."
        git clone --depth 1 https://github.com/ggerganov/llama.cpp "$LLAMA_CPP_DIR" || {
            print_error "Failed to clone llama.cpp"
            return 1
        }
    fi

    cd "$LLAMA_CPP_DIR"
    print_status "Building llama.cpp — this takes 5–15 min on mobile..."

    # Use clang on Termux (GCC can't handle bionic's _Nonnull/_Nullable annotations)
    CMAKE_FLAGS="-DBUILD_SHARED_LIBS=OFF -DGGML_NATIVE=OFF -DGGML_FATAL_WARNINGS=OFF -DGGML_ALL_WARNINGS=OFF"
    if is_termux; then
        CMAKE_FLAGS="$CMAKE_FLAGS -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++"
    fi
    
    cmake -B build $CMAKE_FLAGS || {
        print_error "cmake config failed"
        print_warning "Try building manually:"
        print_warning "  cd $LLAMA_CPP_DIR"
        print_warning "  PREFIX=$PREFIX cmake -B build $CMAKE_FLAGS"
        print_warning "  cmake --build build -j\$(nproc)"
        return 1
    }
    
    cmake --build build --config Release -j"$(nproc)" || {
        print_error "Build failed — try closing other apps and re-running"
        print_warning "If build fails on Termux, try:"
        print_warning "  pkg install clang"
        print_warning "  Or build on a desktop Linux system and copy the binary"
        return 1
    }

    if [ -f "$LLAMA_CPP_DIR/build/bin/llama-server" ]; then
        print_success "llama.cpp built successfully"
    else
        print_error "llama-server binary not found after build"
        return 1
    fi
}

# ── 5. Models ─────────────────────────────────────────────────────────────────

check_disk_space() {
    local required_mb="$1" path="$2"
    local available_kb available_mb
    available_kb=$(df -k "$path" 2>/dev/null | tail -1 | awk '{print $4}')
    available_mb=$((available_kb / 1024))
    if [ "$available_mb" -lt "$required_mb" ]; then
        print_warning "Low disk space: need ~${required_mb}MB, have ${available_mb}MB"
        return 1
    fi
    print_success "Disk space OK (${available_mb}MB free)"
}

# download_file <url> <dest> <label>  — returns 0 on success
download_file() {
    local url="$1" output="$2" label="$3"
    print_status "Downloading $label..."
    if command -v wget &>/dev/null; then
        wget --show-progress -c -O "$output" "$url" 2>&1 && return 0
    elif command -v curl &>/dev/null; then
        curl -L -C - -o "$output" "$url" && return 0
    fi
    print_error "Download failed: $label"
    return 1
}

# file_ok <path> <min_bytes>  — returns 0 if file exists and is big enough
file_ok() {
    local path="$1" min="$2"
    [ -f "$path" ] || return 1
    local size
    size=$(stat -c%s "$path" 2>/dev/null || stat -f%z "$path" 2>/dev/null || echo 0)
    [ "$size" -gt "$min" ]
}

download_models() {
    print_step "Models"
    mkdir -p "$PRIMARY_MODEL_DIR" "$EMBED_MODEL_DIR"
    check_disk_space 3000 "$HOME" || true

    local PRIMARY_PATH="$PRIMARY_MODEL_DIR/$PRIMARY_MODEL_FILE"
    local EMBED_PATH="$EMBED_MODEL_DIR/$EMBED_MODEL_FILE"
    local all_present=true

    # ── Qwen3.5-4B model (every role — coder + planner) ─────────────────────
    if file_ok "$PRIMARY_PATH" 2000000000; then
        print_success "Qwen3.5-4B model already present — skipping"
    elif [ -z "$PRIMARY_MODEL_URL" ]; then
        all_present=false
        print_warning "Qwen3.5-4B model URL is not set — no canonical source was found in this repo."
        print_warning "  Download the model yourself and place it at:"
        print_warning "    $PRIMARY_PATH"
        print_warning "  then re-run this script (or just re-run verify_installation)."
    else
        [ -f "$PRIMARY_PATH" ] && rm -f "$PRIMARY_PATH"
        all_present=false
        print_status "Qwen3.5-4B model (~2.55 GiB)"
        if ! download_file "$PRIMARY_MODEL_URL" "$PRIMARY_PATH" "Qwen3.5-4B Q4_K_M"; then
            print_warning "Manual: wget -c '$PRIMARY_MODEL_URL' -O '$PRIMARY_PATH'"
        fi
    fi

    # ── Embedding model ─────────────────────────────────────────────────────
    if file_ok "$EMBED_PATH" 50000000; then
        print_success "Embedding model already present — skipping"
    else
        [ -f "$EMBED_PATH" ] && rm -f "$EMBED_PATH"
        all_present=false
        print_status "Embedding model (~81 MB) — nomic-ai HF"
        download_file "$EMBED_MODEL_URL" "$EMBED_PATH" "nomic-embed-text-v1.5 Q4_K_M" \
            || print_warning "Manual: wget -c '$EMBED_MODEL_URL' -O '$EMBED_PATH'"
    fi

    $all_present && print_success "All models present" || true
}

# ── 6. Executables & PATH ─────────────────────────────────────────────────────
make_executable() {
    print_step "Permissions"
    chmod +x "$CODEY_OS_DIR/codey"
    chmod +x "$CODEY_OS_DIR/codeyOS"
    chmod +x "$CODEY_OS_DIR/codeydOS"
    chmod +x "$CODEY_OS_DIR/codey-start"
    chmod +x "$CODEY_OS_DIR/codey-stop"
    chmod +x "$CODEY_OS_DIR/codey-metrics"
    chmod +x "$CODEY_OS_DIR/install.sh"
    print_success "Executable bits set"
}

setup_daemon_dir() {
    mkdir -p "$HOME/.codeyOS"
    print_success "Daemon directory: $HOME/.codeyOS"
}

setup_config() {
    print_step "Configuration"
    if [ ! -f "$CODEY_OS_DIR/config.json" ] && [ -f "$CODEY_OS_DIR/config.json.example" ]; then
        cp "$CODEY_OS_DIR/config.json.example" "$CODEY_OS_DIR/config.json"
        print_success "Created initial config.json from template"
    else
        print_success "config.json ready"
    fi
}

setup_symlinks() {
    print_step "Symlinks"
    local bin_dir=""
    if [ -n "$PREFIX" ] && [ -w "$PREFIX/bin" ]; then
        bin_dir="$PREFIX/bin"
    elif [ -w "/usr/local/bin" ]; then
        bin_dir="/usr/local/bin"
    elif [ -d "$HOME/bin" ] || mkdir -p "$HOME/bin" 2>/dev/null; then
        bin_dir="$HOME/bin"
    fi

    if [ -n "$bin_dir" ]; then
        for bin_name in codey codey-start codey-stop codey-metrics codeyOS codeydOS; do
            if [ -f "$CODEY_OS_DIR/$bin_name" ]; then
                ln -sf "$CODEY_OS_DIR/$bin_name" "$bin_dir/$bin_name"
            fi
        done
        print_success "Symlinks created in $bin_dir (codey, codey-start, codey-stop, codey-metrics, codeyOS, codeydOS)"
    else
        print_warning "No writable bin directory found for symlinks; relying on PATH in $SHELL_CONFIG"
    fi
}

setup_path() {
    print_step "PATH"

    if [ -n "$ZSH_VERSION" ]; then
        SHELL_CONFIG="$HOME/.zshrc"
    else
        SHELL_CONFIG="$HOME/.bashrc"
    fi

    if grep -q "codeyOS" "$SHELL_CONFIG" 2>/dev/null; then
        print_status "PATH already configured in $SHELL_CONFIG"
    else
        {
            echo ""
            echo "# Codey-OS"
            echo "export PATH=\"$CODEY_OS_DIR:\$PATH\""
        } >> "$SHELL_CONFIG"
        print_success "Added $CODEY_OS_DIR to PATH in $SHELL_CONFIG"
    fi

    export PATH="$CODEY_OS_DIR:$PATH"
    # shellcheck source=/dev/null
    source "$SHELL_CONFIG" 2>/dev/null || true
}

# ── 7. Verify ─────────────────────────────────────────────────────────────────
verify_installation() {
    print_step "Verification"

    command -v python3 &>/dev/null \
        && print_success "python3: $(python3 --version)" \
        || print_error "python3 not found"

    [ -f "$LLAMA_CPP_DIR/build/bin/llama-server" ] \
        && print_success "llama-server: built" \
        || print_warning "llama-server: not found"

    file_ok "$PRIMARY_MODEL_DIR/$PRIMARY_MODEL_FILE" 2000000000 \
        && print_success "Qwen3.5-4B model: ready" \
        || print_warning "Qwen3.5-4B model: missing"

    file_ok "$EMBED_MODEL_DIR/$EMBED_MODEL_FILE" 50000000 \
        && print_success "Embedding model: ready" \
        || print_warning "Embedding model: missing"

    command -v codey        &>/dev/null && print_success "codey:        in PATH"  || print_warning "codey:        not in PATH yet (restart terminal)"
    command -v codeyOS      &>/dev/null && print_success "codeyOS:      in PATH"  || print_warning "codeyOS:      not in PATH yet (restart terminal)"
    command -v codeydOS     &>/dev/null && print_success "codeydOS:     in PATH"  || print_warning "codeydOS:     not in PATH yet (restart terminal)"
    command -v codey-start  &>/dev/null && print_success "codey-start:  in PATH"  || print_warning "codey-start:  not in PATH yet (restart terminal)"
    command -v codey-stop   &>/dev/null && print_success "codey-stop:   in PATH"  || print_warning "codey-stop:   not in PATH yet (restart terminal)"
    command -v codey-metrics &>/dev/null && print_success "codey-metrics: in PATH" || print_warning "codey-metrics: not in PATH yet (restart terminal)"
}

# ── 7.5. Litestream ────────────────────────────────────────────────────────────
install_litestream() {
    print_step "Litestream"
    
    if [ -f "$HOME/go/bin/litestream" ]; then
        print_success "litestream already installed — skipping"
        return 0
    fi
    
    print_status "Installing Litestream (v0.3.13)..."
    if ! command -v go &>/dev/null; then
        print_warning "go compiler not found — skip litestream install"
        return 1
    fi
    
    # Needs to disable CGO on some environments for clean static build, or just let it use defaults
    go install github.com/benbjohnson/litestream/cmd/litestream@v0.3.13 || {
        print_error "Failed to install litestream"
        return 1
    }
    
    print_success "Litestream installed successfully"
}

# ── 8. Completion message ─────────────────────────────────────────────────────
print_completion() {
    echo
    echo -e "${GREEN}${BOLD}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║            CODEY-OS — Installation Complete                  ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"

    echo -e "${CYAN}${BOLD}QUICK START${NC}"
    echo
    echo -e "  Reload shell:     ${BLUE}source $SHELL_CONFIG${NC}"
    echo -e "  One-word start:   ${BLUE}codey${NC}        (launches all services + interactive TUI)"
    echo -e "  Or background:    ${BLUE}codey start${NC}  (daemon + API in background)"
    echo -e "  Stop everything:  ${BLUE}codey stop${NC}"
    echo -e "  Check status:     ${BLUE}codey status${NC}"
    echo
    echo -e "  Individual pieces still work as before:"
    echo -e "  Start daemon:     ${BLUE}codeydOS start${NC}"
    echo -e "  Run Codey:        ${BLUE}codeyOS${NC}"
    echo -e "  Start orchestrator: ${BLUE}codey-start${NC}"
    echo -e "  Stop orchestrator:  ${BLUE}codey-stop${NC}"
    echo

    echo -e "${CYAN}${BOLD}BACKEND SWITCHING  (local models are the default — no key needed)${NC}"
    echo
    echo -e "  Two independent backend selectors (both point at the SAME Qwen3.5-4B"
    echo -e "  model/server as of M1-D — thinking mode replaces the old dedicated"
    echo -e "  planner process, there is no separate port-8081 planner anymore):"
    echo -e "    ${BOLD}CODEY_BACKEND${NC}   — coding agent  (local: port 8080)"
    echo -e "    ${BOLD}CODEY_BACKEND_P${NC} — planner role  (defaults to CODEY_BACKEND)"
    echo -e "  Each can be: ${BOLD}local${NC} | ${BOLD}openrouter${NC} | ${BOLD}unlimitedclaude${NC}"
    echo
    echo -e "  ── ${BOLD}OpenRouter${NC} ─────────────────────────────────────────────────"
    echo -e "    Key:    ${BLUE}https://openrouter.ai/keys${NC}"
    echo -e "    ${BLUE}export OPENROUTER_API_KEY=\"sk-or-...\"${NC}"
    echo
    echo -e "    # Route both agent and planner to OpenRouter:"
    echo -e "    ${BLUE}export CODEY_BACKEND=\"openrouter\"${NC}"
    echo
    echo -e "    # Override the coding-role model (default: qwen/qwen-2.5-coder-7b-instruct):"
    echo -e "    ${BLUE}export OPENROUTER_MODEL=\"anthropic/claude-sonnet-4-5\"${NC}"
    echo
    echo -e "    # Override the planner-role model independently (default: same as OPENROUTER_MODEL):"
    echo -e "    ${BLUE}export OPENROUTER_PLANNER_MODEL=\"meta-llama/llama-3.2-1b-instruct:free\"${NC}"
    echo
    echo -e "  ── ${BOLD}UnlimitedClaude${NC} ──────────────────────────────────────────────"
    echo -e "    ${BLUE}export UNLIMITEDCLAUDE_API_KEY=\"your-key\"${NC}"
    echo
    echo -e "    # Route both agent and planner:"
    echo -e "    ${BLUE}export CODEY_BACKEND=\"unlimitedclaude\"${NC}"
    echo
    echo -e "    # Override the coding-role model (default: qwen3-coder-next):"
    echo -e "    ${BLUE}export UNLIMITEDCLAUDE_MODEL=\"claude-sonnet-4-5\"${NC}"
    echo
    echo -e "    # Override the planner-role model independently (default: claude-haiku-4.5):"
    echo -e "    ${BLUE}export UNLIMITEDCLAUDE_PLANNER_MODEL=\"claude-haiku-4-5\"${NC}"
    echo
    echo -e "  ── ${BOLD}Mix backends${NC} (most flexible) ───────────────────────────────"
    echo -e "    # e.g. Qwen3.5-4B runs locally, planner role goes to OpenRouter:"
    echo -e "    ${BLUE}export CODEY_BACKEND=\"local\"${NC}"
    echo -e "    ${BLUE}export CODEY_BACKEND_P=\"openrouter\"${NC}"
    echo -e "    ${BLUE}export OPENROUTER_PLANNER_MODEL=\"meta-llama/llama-3.2-1b-instruct:free\"${NC}"
    echo
    echo -e "  ── ${BOLD}Back to local${NC} ────────────────────────────────────────────────"
    echo -e "    ${BLUE}unset CODEY_BACKEND CODEY_BACKEND_P${NC}   # local is always the default"
    echo
    echo -e "  ${YELLOW}Permanent: add exports to ${BLUE}~/.bashrc${YELLOW} then run ${BLUE}source ~/.bashrc${NC}"
    echo

    echo -e "${CYAN}${BOLD}MODEL LOCATIONS${NC}"
    echo -e "  Qwen3.5-4B (coder + planner): ${BLUE}$PRIMARY_MODEL_DIR/$PRIMARY_MODEL_FILE${NC}"
    echo -e "  Embed:                        ${BLUE}$EMBED_MODEL_DIR/$EMBED_MODEL_FILE${NC}"
    echo
    echo -e "  If any model is missing, resume with:"
    if [ -n "$PRIMARY_MODEL_URL" ]; then
        echo -e "  ${BLUE}wget -c '$PRIMARY_MODEL_URL' -O '$PRIMARY_MODEL_DIR/$PRIMARY_MODEL_FILE'${NC}"
    else
        echo -e "  ${YELLOW}Qwen3.5-4B: no download URL known — see the comment at the top of${NC}"
        echo -e "  ${YELLOW}install.sh (PRIMARY_MODEL_URL) — place the file manually at:${NC}"
        echo -e "  ${BLUE}    $PRIMARY_MODEL_DIR/$PRIMARY_MODEL_FILE${NC}"
    fi
    echo -e "  ${BLUE}wget -c '$EMBED_MODEL_URL' -O '$EMBED_MODEL_DIR/$EMBED_MODEL_FILE'${NC}"
    echo
}

# ── Main ──────────────────────────────────────────────────────────────────────
main() {
    SKIP_CONFIRM=false
    for arg in "$@"; do
        [ "$arg" = "--yes" ] || [ "$arg" = "-y" ] && SKIP_CONFIRM=true && break
    done

    echo -e "${BLUE}${BOLD}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║           Codey-OS Installation Script                       ║"
    echo "║   Persistent local AI coding agent for Termux / Android      ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
    echo "  Download: ~2.55 GiB (Qwen3.5-4B) + ~81 MB (embed model) + ~500 MB (llama.cpp build)"
    echo "  Build time: 5–15 min on mobile"
    echo

    if [ "$SKIP_CONFIRM" = false ]; then
        read -p "  Continue? [Y/n] " -n 1 -r; echo
        [[ $REPLY =~ ^[Nn]$ ]] && { echo "Cancelled."; exit 0; }
    else
        echo "  Non-interactive mode."
    fi

    check_termux
    install_system_deps
    install_python_deps

    if ! install_llama_cpp; then
        print_warning "llama.cpp build failed — Codey-OS will not work without llama-server"
        print_warning "You can try building manually later or install from a package manager"
        print_warning "Continuing with model downloads..."
    fi

    download_models || print_warning "Some models failed — re-run to resume (wget -c is used)"

    make_executable
    setup_daemon_dir
    setup_config
    setup_path
    setup_symlinks
    install_litestream
    verify_installation
    print_completion
}

main "$@"
