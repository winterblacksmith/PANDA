"""Model-written answers for data results, checked against the verified numbers.

PANDA's Python/SQL tools compute the facts; the model writes the answer. Every
number in the model's answer must match a verified fact (allowing rounding such
as "68k" for 68,211), otherwise the model is asked once to correct itself. A
template is used only when no model is reachable, and then it says so.
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

AI_UNAVAILABLE_PREFIX = "AI answer unavailable right now, so here is PANDA's verified result: "

_NUMBER = re.compile(
    r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?\s*(%|percent|k\b|thousand|m\b|million|b\b|billion)?",
    re.IGNORECASE,
)
_MULTIPLIERS = {"k": 1e3, "thousand": 1e3, "m": 1e6, "million": 1e6, "b": 1e9, "billion": 1e9}

SYSTEM = """You are PANDA (PERSEUS AI for Natural-language Data Analysis), a forestry data assistant.
PANDA's own Python and SQL tools already computed the verified facts below. Write the answer to the user's question from them.
Rules:
- Use only numbers that appear in the verified facts. Do not recalculate, extrapolate or invent numbers, causes or trends.
- Rounding is fine (e.g. 68,211 -> about 68,000), but never change a number's meaning.
- Answer the question first, in plain language, then add the one or two most useful details.
- If something the user asked for could not be done (for example a map), say so plainly, explain why from the facts, and say what would make it possible.
- Do not mention JSON, internal field names, SQL or "verified facts". Do not repeat the question.
- Keep it short: 2-5 sentences, or a short list when listing items."""


def numbers_in(text: str) -> List[float]:
    values = []
    for match in _NUMBER.finditer(text or ""):
        whole, fraction, unit = match.groups()
        value = float(whole.replace(",", "") + ("." + fraction if fraction else ""))
        if unit and unit.lower() in _MULTIPLIERS:
            value *= _MULTIPLIERS[unit.lower()]
        values.append(value)
    return values


def _fact_numbers(facts_text: str) -> List[float]:
    numbers = set(numbers_in(facts_text))
    # Allow simple derived forms the model may reasonably state.
    for value in list(numbers):
        numbers.add(round(value))
        numbers.add(value * 100)  # fraction -> percent
        numbers.add(value / 100)
    return sorted(numbers)


def unsupported_numbers(answer: str, facts_text: str, small: float = 12) -> List[float]:
    """Numbers in the answer that don't match any verified fact within rounding."""
    facts = _fact_numbers(facts_text)
    bad = []
    for value in numbers_in(answer):
        if value <= small:
            continue
        tolerance = lambda f: max(abs(f) * 0.02, 0.06)  # noqa: E731  ~2% covers "about 68,000" / "1.65 billion"
        if not any(abs(value - f) <= tolerance(f) for f in facts):
            bad.append(value)
    return bad


def grounded_answer(chat: Callable[..., str], model: str, question: str, facts: Dict[str, Any],
                    fallback: str, dataset_context: str = "", instruction: str = "",
                    history: Iterable[Dict[str, str]] = ()) -> Tuple[str, bool]:
    """Return (answer, ai_generated). `chat(model, messages, options=...)` returns text or ''."""
    facts_text = json.dumps(facts, ensure_ascii=False, indent=1, default=str)
    context = facts_text + ("\n" + dataset_context if dataset_context else "")
    system = SYSTEM + (f"\n{instruction.strip()}" if instruction else "")
    if dataset_context:
        system += "\n\nSelected dataset profile (for describing columns; not query results):\n" + dataset_context[:4000]
    messages: List[Dict[str, str]] = [{"role": "system", "content": system}]
    messages += [m for m in list(history)[-4:] if m.get("role") in {"user", "assistant"} and m.get("content")]
    messages.append({"role": "user", "content": f"Question: {question}\n\nVerified facts:\n{facts_text}"})

    options = {"temperature": 0.3, "num_predict": 700}
    answer = (chat(model, messages, options=options) or "").strip()
    if not answer:
        return AI_UNAVAILABLE_PREFIX + fallback, False
    bad = unsupported_numbers(answer, context)
    if bad:
        retry = messages + [
            {"role": "assistant", "content": answer},
            {"role": "user", "content": "These numbers in your answer are not in the verified facts: "
             + ", ".join(f"{b:,g}" for b in bad[:6])
             + ". Rewrite the answer using only numbers from the verified facts."},
        ]
        corrected = (chat(model, retry, options=options) or "").strip()
        if corrected and not unsupported_numbers(corrected, context):
            return corrected, True
        return fallback, False
    return answer, True
