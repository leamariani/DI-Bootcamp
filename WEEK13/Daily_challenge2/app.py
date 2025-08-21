import streamlit as st
import os
from dotenv import load_dotenv
import json
import nbformat
from nbconvert import PythonExporter
import importlib.util
import sys
import asyncio

# --- Configuration et Chargement des Clés API ---

# Charger les variables d'environnement depuis le fichier .env
# C'est une bonne pratique pour gérer les informations sensibles comme les clés API.
load_dotenv()

st.set_page_config(page_title="Agent RAG Auto-Correcteur", layout="wide")

st.title("🤖 Agent RAG Auto-Correcteur avec LangGraph")
st.markdown("""
Cette application est une démonstration d'un agent conversationnel avancé. 
Posez une question sur le Machine Learning (en particulier sur les agents), et l'agent tentera de vous répondre.
S'il ne trouve pas d'information pertinente dans sa base de connaissance, il reformulera votre question pour améliorer sa recherche.
""")

# Configuration pour LangSmith (optionnel mais recommandé pour le débogage)
# LangSmith permet de visualiser et de déboguer les exécutions de vos agents LangChain.
os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_ENDPOINT"] = "https://api.smith.langchain.com"
# Assurez-vous que LANGCHAIN_API_KEY est dans votre .env si vous utilisez LangSmith
if os.getenv("LANGCHAIN_API_KEY"):
    st.sidebar.success("Traçage LangSmith activé.")
else:
    st.sidebar.warning("Clé API LangChain non trouvée. Le traçage LangSmith est désactivé.")

# Affichage des clés API chargées (pour le débogage)
st.sidebar.header("Configuration")
keys = ["GROQ_API_KEY", "TAVILY_API_KEY", "GOOGLE_API_KEY"]
for key in keys:
    if os.getenv(key):
        st.sidebar.success(f"{key} chargée.")
    else:
        st.sidebar.error(f"{key} non trouvée dans le fichier .env.")

# --- Chargement et Exécution de la Logique du Notebook ---

def import_notebook_as_module(notebook_path):
    """
    Charge un notebook Jupyter comme un module Python en mémoire.
    Cela nous permet d'appeler les fonctions définies dans le notebook directement depuis notre script Streamlit,
    sans avoir à dupliquer le code.
    """
    try:
        with open(notebook_path, 'r', encoding='utf-8') as f:
            notebook_content = f.read()

        # Analyser le contenu du notebook
        nb = nbformat.reads(notebook_content, as_version=4)
        
        # Exporter le notebook en script Python
        exporter = PythonExporter()
        source_code, _ = exporter.from_notebook_node(nb)
        
        # Créer un nom de module unique pour éviter les conflits
        module_name = f"agent_logic_{os.path.basename(notebook_path).replace('.ipynb', '')}"
        
        # Créer une spécification de module et le charger
        spec = importlib.util.spec_from_loader(module_name, loader=None)
        if spec is None:
            raise ImportError(f"Impossible de créer le spec pour {module_name}")
            
        agent_module = importlib.util.module_from_spec(spec)
        
        # Exécuter le code du notebook dans le contexte du nouveau module
        exec(source_code, agent_module.__dict__)
        
        # Ajouter le module au système pour qu'il soit trouvable
        sys.modules[module_name] = agent_module
        
        return agent_module

    except FileNotFoundError:
        st.error(f"Le fichier notebook '{notebook_path}' est introuvable. Assurez-vous qu'il se trouve dans le même répertoire que app.py.")
        return None
    except Exception as e:
        st.error(f"Une erreur est survenue lors du chargement du notebook : {e}")
        with st.expander("Détails de l'erreur"):
            st.code(source_code)
        return None

# Charger la logique de l'agent depuis le notebook
agent_logic = import_notebook_as_module("agentic_rag.ipynb")

if agent_logic:
    st.sidebar.success("La logique de l'agent depuis `agentic_rag.ipynb` a été chargée.")

    # --- Interface Utilisateur ---

    # Initialiser l'état de la session pour l'historique de chat
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Afficher les messages précédents
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Zone de saisie pour l'utilisateur
    if prompt := st.chat_input("Posez votre question ici..."):
        # Ajouter le message de l'utilisateur à l'historique et l'afficher
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Obtenir la réponse de l'agent
        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            full_response = ""
            
            # Afficher un indicateur de chargement pendant que l'agent réfléchit
            with st.spinner("L'agent réfléchit..."):
                try:
                    # C'est ici que nous appelons la fonction principale du notebook
                    # La fonction `run_agent` doit être définie dans votre notebook
                    # et doit prendre la question de l'utilisateur en entrée.
                    result_generator = agent_logic.run_agent(prompt)
                    
                    # Simuler un streaming de la réponse pour une meilleure UX
                    for chunk in result_generator:
                        # La fonction `run_agent` doit retourner un générateur
                        # qui produit des morceaux de la réponse.
                        full_response += chunk
                        message_placeholder.markdown(full_response + "▌")
                    message_placeholder.markdown(full_response)

                except AttributeError:
                    st.error("La fonction 'run_agent' n'a pas été trouvée dans le notebook. Assurez-vous qu'elle est bien définie.")
                    full_response = "Erreur : Impossible d'exécuter la logique de l'agent."
                except Exception as e:
                    st.error(f"Une erreur est survenue lors de l'exécution de l'agent : {e}")
                    full_response = f"Désolé, une erreur est survenue."

            # Ajouter la réponse complète de l'agent à l'historique
            st.session_state.messages.append({"role": "assistant", "content": full_response})

else:
    st.error("L'application ne peut pas fonctionner sans la logique de l'agent.")
    st.info("Veuillez vérifier le chemin du fichier `agentic_rag.ipynb` et les erreurs ci-dessus.")

# --- Affichage du code source du notebook (pour la transparence) ---
st.sidebar.markdown("---")
if st.sidebar.checkbox("Afficher le code source du Notebook"):
    try:
        with open("agentic_rag.ipynb", "r", encoding="utf-8") as f:
            notebook_content = f.read()
        st.sidebar.code(notebook_content, language="json")
    except FileNotFoundError:
        st.sidebar.error("Fichier `agentic_rag.ipynb` non trouvé.")
