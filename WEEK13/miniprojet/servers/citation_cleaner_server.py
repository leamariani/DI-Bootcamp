#!/usr/bin/env python3
"""
Serveur MCP personnalisé pour le nettoyage et le formatage des citations académiques.
"""
import json
import re
from typing import Dict, List, Any
from mcp.server import Server
from mcp.server.stdio import stdio_server

# Initialisation du serveur
server = Server("citation_cleaner")

@server.list_tools()
async def handle_list_tools() -> List[Dict[str, Any]]:
    """Liste les outils disponibles"""
    return [
        {
            "name": "clean_citations",
            "description": "Nettoie et formate une liste de citations bibliographiques",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "citations": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Liste des citations à nettoyer"
                    },
                    "format": {
                        "type": "string",
                        "enum": ["apa", "mla", "chicago", "plain"],
                        "description": "Style de formatage",
                        "default": "apa"
                    }
                },
                "required": ["citations"]
            }
        },
        {
            "name": "extract_citations_from_text",
            "description": "Extrait les citations d'un texte académique",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Texte contenant des citations"
                    }
                },
                "required": ["text"]
            }
        }
    ]

@server.call_tool()
async def handle_call_tool(name: str, arguments: Dict) -> List[Dict[str, Any]]:
    """Exécute l'outil demandé"""
    if name == "clean_citations":
        return await clean_citations(arguments)
    elif name == "extract_citations_from_text":
        return await extract_citations_from_text(arguments)
    else:
        raise ValueError(f"Outil inconnu: {name}")

async def clean_citations(arguments: Dict) -> List[Dict[str, Any]]:
    """Nettoie et formate des citations"""
    citations = arguments.get("citations", [])
    format_style = arguments.get("format", "apa")
    
    cleaned_citations = []
    
    for citation in citations:
        try:
            # Nettoyage de base
            cleaned = citation.strip()
            cleaned = re.sub(r'\s+', ' ', cleaned)  # Normalise les espaces
            
            # Application du style de formatage
            if format_style == "apa":
                cleaned = format_apa(cleaned)
            elif format_style == "mla":
                cleaned = format_mla(cleaned)
            elif format_style == "chicago":
                cleaned = format_chicago(cleaned)
            # "plain" ne fait rien de plus
            
            cleaned_citations.append(cleaned)
            
        except Exception as e:
            cleaned_citations.append(f"ERREUR: {citation} ({str(e)})")
    
    return [{
        "type": "text",
        "content": json.dumps({
            "cleaned_citations": cleaned_citations,
            "format_used": format_style,
            "total_processed": len(citations)
        }, ensure_ascii=False, indent=2)
    }]

async def extract_citations_from_text(arguments: Dict) -> List[Dict[str, Any]]:
    """Extrait les citations d'un texte"""
    text = arguments.get("text", "")
    
    # Pattern simple pour détecter les citations (à améliorer)
    citation_patterns = [
        r'\([A-Za-z]+, \d{4}\)',  # (Auteur, année)
        r'[A-Za-z]+ et al\. \(\d{4}\)',  # Auteur et al. (année)
        r'\b\d{4}[a-z]?\b',  # Année seule
    ]
    
    found_citations = []
    for pattern in citation_patterns:
        matches = re.findall(pattern, text)
        found_citations.extend(matches)
    
    return [{
        "type": "text",
        "content": json.dumps({
            "extracted_citations": list(set(found_citations)),  # Déduplication
            "total_found": len(set(found_citations))
        }, ensure_ascii=False, indent=2)
    }]

def format_apa(citation: str) -> str:
    """Formate une citation en style APA"""
    # Implémentation simplifiée
    if re.search(r'\(\d{4}\)', citation):
        return citation  # Supposé déjà formaté
    
    # Tentative de formatage basique
    authors = re.findall(r'[A-Z][a-z]+, [A-Z]\.', citation)
    year = re.findall(r'\b\d{4}\b', citation)
    
    if authors and year:
        return f"{authors[0]} et al. ({year[0]}) {citation}"
    
    return citation

def format_mla(citation: str) -> str:
    """Formate une citation en style MLA"""
    # Implémentation simplifiée
    return citation  # Placeholder

def format_chicago(citation: str) -> str:
    """Formate une citation en style Chicago"""
    # Implémentation simplifiée
    return citation  # Placeholder

async def main():
    """Point d'entrée principal"""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())