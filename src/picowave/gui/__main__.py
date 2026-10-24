"""Launch the desktop GUI:  python -m picowave.gui [options].

The CLI (python -m picowave.main) is unaffected; this is an additional interface.
"""
from __future__ import annotations

import argparse
import sys

from . import run


def main() -> int:
    p = argparse.ArgumentParser(prog="picowave.gui",
                                description="LLM Project desktop GUI")
    p.add_argument("--sdk", choices=["mock", "real"], default=None,
                   help="link the offline mock SDK or the real PicoSDK "
                        "(overrides any saved setting; omit to use the last "
                        "saved choice, or mock if none saved)")
    p.add_argument("--llm", choices=["auto", "ollama", "mock"], default=None,
                   help="LLM backend selection (overrides any saved setting)")
    p.add_argument("--mode", choices=["template", "llm-freeform"],
                   default="template", help="code-generation mode")
    args = p.parse_args()
    return run(sdk_mode=args.sdk, llm_choice=args.llm, mode=args.mode)


if __name__ == "__main__":
    sys.exit(main())
