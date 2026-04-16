"""Graph data extraction from Lucent SQLite database.

Reads nodes and edges from a Lucent SQLite database in read-only mode
and returns them in a format suitable for Cytoscape.js visualization.
"""

import json
import sqlite3


def get_graph_data(db_path: str, limit: int = 400) -> dict:
    """Extract graph data from a Lucent SQLite database.

    Opens the database in read-only mode and queries up to `limit` nodes
    and their connecting edges. Edges referencing nodes outside the
    returned set are filtered out.

    Args:
        db_path: Path to the lucent.db SQLite file.
        limit: Maximum number of nodes to return (default 400).

    Returns:
        Dict with "nodes" and "edges" lists. On error, includes an
        "error" key and empty lists.
    """
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
    except sqlite3.OperationalError as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    try:
        # Query nodes up to the limit
        cursor = conn.execute(
            "SELECT id, type, name, first_name, last_name, properties "
            "FROM nodes ORDER BY id LIMIT ?",
            (limit,)
        )
        rows = cursor.fetchall()

        nodes = []
        node_ids: set[int] = set()
        for row in rows:
            node_id = row["id"]
            node_ids.add(node_id)

            # Label: prefer first_name, fall back to name
            label = row["first_name"] if row["first_name"] else row["name"]

            # Parse properties JSON
            props_raw = row["properties"] or "{}"
            try:
                properties = json.loads(props_raw)
            except (json.JSONDecodeError, TypeError):
                properties = {}

            nodes.append({
                "id": str(node_id),
                "label": label,
                "type": row["type"],
                "properties": properties,
            })

        # Query all edges and filter to only those connecting returned nodes
        edge_cursor = conn.execute(
            "SELECT source_id, target_id, type FROM edges"
        )
        edge_rows = edge_cursor.fetchall()

        edges = []
        for edge in edge_rows:
            src = edge["source_id"]
            tgt = edge["target_id"]
            if src in node_ids and tgt in node_ids:
                edges.append({
                    "source": str(src),
                    "target": str(tgt),
                    "label": edge["type"],
                })

        return {"nodes": nodes, "edges": edges}

    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}
    finally:
        conn.close()
