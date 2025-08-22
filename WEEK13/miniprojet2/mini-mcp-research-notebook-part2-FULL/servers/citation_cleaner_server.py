from mcp.server.fastmcp import FastMCP, tool
import re
from typing import List, Dict

mcp = FastMCP("Citation Cleaner")

@tool()
def clean_citations(text: str) -> str:
    t = re.sub(r"\b(arxiv\s*:\s*|arxiv\s+)?(\d{4}\.\d{4,5})(v\d+)?\b", r"arXiv:\2", text, flags=re.I)
    t = re.sub(r"\[(.*?)\s*,\s*(\d{4})\]", r"[\1 \2]", t)
    t = re.sub(r"(\[(?:[^\]]+)\])(?:\s*,\s*\1)+", r"\1", t)
    t = re.sub(r"\s+\n", "\n", t)
    return t

@tool()
def assemble_brief(items: List[Dict]) -> str:
    lines = ["# Research Brief\n"]
    for i, it in enumerate(items, 1):
        title = it.get("title", "Sans titre")
        authors = it.get("authors", "?")
        year = it.get("year", "?")
        summary = it.get("summary", "(résumé non disponible)")
        arx = it.get("arxiv_id")
        url = it.get("url")
        lines.append(f"## {i}. {title} ({year})\n")
        lines.append(f"**Auteurs** : {authors}\n")
        if arx:
            lines.append(f"**arXiv** : arXiv:{arx}\n")
        if url:
            lines.append(f"**Lien** : {url}\n")
        lines.append("**Résumé**\n")
        lines.append(summary.strip() + "\n")
        lines.append("\n---\n")
    lines.append("\n### Citations (normalisées)\n")
    lines.append("(à compléter selon le besoin)\n")
    return "\n".join(lines)

if __name__ == "__main__":
    import asyncio
    import mcp.server.stdio
    asyncio.run(mcp.run(mcp.server.stdio.stdio_server()))
