import os, json, asyncio, time
from contextlib import AsyncExitStack
from typing import Dict, Any, List, Tuple
from dotenv import load_dotenv
from app.llm_client import build_llm, PLANNER_SCHEMA
from app.log_utils import LogSink

from mcp import ClientSession, Tool
from mcp.client.stdio import stdio_client
from mcp.client import StdioServerParameters

load_dotenv()

class MCPHub:
    def __init__(self, config: Dict[str, Any]):
        self.cfg = config
        self.sessions: Dict[str, ClientSession] = {}
        self.exit_stack = AsyncExitStack()
        self.tools: Dict[Tuple[str,str], Tool] = {}

    async def start(self):
        for name, desc in self.cfg.items():
            cmd = desc["command"]
            args = [self._expand(a) for a in desc.get("args", [])]
            params = StdioServerParameters(command=cmd, args=args)
            read_stream, write_stream = await stdio_client(params)
            session = ClientSession(read_stream, write_stream)
            await self.exit_stack.enter_async_context(session)
            await session.initialize()
            self.sessions[name] = session
            resp = await session.list_tools()
            for t in resp.tools:
                self.tools[(name, t.name)] = t

    async def stop(self):
        await self.exit_stack.aclose()

    async def call(self, server: str, tool: str, args: Dict[str, Any]) -> Any:
        session = self.sessions[server]
        return await asyncio.wait_for(session.call_tool(tool, args), timeout=120)

    def available_tools_spec(self) -> str:
        lines = []
        for (srv, name), t in self.tools.items():
            desc = t.description or ""
            lines.append(f"- {srv}.{name}: {desc}")
        return "\\n".join(lines)

    def _expand(self, s: str) -> str:
        return os.path.expandvars(s)

class Orchestrator:
    def __init__(self, hub: MCPHub, logs: LogSink):
        self.hub = hub
        self.llm = build_llm()
        self.logs = logs

    async def run_goal(self, user_goal: str, max_steps: int = None) -> Dict[str, Any]:
        max_steps = max_steps or int(os.environ.get("MAX_STEPS", 6))
        transcript: List[Dict[str, str]] = [
            {"role":"user","content": user_goal}
        ]
        final_answer = None
        for step in range(1, max_steps+1):
            system = (
              "Tu disposes des outils MCP suivants:\\n" +
              self.hub.available_tools_spec() +
              "\\nDécide du prochain appel d’outil ou fournis la réponse finale. Réponds STRICTEMENT au format JSON.\\n"
              "Stratégie suggérée pour un brief enrichi:\\n"
              "- arxiv.search_papers → arxiv.read_paper pour 2–3 papiers pertinents\\n"
              "- scholarplus.enrich_metadata pour compléter DOI/BibTeX\\n"
              "- cite.assemble_brief puis cite.clean_citations\\n"
              "- scholarplus.generate_bibtex pour les entrées manquantes\\n"
              "- fs.write_file pour sauvegarder le Markdown final"
            )
            plan = self.llm.chat_json(system, transcript, schema=PLANNER_SCHEMA)
            decision = plan.get("decision")
            if decision == "final_answer":
                final_answer = plan.get("notes", "(pas de contenu)")
                break
            action = plan.get("action", {})
            server, tool, args = action.get("server"), action.get("tool"), action.get("args", {})
            t0 = time.time()
            try:
                result = await self.hub.call(server, tool, args)
                elapsed = time.time()-t0
                # result.content existe sur les ToolResponse; sinon fallback str(result)
                content = getattr(result, "content", result)
                try:
                    snippet = json.dumps(content)[:1500]
                except Exception:
                    snippet = str(content)[:1500]
                transcript.append({"role":"assistant","content": f"TOOL {server}.{tool} OK"})
                transcript.append({"role":"user","content": f"Résultat outil (résumé): {snippet}"})
                self.logs.write("tool_call", server, tool, args, content, elapsed, success=True)
            except Exception as e:
                elapsed = time.time()-t0
                msg = f"Erreur {server}.{tool}: {e}"
                transcript.append({"role":"assistant","content": msg})
                self.logs.write("tool_call", server, tool, args, {"error": str(e)}, elapsed, success=False)
                # boucle continue, le LLM adaptera l'étape suivante
                continue
        return {"final": final_answer, "transcript": transcript}
