import os, json
from typing import Dict, Any

CONFIG_PATH = os.environ.get("MCP_SERVERS_CONFIG", "config/mcp_servers.json")

def load_mcp_config() -> Dict[str, Any]:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    # Expand env vars for each arg
    def expand(x):
        return os.path.expandvars(x) if isinstance(x, str) else x
    for name, spec in data.items():
        spec["args"] = [expand(a) for a in spec.get("args", [])]
    return data
