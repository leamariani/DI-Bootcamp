import os, json, httpx
from typing import List, Dict, Any, Optional

class LLM:
    def chat_json(self, system: str, messages: List[Dict[str, str]], schema: Optional[Dict]=None) -> Dict:
        raise NotImplementedError

class GroqLLM(LLM):
    def __init__(self, model: str):
        from groq import Groq
        self.client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
        self.model = model

    def chat_json(self, system, messages, schema=None) -> Dict:
        resp_fmt = {"type": "json_object"}
        if schema:
            resp_fmt = {"type": "json_schema", "json_schema": {"name":"planner","schema": schema}}
        r = self.client.chat.completions.create(
            model=self.model,
            temperature=0,
            response_format=resp_fmt,
            messages=[
                {"role":"system","content": system},
                *messages
            ]
        )
        text = r.choices[0].message.content
        return json.loads(text)

class OllamaLLM(LLM):
    def __init__(self, model: str, host: str="http://localhost:11434"):
        self.model = model
        self.host = host.rstrip("/")

    def chat_json(self, system, messages, schema=None) -> Dict:
        payload = {
            "model": self.model,
            "messages": [{"role":"system","content":system}, *messages],
            "stream": False
        }
        if schema:
            payload["format"] = schema  # JSON Schema
        with httpx.Client(timeout=90.0) as c:
            r = c.post(f"{self.host}/api/chat", json=payload)
            r.raise_for_status()
            data = r.json()
            text = data["message"]["content"]
            return json.loads(text)

def build_llm() -> LLM:
    backend = os.environ.get("LLM_BACKEND", "groq").lower()
    if backend == "ollama":
        return OllamaLLM(
            model=os.environ.get("OLLAMA_MODEL", "llama3.1"),
            host=os.environ.get("OLLAMA_HOST", "http://localhost:11434"),
        )
    else:
        return GroqLLM(model=os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"))

PLANNER_SCHEMA = {
  "type": "object",
  "properties": {
    "decision": {"type":"string", "enum":["call_tool","final_answer"]},
    "action": {
      "type":"object",
      "properties": {
        "server": {"type":"string"},
        "tool": {"type":"string"},
        "args": {"type":"object"}
      },
      "required":["server","tool","args"]
    },
    "notes": {"type":"string"}
  },
  "required":["decision"]
}
