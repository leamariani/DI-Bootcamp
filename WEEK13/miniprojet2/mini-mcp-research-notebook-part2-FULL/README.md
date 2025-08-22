# Mini MCP Research Notebook — Part 2

Application agentique Streamlit orchestrant des serveurs MCP tiers (**arXiv**, **Filesystem**)
et un serveur MCP custom **Scholar Plus** (métadonnées, BibTeX, extraction méthodo).
Backend LLM interchangeable **GroqCloud** ou **Ollama** via `.env`.

## Démarrage rapide
1. `cp .env.example .env` puis renseignez GROQ_API_KEY ou configurez Ollama
2. `mkdir -p workspace data/arxiv logs`
3. `uv tool install arxiv-mcp-server` (ou laissez l'app le lancer)
4. `pip install -r requirements.txt` (ou `uv pip install -r requirements.txt`)
5. `streamlit run app/app.py`

## Serveur custom: Scholar Plus
- `enrich_metadata({doi?|arxiv_id?|title?})` → métadonnées + BibTeX (Crossref/arXiv)
- `generate_bibtex({doi?|arxiv_id?|title?})` → BibTeX propre
- `extract_methods({text})` → tâches / datasets / méthodes / métriques / plan

## Orchestration conseillée
arxiv.search_papers → arxiv.read_paper → scholarplus.enrich_metadata →
cite.assemble_brief → cite.clean_citations → scholarplus.generate_bibtex → fs.write_file
