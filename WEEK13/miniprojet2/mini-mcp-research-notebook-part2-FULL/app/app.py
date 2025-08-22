import asyncio, os
import streamlit as st
from app.config import load_mcp_config
from app.orchestrator import MCPHub, Orchestrator
from app.log_utils import LogSink

st.set_page_config(page_title="MCP Research Notebook", layout="wide")
st.title("MCP Research Notebook")
st.write("Saisissez un objectif de recherche (ex. \"Transformer-based retrieval for code search since 2023\").")
mode = st.selectbox("Mode", ["Brief standard", "Brief enrichi (métadonnées + BibTeX)"])
outfile = st.text_input("Nom du fichier de sortie", value="brief.md")

user_goal = st.text_input("Objectif de recherche")
run = st.button("Lancer l'agent")

if "last_run" not in st.session_state:
    st.session_state.last_run = None

if run and user_goal:
    cfg = load_mcp_config()
    logs = LogSink()
    hub = MCPHub(cfg)
    async def _run():
        await hub.start()
        try:
            orch = Orchestrator(hub, logs)
            goal = user_goal + ("\nMode: " + mode + "\nOutput: " + outfile)
            result = await orch.run_goal(goal)
            return result, logs.path
        finally:
            await hub.stop()
    result, logpath = asyncio.run(_run())
    st.session_state.last_run = (result, logpath)

if st.session_state.last_run:
    result, logpath = st.session_state.last_run
    st.subheader("Réponse finale")
    st.markdown(result.get("final") or "(Pas de réponse finale produite)")
    st.subheader("Logs JSONL")
    with open(logpath, "r", encoding="utf-8") as f:
        st.code(f.read(), language="json")
