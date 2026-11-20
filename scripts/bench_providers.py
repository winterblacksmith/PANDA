"""Time each PANDA model provider on the same prompts.

Run from the repo root with the keys you want to test exported, e.g.:

    export GROQ_API_KEY=...  GEMINI_API_KEY=...
    python scripts/bench_providers.py            # groq, gemini, local
    python scripts/bench_providers.py groq gemini

Each provider is called directly (no fallback), so a failure is reported as a
failure instead of silently using the next provider. Keys are never printed.
"""

from __future__ import annotations

import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import llm_client  # noqa: E402

LOCAL_MODEL = llm_client.os.environ.get("PANDA_OLLAMA_MODEL", llm_client.DEFAULT_MODEL)

PROMPTS = {
    "short": "Reply with the words PANDA model connected.",
    "forestry": (
        "A forest dataset has 20,069 stands covering 873,483.5 acres. Stand ages "
        "are mostly 20-60 years and TCuFt is cubic-foot volume per acre. In about "
        "120 words, explain to a land manager what an acreage-by-age chart would "
        "show and one caution about simulated ages."
    ),
}
RUNS = 3


def call(provider: str, prompt: str) -> tuple[float, str]:
    messages = [{"role": "user", "content": prompt}]
    options = {"num_predict": 300, "temperature": 0.2}
    start = time.perf_counter()
    if provider in llm_client.HOSTED_PROVIDERS:
        result = llm_client._hosted_chat(provider, messages, options, timeout=90)
    else:
        result = llm_client._local_chat(LOCAL_MODEL, messages, options, timeout=180)
        if not isinstance(result, dict):
            result = result.model_dump()
    elapsed = time.perf_counter() - start
    return elapsed, str(result["message"]["content"]).strip()


def main() -> None:
    providers = sys.argv[1:] or ["groq", "gemini", "local"]
    for provider in providers:
        if provider in llm_client.HOSTED_PROVIDERS and not llm_client._hosted_key(provider):
            print(f"\n== {provider}: skipped ({llm_client.HOSTED_PROVIDERS[provider]['key_env']} not set)")
            continue
        model = llm_client.hosted_model(provider) if provider in llm_client.HOSTED_PROVIDERS else LOCAL_MODEL
        print(f"\n== {llm_client.provider_label(provider)} ({model})")
        for name, prompt in PROMPTS.items():
            times, sample = [], ""
            for _ in range(RUNS):
                try:
                    elapsed, text = call(provider, prompt)
                except llm_client.LLMConnectionError as exc:
                    print(f"  {name}: FAILED - {exc}")
                    break
                times.append(elapsed)
                sample = text
                llm_client.reset_cooldowns()
            if times:
                print(f"  {name}: median {statistics.median(times):.2f}s, "
                      f"first {times[0]:.2f}s, words {len(sample.split())}")
        if sample:
            print(f"  sample answer: {sample[:300]}{'...' if len(sample) > 300 else ''}")


if __name__ == "__main__":
    main()
