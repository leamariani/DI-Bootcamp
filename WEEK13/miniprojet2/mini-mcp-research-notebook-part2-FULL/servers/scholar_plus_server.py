from __future__ import annotations
import os, re
from typing import Optional, List, Dict, Any
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential
from pydantic import BaseModel, Field
from mcp.server.fastmcp import FastMCP, tool

CR_CONTACT = os.environ.get("CONTACT_EMAIL", "dev@example.com")
CR_UA = f"MiniMCP-ResearchNotebook/0.2 (+mailto:{CR_CONTACT})"

def _http() -> httpx.Client:
    return httpx.Client(timeout=20.0, headers={"User-Agent": CR_UA})

def _author_str(a: Dict[str, Any]) -> str:
    given = a.get("given") or ""
    family = a.get("family") or ""
    full = (family + ", " + given).strip(", ").strip()
    return full or (a.get("name") or "?")

def _norm_year(msg: Dict[str, Any]) -> Optional[int]:
    parts = msg.get("issued", {}).get("date-parts") or msg.get("published", {}).get("date-parts")
    if parts and parts[0]:
        return parts[0][0]
    return None

def _to_bibtex_key(title: str, authors: List[str], year: Optional[int]) -> str:
    import re as _re
    if authors:
        first = _re.sub(r"[^A-Za-z]", "", authors[0].split(",")[0])[:12]
    else:
        first = "NoAuthor"
    yr = str(year) if year else "n.d."
    t0 = _re.sub(r"[^A-Za-z0-9]", "", (title or "")).lower()[:12] or "untitled"
    return f"{first}{yr}{t0}"

def _bibtex_from_crossref(msg: Dict[str, Any]) -> str:
    title = " ".join(msg.get("title") or [])
    authors = [_author_str(a) for a in msg.get("author", [])]
    year = _norm_year(msg)
    venue = (msg.get("container-title") or [""])[0]
    doi = msg.get("DOI")
    url = msg.get("URL")
    key = _to_bibtex_key(title, authors, year)
    fields = {
        "title": title,
        "author": " and ".join(authors) if authors else None,
        "year": str(year) if year else None,
        "journal": venue or None,
        "doi": doi or None,
        "url": url or None,
    }
    body = ",\n  ".join([f"{k} = {{{v}}}" for k, v in fields.items() if v])
    return f"@article{{{key},\n  {body}\n}}"

def _bibtex_from_arxiv(meta: Dict[str, Any]) -> str:
    title = meta.get("title") or "Untitled"
    authors = meta.get("authors") or []
    year = meta.get("year")
    arxiv_id = meta.get("arxiv_id")
    pdf = meta.get("pdf_url")
    key = _to_bibtex_key(title, authors, year)
    fields = {
        "title": title,
        "author": " and ".join(authors) if authors else None,
        "year": str(year) if year else None,
        "eprint": f"arXiv:{arxiv_id}" if arxiv_id else None,
        "archivePrefix": "arXiv",
        "primaryClass": meta.get("primary_category"),
        "url": pdf or None,
    }
    body = ",\n  ".join([f"{k} = {{{v}}}" for k, v in fields.items() if v])
    return f"@article{{{key},\n  {body}\n}}"

class EnrichRequest(BaseModel):
    doi: Optional[str] = Field(default=None, description="Identifiant DOI")
    arxiv_id: Optional[str] = Field(default=None, description="Identifiant arXiv, ex: 2101.00001")
    title: Optional[str] = Field(default=None, description="Titre approximatif pour recherche Crossref")

class EnrichResponse(BaseModel):
    title: Optional[str]
    authors: List[str] = []
    year: Optional[int]
    venue: Optional[str]
    doi: Optional[str]
    arxiv_id: Optional[str]
    url: Optional[str]
    pdf_url: Optional[str]
    primary_category: Optional[str]
    bibtex: Optional[str]

class BibRequest(BaseModel):
    doi: Optional[str] = None
    arxiv_id: Optional[str] = None
    title: Optional[str] = None

class BibResponse(BaseModel):
    bibtex: str

class ExtractMethodsRequest(BaseModel):
    text: str = Field(..., description="Texte d'article (abstract ou introduction)")

class ExtractMethodsResponse(BaseModel):
    tasks: List[str] = []
    datasets: List[str] = []
    methods: List[str] = []
    metrics: List[str] = []
    outline: List[str] = []

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=0.5, max=4), reraise=True)
def _crossref_by_doi(doi: str):
    if not doi:
        return None
    with _http() as c:
        r = c.get(f"https://api.crossref.org/works/{doi}")
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json().get("message")

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=0.5, max=4), reraise=True)
def _crossref_by_title(title: str):
    if not title:
        return None
    with _http() as c:
        r = c.get("https://api.crossref.org/works", params={"query.title": title, "rows": 1, "sort": "relevance"})
        r.raise_for_status()
        items = r.json().get("message", {}).get("items", [])
        return items[0] if items else None

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=0.5, max=4), reraise=True)
def _arxiv_meta(arxiv_id: str):
    if not arxiv_id:
        return None
    with _http() as c:
        r = c.get("http://export.arxiv.org/api/query", params={"search_query": f"id:{arxiv_id}", "max_results": 1})
        r.raise_for_status()
        txt = r.text
    title = re.search(r"<title>([^<]+)</title>", txt)
    title = title.group(1).strip() if title else None
    pdf = re.search(r'href="(http[^"]+\.pdf)"', txt)
    pdf = pdf.group(1) if pdf else None
    authors = re.findall(r"<name>([^<]+)</name>", txt)
    year_m = re.search(r"<published>(\d{4})-", txt)
    year = int(year_m.group(1)) if year_m else None
    cats = re.search(r"<category term=\"([^\"]+)\"", txt)
    cat = cats.group(1) if cats else None
    return {
        "title": title,
        "authors": authors,
        "year": year,
        "arxiv_id": arxiv_id,
        "pdf_url": pdf,
        "primary_category": cat,
    }

mcp = FastMCP("Scholar Plus")

@tool()
def enrich_metadata(req: EnrichRequest) -> EnrichResponse:
    msg = None
    arxiv = None
    if req.doi:
        msg = _crossref_by_doi(req.doi)
    if not msg and req.title:
        msg = _crossref_by_title(req.title)
    if req.arxiv_id:
        arxiv = _arxiv_meta(req.arxiv_id)

    title = None
    authors: List[str] = []
    year = None
    venue = None
    doi = None
    url = None

    if msg:
        title = " ".join(msg.get("title") or []) or title
        authors = [_author_str(a) for a in msg.get("author", [])] or authors
        year = _norm_year(msg) or year
        venue = (msg.get("container-title") or [""])[0] or venue
        doi = msg.get("DOI") or doi
        url = msg.get("URL") or url

    meta: Dict[str, Any] = {
        "title": arxiv.get("title") if (arxiv and not title) else title,
        "authors": authors or (arxiv.get("authors") if arxiv else []),
        "year": year or (arxiv.get("year") if arxiv else None),
        "venue": venue,
        "doi": doi,
        "arxiv_id": req.arxiv_id,
        "url": url or (f"https://doi.org/{doi}" if doi else None),
        "pdf_url": (arxiv.get("pdf_url") if arxiv else None),
        "primary_category": (arxiv.get("primary_category") if arxiv else None),
    }

    if msg:
        meta["bibtex"] = _bibtex_from_crossref(msg)
    elif arxiv:
        meta["bibtex"] = _bibtex_from_arxiv(arxiv)
    else:
        meta["bibtex"] = None

    return EnrichResponse(**meta)

@tool()
def generate_bibtex(req: BibRequest) -> BibResponse:
    if req.doi:
        msg = _crossref_by_doi(req.doi)
        if msg:
            return BibResponse(bibtex=_bibtex_from_crossref(msg))
    if req.title and not req.doi:
        msg = _crossref_by_title(req.title)
        if msg:
            return BibResponse(bibtex=_bibtex_from_crossref(msg))
    if req.arxiv_id:
        arxiv = _arxiv_meta(req.arxiv_id)
        if arxiv:
            return BibResponse(bibtex=_bibtex_from_arxiv(arxiv))
    raise ValueError("Aucun identifiant exploitable: fournissez doi, arxiv_id, ou title.")

@tool()
def extract_methods(req: ExtractMethodsRequest) -> ExtractMethodsResponse:
    t = req.text
    DATASETS = ["ImageNet", "COCO", "MNIST", "SQuAD", "LibriSpeech", "CIFAR-10", "CIFAR-100", "WikiText", "WebText"]
    METHODS = ["Transformer", "BERT", "GPT", "Llama", "RAG", "CNN", "LSTM", "GRU", "ViT", "T5"]
    METRICS = ["BLEU", "ROUGE", "F1", "Accuracy", "Precision", "Recall", "mAP", "AUC", "WER", "CER"]
    TASKS = ["classification", "retrieval", "summarization", "translation", "detection", "segmentation", "speech recognition"]

    def pick(keys: List[str]) -> List[str]:
        found = []
        for k in keys:
            if re.search(rf"\b{k}\b", t, flags=re.I):
                found.append(k)
        return sorted(set(found))

    datasets = pick(DATASETS)
    methods = pick(METHODS)
    metrics = pick(METRICS)
    tasks = pick(TASKS)

    outline = []
    for head in ["Introduction", "Méthodes", "Données", "Expériences", "Résultats", "Limites"]:
        if re.search(head, t, flags=re.I):
            outline.append(head)

    return ExtractMethodsResponse(tasks=tasks, datasets=datasets, methods=methods, metrics=metrics, outline=outline)

if __name__ == "__main__":
    import asyncio
    import mcp.server.stdio
    asyncio.run(mcp.run(mcp.server.stdio.stdio_server()))
