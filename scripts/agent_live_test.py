"""Run the example bibliography through the real agent (needs GROQ_API_KEY) and print what happened.

    python scripts/agent_live_test.py                       # model from GROQ_MODEL / .env
    GROQ_MODEL=openai/gpt-oss-120b python scripts/agent_live_test.py "Which ones should I replace?"

Prints the tool-call trace, the final answer, the DOI-grounding verdict, token usage and timing.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bedrock.agent import AuditAgent  # noqa: E402
from bedrock.config import load_settings  # noqa: E402
from bedrock.graph import connect  # noqa: E402
from bedrock.llm import GroqClient, LLMError  # noqa: E402


def main() -> int:
    s = load_settings()
    if not s.groq_api_key:
        print("GROQ_API_KEY is not set in bedrock/.env")
        return 2
    text = json.loads((ROOT / "src" / "bedrock" / "web" / "examples.json").read_text(encoding="utf-8"))["examples"][0]["text"]
    question = " ".join(sys.argv[1:])
    llm = GroqClient(s.groq_api_key, s.groq_model)
    print(f"model: {s.groq_model}\nquestion: {question or '(default)'}\n")
    t = time.time()
    try:
        out = AuditAgent(connect(), llm).run(text, question)
    except LLMError as exc:
        print("LLM ERROR:", exc)
        return 1
    print(f"finished in {time.time() - t:.1f}s  source={out['source']}  usage={out.get('usage')}")
    if out.get("error"):
        print("error:", out["error"])
    print("\n--- trace")
    for tr in out["trace"]:
        print(f"  step {tr['step']}: {tr['tool']}({tr['arguments'][:70]}) -> {tr['result']}  ok={tr['ok']}  {tr['seconds']}s")
    print("\n--- answer\n" + out["answer"])
    print("\n--- verification:", out["verification"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
