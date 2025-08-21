import os
import requests
import json
from typing import Dict, List, Any, Optional
from app.log_utils import logger

class LLMClient:
    def __init__(self):
        self.backend = os.getenv("LLM_BACKEND", "groq").lower()
        self._validate_config()
    
    def _validate_config(self):
        """Valide la configuration du backend LLM"""
        if self.backend == "groq" and not os.getenv("GROQ_API_KEY"):
            raise ValueError("GROQ_API_KEY est requis pour le backend Groq")
        elif self.backend == "ollama":
            # Vérification basique qu'Ollama est accessible
            try:
                requests.get(os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"), timeout=5)
            except:
                logger.warning("Ollama n'est pas accessible. Vérifiez qu'il est installé et démarré.")
    
    def create_completion(self, messages: List[Dict[str, str]], tools: Optional[List[Dict]] = None) -> Dict[str, Any]:
        """Crée une completion avec le backend configuré"""
        if self.backend == "groq":
            return self._create_groq_completion(messages, tools)
        else:
            return self._create_ollama_completion(messages, tools)
    
    def _create_groq_completion(self, messages: List[Dict[str, str]], tools: Optional[List[Dict]] = None) -> Dict[str, Any]:
        """Utilise l'API Groq pour la completion"""
        try:
            import groq
            
            client = groq.Client(api_key=os.getenv("GROQ_API_KEY"))
            
            completion_kwargs = {
                "model": os.getenv("GROQ_MODEL", "llama3-70b-8192"),
                "messages": messages,
                "temperature": 0.1,
                "max_tokens": 4000
            }
            
            if tools:
                completion_kwargs["tools"] = tools
                completion_kwargs["tool_choice"] = "auto"
            
            response = client.chat.completions.create(**completion_kwargs)
            
            return {
                "content": response.choices[0].message.content,
                "tool_calls": getattr(response.choices[0].message, 'tool_calls', None)
            }
            
        except ImportError:
            raise ImportError("Le package groq est requis. Installez-le avec 'pip install groq'")
        except Exception as e:
            logger.error(f"Erreur Groq: {str(e)}")
            return {"content": f"Erreur: {str(e)}", "tool_calls": None}
    
    def _create_ollama_completion(self, messages: List[Dict[str, str]], tools: Optional[List[Dict]] = None) -> Dict[str, Any]:
        """Utilise Ollama pour la completion"""
        try:
            url = f"{os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')}/api/chat"
            
            payload = {
                "model": os.getenv("OLLAMA_MODEL", "llama3"),
                "messages": messages,
                "options": {
                    "temperature": 0.1
                }
            }
            
            if tools:
                payload["tools"] = tools
            
            response = requests.post(
                url, 
                json=payload, 
                timeout=int(os.getenv("REQUEST_TIMEOUT", 30))
            )
            response.raise_for_status()
            
            result = response.json()
            
            return {
                "content": result["message"]["content"],
                "tool_calls": result["message"].get("tool_calls")
            }
            
        except Exception as e:
            logger.error(f"Erreur Ollama: {str(e)}")
            return {"content": f"Erreur: {str(e)}", "tool_calls": None}