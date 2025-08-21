import os
import json
import asyncio
import time
from typing import Dict, List, Any, Optional
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.llm_client import LLMClient
from app.log_utils import logger, log_tool_call

class MCPOrchestrator:
    def __init__(self):
        self.llm_client = LLMClient()
        self.sessions = {}
        self.available_tools = []
        self.max_retries = int(os.getenv("MAX_RETRIES", 3))
    
    async def initialize_servers(self):
        """Initialise tous les serveurs MCP configurés"""
        try:
            with open("config/mcp_servers.json", "r") as f:
                config = json.load(f)
            
            for server_config in config["servers"]:
                server_name = server_config["name"]
                logger.info(f"Initialisation du serveur {server_name}")
                
                # Configuration du serveur
                server_params = StdioServerParameters(
                    command=server_config["command"],
                    args=server_config["args"],
                    env=server_config.get("env", {})
                )
                
                # Connexion au serveur
                session = await stdio_client(server_params)
                await session.initialize()
                
                # Liste des outils disponibles
                tools_response = await session.list_tools()
                for tool in tools_response.tools:
                    tool_info = {
                        "name": f"{server_name}.{tool.name}",
                        "description": tool.description,
                        "inputSchema": tool.inputSchema
                    }
                    self.available_tools.append(tool_info)
                
                self.sessions[server_name] = session
                logger.info(f"Serveur {server_name} initialisé avec {len(tools_response.tools)} outils")
                
        except Exception as e:
            logger.error(f"Erreur lors de l'initialisation des serveurs: {str(e)}")
            raise
    
    async def execute_tool(self, tool_name: str, arguments: Dict) -> Dict:
        """Exécute un outil MCP avec gestion des erreurs"""
        try:
            # Extraction du nom du serveur et de l'outil
            server_name, actual_tool_name = tool_name.split(".", 1)
            
            if server_name not in self.sessions:
                raise ValueError(f"Serveur {server_name} non connecté")
            
            session = self.sessions[server_name]
            
            # Journalisation de l'appel
            log_tool_call(tool_name, arguments, {}, False)
            
            # Exécution avec retries
            for attempt in range(self.max_retries):
                try:
                    result = await session.call_tool(actual_tool_name, arguments)
                    
                    # Conversion du résultat en format utilisable
                    output = self._format_tool_result(result)
                    
                    # Journalisation du succès
                    log_tool_call(tool_name, arguments, output, True)
                    
                    return output
                    
                except Exception as e:
                    if attempt == self.max_retries - 1:
                        raise
                    logger.warning(f"Tentative {attempt + 1} échouée, réessai dans 1s: {str(e)}")
                    time.sleep(1)
                    
        except Exception as e:
            logger.error(f"Erreur lors de l'exécution de {tool_name}: {str(e)}")
            return {"error": str(e), "status": "failed"}
    
    def _format_tool_result(self, result) -> Dict:
        """Formate le résultat d'un outil MCP"""
        if not result or not hasattr(result, 'content'):
            return {}
        
        formatted = {}
        for item in result.content:
            if hasattr(item, 'text'):
                formatted['text'] = item.text
            elif hasattr(item, 'image'):
                formatted['image'] = f"Image: {item.image.uri}"
            elif hasattr(item, 'resources'):
                formatted['resources'] = item.resources
        
        return formatted
    
    async def plan_and_execute(self, user_query: str) -> str:
        """Planifie et exécute une requête utilisateur"""
        # Étape 1: Planification avec le LLM
        plan_prompt = f"""
        En tant qu'assistant de recherche, planifiez l'exécution de cette requête:
        {user_query}
        
        Outils disponibles:
        {json.dumps(self.available_tools, indent=2)}
        
        Créez un plan étape par étape. Pour chaque étape, spécifiez:
        1. L'outil à utiliser
        2. Les arguments nécessaires
        3. Le but de cette étape
        """
        
        plan_response = self.llm_client.create_completion([
            {"role": "system", "content": "Vous êtes un planificateur expert pour la recherche académique."},
            {"role": "user", "content": plan_prompt}
        ])
        
        plan = plan_response.get("content", "")
        logger.info(f"Plan généré: {plan}")
        
        # Étape 2: Exécution du plan
        execution_prompt = f"""
        Plan à exécuter:
        {plan}
        
        Résultats actuels: Aucun pour le moment
        
        Quelle est la prochaine action à effectuer? Répondez avec un JSON contenant:
        - tool: nom de l'outil
        - arguments: objet avec les paramètres
        - reasoning: raisonnement pour ce choix
        """
        
        context = []
        max_steps = 10
        
        for step in range(max_steps):
            # Demander au LLM la prochaine action
            messages = [
                {"role": "system", "content": "Vous exécutez un plan de recherche. Choisissez la prochaine action."},
                {"role": "user", "content": execution_prompt}
            ]
            messages.extend(context)
            
            response = self.llm_client.create_completion(messages, self.available_tools)
            
            if response.get("tool_calls"):
                # Exécuter les appels d'outils
                for tool_call in response["tool_calls"]:
                    tool_name = tool_call["function"]["name"]
                    arguments = json.loads(tool_call["function"]["arguments"])
                    
                    result = await self.execute_tool(tool_name, arguments)
                    
                    # Ajouter au contexte
                    context.append({
                        "role": "assistant", 
                        "content": f"Exécution de {tool_name} avec {arguments}"
                    })
                    context.append({
                        "role": "user", 
                        "content": f"Résultat: {json.dumps(result, indent=2)}"
                    })
            else:
                # Plus d'actions, retourner le résultat final
                return response.get("content", "Exécution terminée")
        
        return "Nombre maximum d'étapes atteint. Exécution terminée."
    
    async def close(self):
        """Ferme toutes les sessions MCP"""
        for session in self.sessions.values():
            await session.close()