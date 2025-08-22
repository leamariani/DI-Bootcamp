import os, json, time
from typing import Any

class LogSink:
    def __init__(self, base_dir: str = None):
        self.base = base_dir or os.environ.get("LOGS_DIR", "./logs")
        os.makedirs(self.base, exist_ok=True)
        self.path = os.path.join(self.base, f"run_{int(time.time())}.jsonl")

    def write(self, kind: str, server: str, tool: str, args: dict, output: Any, elapsed: float, success: bool):
        rec = {
            "ts": time.strftime('%Y-%m-%dT%H:%M:%S'),
            "kind": kind,
            "server": server,
            "tool": tool,
            "args": _redact(args),
            "output_summary": _summ(output),
            "elapsed_s": round(elapsed, 3),
            "success": success
        }
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

def _summ(o: Any) -> str:
    t = json.dumps(o, ensure_ascii=False) if not isinstance(o, str) else o
    return (t[:700] + "…") if len(t) > 700 else t

def _redact(d: dict) -> dict:
    HIDDEN = {"api_key", "token", "authorization", "password", "secret", "GROQ_API_KEY"}
    return {k: ("***" if k.lower() in HIDDEN else v) for k, v in d.items()}
