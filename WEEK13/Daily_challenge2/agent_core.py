# ===============================
# agent_core.py — Partie 1/3
# ===============================

import os
import time
from typing import Dict, Any, List

from dotenv import load_dotenv
load_dotenv(override=True)

# LangChain / LangGraph
from langchain_groq import ChatGroq
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_community.document_loaders import WebBaseLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langgraph.graph import StateGraph, END

from pydantic import BaseModel, Field


# -------------------------------
# 1) LLM (Groq) — choix et fallback
# -------------------------------
def _make_llm():
    """
    Choix par défaut : Llama 3.1 70B pour une meilleure robustesse de raisonnement.
    Fallback : 8B instant si indisponible, puis Mixtral.
    Température = 0 pour rendre le routage/évaluation plus stables (comportement quasi-déterministe).
    """
    model_candidates = [
        "llama-3.1-70b-versatile",
        "llama-3.1-8b-instant",
        "mixtral-8x7b-32768",
    ]
    last_error = None
    for name in model_candidates:
        try:
            return ChatGroq(model_name=name, temperature=0)
        except Exception as e:
            last_error = e
            continue
    # Si aucun modèle ne marche, remonter l'erreur explicite
    raise RuntimeError(f"Impossible d'initialiser un modèle Groq parmi {model_candidates}: {last_error}")


# -------------------------------
# 2) Embeddings (rapides et gratuits)
# -------------------------------
def _make_embeddings():
    """
    'all-MiniLM-L6-v2' est un excellent compromis vitesse/qualité pour RAG léger.
    """
    return HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")


# -------------------------------
# 3) Construction / chargement du vector store Chroma
# -------------------------------
def _ensure_vectorstore(persist_dir: str = "./chroma_db") -> Chroma:
    """
    - Si 'persist_dir' est vide ou absent, on construit l'index:
        a) on tente de charger des pages web techniques (LangChain docs),
        b) fallback local minimal si pas de réseau.
    - On persiste ensuite l'index pour réutilisation.
    """
    os.makedirs(persist_dir, exist_ok=True)
    # S'il y a déjà des fichiers dans le dossier, on recharge
    if any(os.scandir(persist_dir)):
        return Chroma(embedding_function=_make_embeddings(), persist_directory=persist_dir)

    # Sinon, construire l'index
    try:
        urls = [
            "https://python.langchain.com/docs/introduction/",
            "https://python.langchain.com/docs/concepts/rag/",
            "https://python.langchain.com/docs/concepts/agents/",
        ]
        loader = WebBaseLoader(urls)
        docs = loader.load()
    except Exception:
        # Fallback hors ligne : documents embarqués minimaux pour tester la pipeline
        from langchain_core.documents import Document
        docs = [
            Document(page_content=(
                "RAG (Retrieval-Augmented Generation) combine un modèle de langage avec un "
                "retriever qui extrait des passages pertinents depuis une base de connaissances "
                "vectorielle afin de répondre de manière plus fiable et sourcée."
            ), metadata={"source": "local_fallback:rag"}),
            Document(page_content=(
                "Un agent peut décider d'appeler des outils (par exemple recherche web) en plus d'un retriever. "
                "LangGraph permet d'orchestrer des étapes et des conditions au sein d'un graphe d'états."
            ), metadata={"source": "local_fallback:agents"}),
        ]

    splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=120)
    splits = splitter.split_documents(docs)

    vect = Chroma.from_documents(
        splits,
        embedding=_make_embeddings(),
        persist_directory=persist_dir
    )
    vect.persist()
    return vect

# ===============================
# agent_core.py — Partie 2/3
# ===============================

# -------------------------------
# 4) Outil de recherche web
# -------------------------------
def _make_tools():
    """
    TavilySearchResults lit la clé TAVILY_API_KEY depuis l'environnement.
    max_results=5 pour limiter le coût/latence.
    """
    return {"web_search": TavilySearchResults(max_results=5)}


# -------------------------------
# 5) État & schémas structurés
# -------------------------------
class RouteDecision(BaseModel):
    use_tool: bool = Field(..., description="Faut-il appeler un outil ?")
    which_tool: str = Field("retriever", description="Parmi ['retriever','web_search']")

class GradeResult(BaseModel):
    relevant: bool = Field(..., description="True si les documents semblent pertinents.")

class AgentState(dict):
    """
    État minimaliste : on y stocke la question, la décision, les documents,
    et plus tard la réponse, sources, etc. Dict pour rester flexible.
    """
    pass


# -------------------------------
# 6) Nœud: Router (LLM à sortie structurée)
# -------------------------------
def node_router(state: AgentState) -> AgentState:
    """
    Décide: utiliser 'retriever', 'web_search' ou aucun outil (et aller directement à generate).
    """
    llm = _make_llm()
    prompt = ChatPromptTemplate.from_messages([
        ("system", "Tu es un routeur. Décide si l'assistant doit appeler un outil."),
        ("human", "Question: {q}\nRéponds en JSON avec 'use_tool' (true/false) et 'which_tool' ('retriever' ou 'web_search')."),
    ])
    chain = prompt | llm.with_structured_output(RouteDecision)
    decision = chain.invoke({"q": state["question"]})
    state["decision"] = decision.dict()
    return state


# -------------------------------
# 7) Nœud: Retrieve (Chroma)
# -------------------------------
def node_retrieve(state: AgentState) -> AgentState:
    vect = _ensure_vectorstore()
    retriever = vect.as_retriever(search_kwargs={"k": 5})
    docs = retriever.invoke(state["question"])
    state["documents"] = [{"content": d.page_content, "metadata": d.metadata} for d in docs]
    return state


# -------------------------------
# 8) Nœud: Web Search (Tavily)
# -------------------------------
def node_web_search(state: AgentState) -> AgentState:
    tools = _make_tools()
    results = tools["web_search"].invoke(state["question"])
    # Normaliser le format en pseudo-documents
    state["documents"] = [
        {
            "content": r.get("content", "") or r.get("snippet", ""),
            "metadata": {"source": r.get("url", ""), "title": r.get("title", "")},
        }
        for r in results
    ]
    return state


# -------------------------------
# 9) Aiguillage conditionnel: pertinence des documents
# -------------------------------
def grade_documents(state: AgentState) -> str:
    """
    Retourne 'generate' si pertinent, sinon 'rewrite'.
    On donne un aperçu tronqué pour maîtriser le coût LLM.
    """
    llm = _make_llm()
    docs_preview = "\n\n".join([d["content"][:400] for d in state.get("documents", [])])
    prompt = ChatPromptTemplate.from_messages([
        ("system", "Tu es un évaluateur. Juge la pertinence des documents récupérés."),
        ("human", "Question:\n{q}\n\nDocs (aperçu):\n{docs}\n\nRéponds JSON: {relevant: true/false}"),
    ])
    chain = prompt | llm.with_structured_output(GradeResult)
    result = chain.invoke({"q": state["question"], "docs": docs_preview or "(no docs)"})
    return "generate" if result.relevant else "rewrite"


# -------------------------------
# 10) Nœud: Rewrite (optimisation de requête)
# -------------------------------
def node_rewrite(state: AgentState) -> AgentState:
    """
    Réécrit la question pour améliorer la récupération.
    On renverra ensuite vers le router pour éventuellement changer de stratégie (retriever vs web).
    """
    llm = _make_llm()
    prompt = ChatPromptTemplate.from_messages([
        ("system", "Tu es un optimiseur de requêtes."),
        ("human", "Question initiale: {q}\nRéécris une requête claire, spécifique et utile à la recherche d'informations pertinentes."),
    ])
    chain = prompt | llm | StrOutputParser()
    improved = chain.invoke({"q": state["question"]})
    state["question"] = improved.strip()
    return state


# ===============================
# agent_core.py — Partie 3/3
# ===============================

# -------------------------------
# 11) Nœud: Generate (réponse ancrée + citations)
# -------------------------------
def node_generate(state: AgentState) -> AgentState:
    # Prépare les sources pour attribution
    sources: List[Dict[str, str]] = []
    for i, d in enumerate(state.get("documents", []) or [], 1):
        meta = d.get("metadata", {}) or {}
        src = meta.get("source") or meta.get("url") or ""
        title = meta.get("title") or f"Source {i}"
        sources.append({"title": title, "url": src})

    ctx = "\n---\n".join([d["content"] for d in (state.get("documents") or [])])

    prompt = ChatPromptTemplate.from_messages([
        ("system",
         "Tu es un assistant fiable. Réponds STRICTEMENT à partir du contexte fourni ci-dessous. "
         "Si le contexte est vide ou hors-sujet, indique que tu n'as pas assez d'information."),
        ("human",
         "Question:\n{q}\n\nContexte (extraits récupérés):\n{ctx}\n\n"
         "Rédige une réponse concise et ajoute des citations numérotées [1], [2] correspondant aux sources."),
    ])

    chain = prompt | _make_llm() | StrOutputParser()
    answer = chain.invoke({"q": state["question"], "ctx": ctx})

    state["answer"] = answer
    state["sources"] = sources
    return state


# -------------------------------
# 12) Câblage LangGraph et compilation
# -------------------------------
def _build_graph():
    """
    Graphe:
        router ──> retrieve ──> (grade) ──> generate
           └──> web_search ───> (grade) ──> generate
        rewrite ────────────────────────────┘ (boucle via router)
    """
    wf = StateGraph(AgentState)

    wf.add_node("router", node_router)
    wf.add_node("retrieve", node_retrieve)
    wf.add_node("web_search", node_web_search)
    wf.add_node("rewrite", node_rewrite)
    wf.add_node("generate", node_generate)
    wf.set_entry_point("router")

    # Route conditionnel depuis router
    def route_decision(state: AgentState) -> str:
        dec = state.get("decision", {}) or {}
        if not dec or not dec.get("use_tool", True):
            return "generate"
        return "retrieve" if dec.get("which_tool", "retriever") == "retriever" else "web_search"

    wf.add_conditional_edges(
        "router",
        route_decision,
        {"retrieve": "retrieve", "web_search": "web_search", "generate": "generate"}
    )

    # Après récupération: évaluer la pertinence -> generate ou rewrite
    wf.add_conditional_edges("retrieve", grade_documents, {"generate": "generate", "rewrite": "rewrite"})
    wf.add_conditional_edges("web_search", grade_documents, {"generate": "generate", "rewrite": "rewrite"})

    # rewrite boucle vers router
    wf.add_edge("rewrite", "router")

    # generate termine
    wf.add_edge("generate", END)

    return wf.compile()


# Compile une seule fois (évite de reconstruire à chaque appel)
_APP = _build_graph()


# -------------------------------
# 13) API publique appelée par Streamlit
# -------------------------------
def answer_question(question: str) -> Dict[str, Any]:
    """
    Exécute le graphe et renvoie un payload prêt pour l'UI.
    """
    t0 = time.time()
    try:
        init_state = {"question": (question or "").strip()}
        result = _APP.invoke(init_state)
        payload = {
            "answer": result.get("answer") or "Je n'ai pas assez d'information pour répondre de façon fiable.",
            "sources": result.get("sources", []),
            "meta": {
                "latency_ms": int((time.time() - t0) * 1000),
                "decision": result.get("decision", {}),
                "num_docs": len(result.get("documents", []) if result.get("documents") else []),
            },
        }
        return payload
    except Exception as e:
        return {
            "answer": f"Erreur lors de l'exécution de l'agent: {e}",
            "sources": [],
            "meta": {"latency_ms": int((time.time() - t0) * 1000)},
        }


# Option facultative pour tester en ligne de commande:
if __name__ == "__main__":
    demo_q = "Explique le principe de RAG et comment il se combine avec des agents."
    print(answer_question(demo_q))
