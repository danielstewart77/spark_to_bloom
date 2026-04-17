"""Graph data fetching from the hive_mind HTTP API.

Calls the /graph/data endpoint on the hive_mind gateway service and
returns nodes and edges in a format suitable for Cytoscape.js visualization.
"""

import json
import urllib.request


def get_graph_data(api_url: str, limit: int = 400) -> dict:
    """Fetch graph data from the hive_mind /graph/data endpoint.

    Args:
        api_url: Base URL of the hive_mind gateway (e.g. http://server:8420).
        limit: Maximum number of nodes to request.

    Returns:
        Dict with "nodes" and "edges" lists. On error, includes an
        "error" key and empty lists.
    """
    url = f"{api_url.rstrip('/')}/graph/data?limit={limit}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    return data
