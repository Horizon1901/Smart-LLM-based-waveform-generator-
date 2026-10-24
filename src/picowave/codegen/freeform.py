"""Optional freeform C generation.

This is the *opt-in* path (``--mode llm-freeform``): the LLM writes the whole C
program from the manufacturer reference. It is intentionally NOT the default,
because a small local model will sometimes emit non-compiling driver code. The
pipeline wraps this in compile -> capture-errors -> rollback -> retry, which is
where freehand generation belongs.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from ..intent import Intent
from ..llm.prompts import FREEFORM_SYSTEM_PROMPT, build_freeform_prompt
from .generator import GenerationResult


def _manufacturer_reference(manufacturer_c: Path, max_chars: int = 6000) -> str:
    """Extract a compact API reference: the ps2000_* prototypes actually used
    plus two short manufacturer function bodies, capped to keep the prompt small.
    """
    text = manufacturer_c.read_text(encoding="utf-8", errors="ignore")
    calls = sorted(set(re.findall(r"ps2000_[a-zA-Z_]+", text)))
    ref = ["Available ps2000 API functions (use only these):"]
    ref += [f"  {c}" for c in calls]
    # Include the immediate-block example as a usage pattern.
    m = re.search(r"void collect_block_immediate.*?\n\}", text, re.DOTALL)
    if m:
        ref.append("\nExample usage pattern (collect_block_immediate):")
        ref.append(m.group(0))
    out = "\n".join(ref)
    return out[:max_chars]


class FreeformGenerator:
    def __init__(self, llm, manufacturer_c: Path, generated_dir: Path,
                 next_id_fn):
        self.llm = llm
        self.manufacturer_c = manufacturer_c
        self.generated_dir = generated_dir
        self.next_id_fn = next_id_fn  # reuse CodeGenerator.next_gen_id

    @staticmethod
    def _strip_fences(text: str) -> str:
        t = text.strip()
        if t.startswith("```"):
            t = re.sub(r"^```[a-zA-Z]*\n", "", t)
            t = re.sub(r"\n```$", "", t)
        return t

    def generate(self, intent: Intent, temperature: float = 0.0) -> GenerationResult:
        reference = _manufacturer_reference(self.manufacturer_c)
        prompt = build_freeform_prompt(intent.raw_text, reference)
        raw = self.llm.generate(FREEFORM_SYSTEM_PROMPT, prompt,
                                temperature=temperature, force_json=False)
        source = self._strip_fences(raw)

        header = (
            f"/* GENERATED (freeform) at "
            f"{datetime.now().isoformat(timespec='seconds')} */\n"
        )
        gid = self.next_id_fn()
        out_path = self.generated_dir / f"acquisition_{gid}.c"
        out_path.write_text(header + source, encoding="utf-8")
        return GenerationResult(gen_id=gid, path=out_path,
                                action=intent.action, template="llm-freeform")
