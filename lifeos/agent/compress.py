"""Post-ingestion log compression — per D-15, D-16, D-17."""

import json
from pathlib import Path

import tiktoken
from google import genai
from google.genai import types

from lifeos.memory import graph as graph_module

LOG_COMPRESSION_THRESHOLD = 2000  # cl100k_base tokens

_enc = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    """Count tokens using tiktoken cl100k_base encoding."""
    return len(_enc.encode(text))


def needs_compression(log_json: str) -> bool:
    """Return True if log JSON exceeds the token threshold."""
    return count_tokens(log_json) > LOG_COMPRESSION_THRESHOLD


def load_prompt(path: str) -> str:
    """Load a prompt file from disk."""
    return Path(path).read_text(encoding="utf-8")


def compress_log(log_entries: list[dict], client: genai.Client) -> list[dict]:
    """Compress older log entries, keep last 3 intact. Returns new log list.

    Per COMP-03: recent (last 3) entries kept intact; older entries condensed.
    Per D-16: standalone Gemini call with compression prompt. No tools.
    """
    if len(log_entries) <= 3:
        return log_entries

    recent = log_entries[-3:]
    older = log_entries[:-3]

    prompt = load_prompt("prompts/compress.md")
    older_json = json.dumps(older, indent=2, default=str)

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=f"Compress these log entries:\n\n{older_json}",
        config=types.GenerateContentConfig(
            system_instruction=prompt,
            response_mime_type="application/json",
        ),
    )

    compressed_entry = json.loads(response.text)
    return [compressed_entry] + recent


def run_compression_pass(
    graph,
    modified_node_ids: list[str],
    modified_edge_ids: list[str],
    client: genai.Client,
) -> int:
    """Compress logs for all over-budget nodes and edges.

    Per D-15: runs after the agent finishes all graph writes.
    Uses set_node_log/set_edge_log (NOT update_node) to avoid spurious re-embedding.

    Returns the number of logs compressed.
    """
    compressed_count = 0

    for node_id in modified_node_ids:
        node = graph_module.get_node(graph, node_id)
        if node and node.get("log"):
            log_json = node["log"] if isinstance(node["log"], str) else json.dumps(node["log"])
            if needs_compression(log_json):
                log_entries = json.loads(log_json) if isinstance(log_json, str) else node["log"]
                new_log = compress_log(log_entries, client)
                graph_module.set_node_log(graph, node_id, new_log)
                compressed_count += 1

    for edge_id in modified_edge_ids:
        edge_data = graph.query(
            "MATCH ()-[r:EDGE {id: $id}]->() RETURN r.log",
            {"id": edge_id},
        )
        if edge_data.result_set and edge_data.result_set[0][0]:
            log_json = edge_data.result_set[0][0]
            if needs_compression(log_json):
                log_entries = json.loads(log_json)
                new_log = compress_log(log_entries, client)
                graph_module.set_edge_log(graph, edge_id, new_log)
                compressed_count += 1

    return compressed_count
