import streamlit as st
import asyncio
import json
from app.orchestrator import MCPOrchestrator
from app.log_utils import logger

# Configuration de la page
st.set_page_config(
    page_title="Carnet de Recherche MCP",
    page_icon="📚",
    layout="wide"
)

# Titre et description
st.title("📚 Carnet de Recherche avec MCP")
st.markdown("""
Cette application utilise des serveurs MCP pour vous aider dans vos recherches académiques.
Elle combine la puissance d'arXiv, la gestion de fichiers et le nettoyage de citations.
""")

# Initialisation de l'orchestrateur
@st.cache_resource
def get_orchestrator():
    return MCPOrchestrator()

# Section principale
def main():
    tab1, tab2, tab3 = st.tabs(["Recherche", "Configuration", "Journal"])
    
    with tab1:
        st.header("Recherche Académique")
        
        query = st.text_area(
            "Votre requête de recherche:",
            height=100,
            placeholder="Ex: Trouve les derniers articles sur les transformers en NLP, télécharge les PDFs pertinents, et crée un résumé avec les citations formatées correctement."
        )
        
        if st.button("Lancer la recherche", type="primary"):
            if not query:
                st.warning("Veuillez entrer une requête de recherche.")
            else:
                with st.spinner("Initialisation des serveurs MCP..."):
                    orchestrator = get_orchestrator()
                    try:
                        # Initialisation asynchrone
                        async def initialize_and_execute():
                            await orchestrator.initialize_servers()
                            return await orchestrator.plan_and_execute(query)
                        
                        result = asyncio.run(initialize_and_execute())
                        
                        st.success("Recherche terminée!")
                        st.subheader("Résultats")
                        st.write(result)
                        
                    except Exception as e:
                        st.error(f"Erreur lors de l'exécution: {str(e)}")
                        logger.error(f"Erreur: {str(e)}")
    
    with tab2:
        st.header("Configuration")
        
        st.subheader("Serveurs MCP")
        try:
            with open("config/mcp_servers.json", "r") as f:
                config = json.load(f)
            st.json(config)
        except:
            st.error("Impossible de charger la configuration des serveurs")
        
        st.subheader("Variables d'environnement")
        env_vars = {
            "LLM_BACKEND": os.getenv("LLM_BACKEND", "Non défini"),
            "GROQ_MODEL": os.getenv("GROQ_MODEL", "Non défini"),
            "OLLAMA_MODEL": os.getenv("OLLAMA_MODEL", "Non défini")
        }
        st.json(env_vars)
    
    with tab3:
        st.header("Journal d'exécution")
        if st.button("Rafraîchir les logs"):
            try:
                with open("app.log", "r") as f:
                    logs = f.read()
                st.text_area("Logs", logs, height=400)
            except:
                st.warning("Aucun log disponible")

if __name__ == "__main__":
    main()