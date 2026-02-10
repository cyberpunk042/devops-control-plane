#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────
# manage.sh — DevOps Control Plane operator console
#
# Interactive TUI menu + direct command invocation.
#
# Usage:
#     ./manage.sh               # Interactive menu
#     ./manage.sh status        # Direct invocation
#     ./manage.sh run test      # Direct invocation with args
#     ./manage.sh --help        # Pass-through to CLI
# ──────────────────────────────────────────────────────────────────

set -euo pipefail

# ── Config ──────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/.venv"
PYTHON="${VENV_DIR}/bin/python"
CLI_MODULE="src.main"

# ── Colors (graceful degradation) ───────────────────────────────

if [[ -t 1 ]] && command -v tput &>/dev/null && [[ $(tput colors 2>/dev/null || echo 0) -ge 8 ]]; then
    BOLD=$(tput bold)
    DIM=$(tput dim)
    RESET=$(tput sgr0)
    CYAN=$(tput setaf 6)
    GREEN=$(tput setaf 2)
    YELLOW=$(tput setaf 3)
    RED=$(tput setaf 1)
    BLUE=$(tput setaf 4)
    MAGENTA=$(tput setaf 5)
else
    BOLD="" DIM="" RESET=""
    CYAN="" GREEN="" YELLOW="" RED="" BLUE="" MAGENTA=""
fi

# ── Helpers ─────────────────────────────────────────────────────

banner() {
    echo ""
    echo "${BLUE}${BOLD}  ⚡ DevOps Control Plane${RESET}"
    echo "${DIM}  ──────────────────────────────────────${RESET}"
    echo ""
}

info()  { echo "${CYAN}  ▸${RESET} $*"; }
ok()    { echo "${GREEN}  ✓${RESET} $*"; }
warn()  { echo "${YELLOW}  ⚠${RESET} $*"; }
err()   { echo "${RED}  ✗${RESET} $*" >&2; }

check_venv() {
    if [[ ! -f "${PYTHON}" ]]; then
        err "Virtual environment not found at ${VENV_DIR}"
        info "Run: python3 -m venv .venv && pip install -e '.[dev]'"
        exit 1
    fi
}

run_cli() {
    "${PYTHON}" -m "${CLI_MODULE}" "$@"
}

# ── Menu ────────────────────────────────────────────────────────

show_menu() {
    echo "  ${BOLD}Commands${RESET}"
    echo ""
    echo "  ${CYAN}1${RESET})  ${BOLD}status${RESET}       — Project status overview"
    echo "  ${CYAN}2${RESET})  ${BOLD}detect${RESET}       — Scan for modules & stacks"
    echo "  ${CYAN}3${RESET})  ${BOLD}run test${RESET}     — Run tests (mock)"
    echo "  ${CYAN}4${RESET})  ${BOLD}run lint${RESET}     — Run linter (mock)"
    echo "  ${CYAN}5${RESET})  ${BOLD}health${RESET}       — System health check"
    echo "  ${CYAN}6${RESET})  ${BOLD}config check${RESET} — Validate project.yml"
    echo "  ${CYAN}7${RESET})  ${BOLD}web${RESET}          — Start web dashboard"
    echo ""
    echo "  ${DIM}q)  quit${RESET}"
    echo ""
}

handle_choice() {
    case "$1" in
        1)  run_cli status ;;
        2)  run_cli detect ;;
        3)  run_cli run test --mock ;;
        4)  run_cli run lint --mock ;;
        5)  run_cli health ;;
        6)  run_cli config check ;;
        7)  run_cli web --mock ;;
        q|Q|exit)
            echo ""
            ok "Goodbye!"
            echo ""
            exit 0
            ;;
        *)
            warn "Unknown option: $1"
            ;;
    esac
}

interactive_loop() {
    banner
    while true; do
        show_menu
        printf "  ${MAGENTA}❯${RESET} "
        if ! read -r choice; then
            # EOF (piped input, CI, etc.)
            echo ""
            exit 0
        fi
        echo ""

        if [[ -z "${choice}" ]]; then
            continue
        fi

        handle_choice "${choice}"
        echo ""
    done
}

# ── Main ────────────────────────────────────────────────────────

main() {
    check_venv

    # Direct invocation: pass all args to CLI
    if [[ $# -gt 0 ]]; then
        run_cli "$@"
        exit $?
    fi

    # No args: interactive menu
    # Check if we have a TTY
    if [[ ! -t 0 ]]; then
        err "No TTY detected. Use direct invocation: ./manage.sh <command>"
        info "Examples:"
        info "  ./manage.sh status"
        info "  ./manage.sh detect"
        info "  ./manage.sh run test --mock"
        info "  ./manage.sh --help"
        exit 1
    fi

    interactive_loop
}

main "$@"
