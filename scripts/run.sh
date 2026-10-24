#!/usr/bin/env bash
# Convenience launcher. Passes all args through to the CLI.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -d .venv ] && source .venv/bin/activate || true
export PYTHONPATH="src:${PYTHONPATH:-}"
exec python3 -m picowave.main "$@"
