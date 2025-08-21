import logging
import sys
import json
from typing import Dict, Any
from datetime import datetime

def setup_logging():
    """Configure la journalisation pour l'application"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler("app.log"),
            logging.StreamHandler(sys.stdout)
        ]
    )

# Configuration initiale
setup_logging()

# Logger principal
logger = logging.getLogger("mcp_research_app")

def log_tool_call(tool_name: str, inputs: Dict[str, Any], outputs: Dict[str, Any], success: bool = True):
    """Journalise un appel d'outil avec ses entrées et sorties"""
    # Nettoyage des données sensibles
    sanitized_inputs = sanitize_log_data(inputs)
    sanitized_outputs = sanitize_log_data(outputs)
    
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "tool": tool_name,
        "inputs": sanitized_inputs,
        "outputs": sanitized_outputs,
        "success": success
    }
    
    if success:
        logger.info(f"Appel d'outil: {json.dumps(log_entry, default=str)}")
    else:
        logger.error(f"Échec d'appel d'outil: {json.dumps(log_entry, default=str)}")

def sanitize_log_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """Nettoie les données de journalisation pour enlever les informations sensibles"""
    if not isinstance(data, dict):
        return data
    
    sanitized = data.copy()
    
    # Liste des champs potentiellement sensibles
    sensitive_fields = ['api_key', 'password', 'secret', 'token', 'key', 'credentials']
    
    for field in sensitive_fields:
        if field in sanitized:
            sanitized[field] = '***REDACTED***'
    
    # Nettoyage récursif des sous-dictionnaires
    for key, value in sanitized.items():
        if isinstance(value, dict):
            sanitized[key] = sanitize_log_data(value)
        elif isinstance(value, list):
            sanitized[key] = [sanitize_log_data(item) if isinstance(item, dict) else item for item in value]
    
    return sanitized