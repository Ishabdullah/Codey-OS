#!/usr/bin/env python3
"""
Symbolic Graph Layer — Mentalese Engine for Codey-OS.

Inserts a structured concept graph between the planner and coder.
The planner converts natural language into graph operations; the graph
engine executes those operations against a persistent SQLite-backed
NetworkX graph; the coder renders the graph state back to natural language.

Graph structure:
  - Nodes: concepts with language-agnostic UUIDs, labels, and metadata
  - Edges: typed relationships (causal, spatial, possessive, agentive, temporal)

Operations:
  OBSERVE   — add an observation node with multilingual utterances
  CAUSE     — add a causal edge between two concepts
  POSSESS   — add a possessive edge (A owns/has B)
  AGENTIVE  — add an agentive edge (A acts on B)
  SPATIAL   — add a spatial edge (A is at/in B)
  TEMPORAL  — add a temporal edge (A happens before B)
  INTEND    — add an intention node (goal state)
  QUERY     — retrieve subgraph matching criteria

Persistence:
  SQLite-backed (WAL mode) for crash recovery and cross-session state.
  NetworkX graph is rebuilt from SQLite on startup.
"""

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from utils.config import STATE_DB_FILE
from utils.logger import error, info, success, warning


# ── Graph Operation Types ─────────────────────────────────────────────────────


class GraphOp(Enum):
    OBSERVE = "observe"
    CAUSE = "cause"
    POSSESS = "possess"
    AGENTIVE = "agentive"
    SPATIAL = "spatial"
    TEMPORAL = "temporal"
    INTEND = "intend"
    QUERY = "query"


# ── Data Classes ──────────────────────────────────────────────────────────────


@dataclass
class Concept:
    id: str
    label: str
    utterances: Dict[str, str] = field(default_factory=dict)  # lang -> text
    node_type: str = "entity"  # entity, action, state, intention
    created_at: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Relation:
    source_id: str
    target_id: str
    relation_type: str  # cause, possess, agentive, spatial, temporal
    weight: float = 1.0
    created_at: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphOperation:
    op: GraphOp
    args: Dict[str, Any]


# ── Symbolic Graph Engine ─────────────────────────────────────────────────────


class SymbolicGraph:
    """
    Persistent symbolic concept graph backed by SQLite + NetworkX.

    Nodes are concepts with language-agnostic UUIDs.
    Edges are typed relationships between concepts.
    The graph is rebuilt from SQLite on each session start.
    """

    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            STATE_DB_FILE.parent.mkdir(parents=True, exist_ok=True)
            db_path = STATE_DB_FILE
        self.db_path = db_path
        self._concepts: Dict[str, Concept] = {}
        self._relations: List[Relation] = []
        self._nx_graph = None  # lazy NetworkX graph
        self._init_schema()

    # ── Schema ────────────────────────────────────────────────────────────────

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_schema(self):
        conn = self._get_conn()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS sg_concepts (
                    id TEXT PRIMARY KEY,
                    label TEXT NOT NULL,
                    node_type TEXT NOT NULL DEFAULT 'entity',
                    created_at REAL NOT NULL,
                    metadata TEXT DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS sg_utterances (
                    concept_id TEXT NOT NULL,
                    lang TEXT NOT NULL,
                    text TEXT NOT NULL,
                    PRIMARY KEY (concept_id, lang),
                    FOREIGN KEY (concept_id) REFERENCES sg_concepts(id)
                );
                CREATE TABLE IF NOT EXISTS sg_relations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    relation_type TEXT NOT NULL,
                    weight REAL NOT NULL DEFAULT 1.0,
                    created_at REAL NOT NULL,
                    metadata TEXT DEFAULT '{}',
                    FOREIGN KEY (source_id) REFERENCES sg_concepts(id),
                    FOREIGN KEY (target_id) REFERENCES sg_concepts(id)
                );
                CREATE TABLE IF NOT EXISTS sg_episodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    observation TEXT NOT NULL,
                    lang TEXT NOT NULL DEFAULT 'en',
                    graph_snapshot TEXT DEFAULT '{}',
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_sg_utt_lang ON sg_utterances(lang);
                CREATE INDEX IF NOT EXISTS idx_sg_rel_src ON sg_relations(source_id);
                CREATE INDEX IF NOT EXISTS idx_sg_rel_tgt ON sg_relations(target_id);
            """)
            conn.commit()
        finally:
            conn.close()

    # ── Load from DB ──────────────────────────────────────────────────────────

    def _load_graph(self):
        """Rebuild in-memory state from SQLite."""
        # Clear existing state to avoid duplicates
        self._concepts.clear()
        self._relations.clear()

        conn = self._get_conn()
        try:
            # Load concepts
            for row in conn.execute("SELECT * FROM sg_concepts"):
                cid = row["id"]
                meta = json.loads(row["metadata"]) if row["metadata"] else {}
                self._concepts[cid] = Concept(
                    id=cid,
                    label=row["label"],
                    node_type=row["node_type"],
                    created_at=row["created_at"],
                    metadata=meta,
                )

            # Load utterances
            for row in conn.execute("SELECT * FROM sg_utterances"):
                cid = row["concept_id"]
                if cid in self._concepts:
                    self._concepts[cid].utterances[row["lang"]] = row["text"]

            # Load relations
            for row in conn.execute("SELECT * FROM sg_relations"):
                meta = json.loads(row["metadata"]) if row["metadata"] else {}
                self._relations.append(Relation(
                    source_id=row["source_id"],
                    target_id=row["target_id"],
                    relation_type=row["relation_type"],
                    weight=row["weight"],
                    created_at=row["created_at"],
                    metadata=meta,
                ))
        finally:
            conn.close()

    def _get_nx(self):
        """Lazy-load NetworkX graph."""
        if self._nx_graph is None:
            try:
                import networkx as nx
            except ImportError:
                warning("networkx not installed — symbolic graph runs without NetworkX")
                return None
            self._nx_graph = nx.DiGraph()
            for cid, concept in self._concepts.items():
                self._nx_graph.add_node(
                    cid,
                    label=concept.label,
                    node_type=concept.node_type,
                    utterances=concept.utterances,
                )
            for rel in self._relations:
                self._nx_graph.add_edge(
                    rel.source_id,
                    rel.target_id,
                    relation_type=rel.relation_type,
                    weight=rel.weight,
                )
        return self._nx_graph

    # ── Public API ────────────────────────────────────────────────────────────

    def execute(self, op: GraphOperation) -> Dict[str, Any]:
        """Execute a graph operation and return the result."""
        self._load_graph()

        handlers = {
            GraphOp.OBSERVE: self._op_observe,
            GraphOp.CAUSE: self._op_cause,
            GraphOp.POSSESS: self._op_possess,
            GraphOp.AGENTIVE: self._op_agentive,
            GraphOp.SPATIAL: self._op_spatial,
            GraphOp.TEMPORAL: self._op_temporal,
            GraphOp.INTEND: self._op_intend,
            GraphOp.QUERY: self._op_query,
        }

        handler = handlers.get(op.op)
        if not handler:
            return {"error": f"Unknown operation: {op.op}"}

        try:
            result = handler(op.args)
            self._nx_graph = None  # invalidate NetworkX cache
            return result
        except Exception as e:
            error(f"Graph operation {op.op.value} failed: {e}")
            return {"error": str(e)}

    def execute_batch(self, ops: List[GraphOperation]) -> List[Dict[str, Any]]:
        """Execute a batch of graph operations."""
        self._load_graph()
        results = []
        for op in ops:
            results.append(self.execute(op))
        return results

    def get_graph_state(self) -> Dict[str, Any]:
        """Return the full graph state as a JSON-serializable dict."""
        self._load_graph()
        nodes = []
        for c in self._concepts.values():
            nodes.append({
                "id": c.id,
                "label": c.label,
                "utterances": c.utterances,
                "node_type": c.node_type,
            })
        edges = []
        for r in self._relations:
            edges.append({
                "source": r.source_id,
                "target": r.target_id,
                "relation_type": r.relation_type,
                "weight": r.weight,
            })
        return {"nodes": nodes, "edges": edges}

    def get_graph_state_json(self) -> str:
        """Return graph state as a JSON string."""
        return json.dumps(self.get_graph_state(), ensure_ascii=False)

    def get_adjacency_list(self) -> str:
        """Return NetworkX-style JSON adjacency list for training data."""
        nx_g = self._get_nx()
        if nx_g is None:
            # Fallback without NetworkX
            return json.dumps(self.get_graph_state(), ensure_ascii=False)
        try:
            import networkx as nx
            return json.dumps(nx.adjacency_data(nx_g), ensure_ascii=False)
        except Exception:
            return json.dumps(self.get_graph_state(), ensure_ascii=False)

    def find_concept(self, label: str, lang: str = "en") -> Optional[Concept]:
        """Find a concept by label in any language."""
        self._load_graph()
        label_lower = label.lower()
        for concept in self._concepts.values():
            for utt_lang, text in concept.utterances.items():
                if text.lower() == label_lower:
                    return concept
            if concept.label.lower() == label_lower:
                return concept
        return None

    def find_related(
        self, concept_id: str, relation_type: Optional[str] = None
    ) -> List[Tuple[Concept, Relation]]:
        """Find all concepts related to a given concept."""
        self._load_graph()
        results = []
        for rel in self._relations:
            target_id = None
            if rel.source_id == concept_id:
                target_id = rel.target_id
            elif rel.target_id == concept_id:
                target_id = rel.source_id

            if target_id and relation_type and rel.relation_type != relation_type:
                continue
            if target_id and target_id in self._concepts:
                results.append((self._concepts[target_id], rel))
        return results

    def to_natural_language(self, lang: str = "en", max_depth: int = 2) -> str:
        """
        Render the graph state as natural language descriptions.
        Used by the coder to generate output from graph state.
        """
        self._load_graph()
        if not self._concepts:
            return "No concepts in graph."

        lines = []
        for concept in self._concepts.values():
            text = concept.utterances.get(lang, concept.label)
            lines.append(f"Concept: {text} (type={concept.node_type})")

            related = self.find_related(concept.id)
            for target, rel in related:
                target_text = target.utterances.get(lang, target.label)
                lines.append(f"  --[{rel.relation_type}]--> {target_text}")

        return "\n".join(lines)

    def clear(self):
        """Clear the entire graph."""
        conn = self._get_conn()
        try:
            conn.executescript("""
                DELETE FROM sg_relations;
                DELETE FROM sg_utterances;
                DELETE FROM sg_concepts;
                DELETE FROM sg_episodes;
            """)
            conn.commit()
        finally:
            conn.close()
        self._concepts.clear()
        self._relations.clear()
        self._nx_graph = None

    def status(self) -> Dict[str, Any]:
        """Return graph statistics."""
        self._load_graph()
        return {
            "concepts": len(self._concepts),
            "relations": len(self._relations),
            "node_types": {},
            "relation_types": {},
        }

    # ── Operation Handlers ────────────────────────────────────────────────────

    def _op_observe(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """OBSERVE: Add an observation as a concept node with multilingual utterances."""
        label = args.get("label", "")
        utterances = args.get("utterances", {})
        node_type = args.get("node_type", "entity")
        observation = args.get("observation", "")

        if not label and utterances:
            label = utterances.get("en", list(utterances.values())[0])
        if not label:
            return {"error": "OBSERVE requires label or utterances"}

        concept_id = str(uuid.uuid4())[:8]
        now = time.time()

        concept = Concept(
            id=concept_id,
            label=label,
            utterances=utterances or {"en": label},
            node_type=node_type,
            created_at=now,
        )
        self._concepts[concept_id] = concept

        # Persist to SQLite
        conn = self._get_conn()
        try:
            conn.execute(
                "INSERT INTO sg_concepts (id, label, node_type, created_at, metadata) VALUES (?, ?, ?, ?, ?)",
                (concept_id, label, node_type, now, "{}"),
            )
            for lang, text in concept.utterances.items():
                conn.execute(
                    "INSERT INTO sg_utterances (concept_id, lang, text) VALUES (?, ?, ?)",
                    (concept_id, lang, text),
                )

            # Store episode
            if observation:
                conn.execute(
                    "INSERT INTO sg_episodes (observation, lang, graph_snapshot, created_at) VALUES (?, ?, ?, ?)",
                    (observation, args.get("lang", "en"), self.get_graph_state_json(), now),
                )
            conn.commit()
        finally:
            conn.close()

        return {"concept_id": concept_id, "label": label}

    def _op_cause(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """CAUSE: Add a causal edge (A causes B)."""
        return self._add_relation(args, "cause")

    def _op_possess(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """POSSESS: Add a possessive edge (A has/owns B)."""
        return self._add_relation(args, "possess")

    def _op_agentive(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """AGENTIVE: Add an agentive edge (A acts on B)."""
        return self._add_relation(args, "agentive")

    def _op_spatial(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """SPATIAL: Add a spatial edge (A is at/in B)."""
        return self._add_relation(args, "spatial")

    def _op_temporal(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """TEMPORAL: Add a temporal edge (A before B)."""
        return self._add_relation(args, "temporal")

    def _op_intend(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """INTEND: Add an intention/goal node."""
        args["node_type"] = "intention"
        return self._op_observe(args)

    def _op_query(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """QUERY: Retrieve graph information matching criteria."""
        concept_label = args.get("concept")
        relation_type = args.get("relation")
        lang = args.get("lang", "en")
        max_results = args.get("max_results", 10)

        if concept_label:
            concept = self.find_concept(concept_label, lang)
            if not concept:
                return {"results": [], "message": f"Concept '{concept_label}' not found"}

            related = self.find_related(concept.id, relation_type)
            results = []
            for target, rel in related[:max_results]:
                text = target.utterances.get(lang, target.label)
                results.append({
                    "concept": text,
                    "relation": rel.relation_type,
                    "node_type": target.node_type,
                })
            return {"results": results, "source": concept.utterances.get(lang, concept.label)}

        # Return all concepts
        results = []
        for c in list(self._concepts.values())[:max_results]:
            text = c.utterances.get(lang, c.label)
            results.append({"concept": text, "node_type": c.node_type})
        return {"results": results}

    def _add_relation(self, args: Dict[str, Any], relation_type: str) -> Dict[str, Any]:
        """Add a relation between two concepts."""
        source_id = args.get("source_id")
        target_id = args.get("target_id")
        source_label = args.get("source")
        target_label = args.get("target")
        lang = args.get("lang", "en")

        # Resolve labels to IDs if needed
        if not source_id and source_label:
            concept = self.find_concept(source_label, lang)
            if concept:
                source_id = concept.id
            else:
                # Auto-create the concept
                result = self._op_observe({
                    "label": source_label,
                    "utterances": {lang: source_label},
                    "node_type": "entity",
                })
                source_id = result.get("concept_id")

        if not target_id and target_label:
            concept = self.find_concept(target_label, lang)
            if concept:
                target_id = concept.id
            else:
                result = self._op_observe({
                    "label": target_label,
                    "utterances": {lang: target_label},
                    "node_type": "entity",
                })
                target_id = result.get("concept_id")

        if not source_id or not target_id:
            return {"error": f"Cannot resolve concepts: source={source_label}, target={target_label}"}

        weight = args.get("weight", 1.0)
        now = time.time()

        rel = Relation(
            source_id=source_id,
            target_id=target_id,
            relation_type=relation_type,
            weight=weight,
            created_at=now,
        )
        self._relations.append(rel)

        conn = self._get_conn()
        try:
            conn.execute(
                "INSERT INTO sg_relations (source_id, target_id, relation_type, weight, created_at, metadata) VALUES (?, ?, ?, ?, ?, ?)",
                (source_id, target_id, relation_type, weight, now, "{}"),
            )
            conn.commit()
        finally:
            conn.close()

        return {
            "source": source_id,
            "target": target_id,
            "relation_type": relation_type,
        }

    # ── Consistency Check ─────────────────────────────────────────────────────

    def check_consistency(self) -> List[str]:
        """
        Check the graph for logical inconsistencies.
        Returns a list of issue descriptions.
        """
        self._load_graph()
        issues = []

        # Check for dangling references
        concept_ids = set(self._concepts.keys())
        for rel in self._relations:
            if rel.source_id not in concept_ids:
                issues.append(f"Dangling source: {rel.source_id}")
            if rel.target_id not in concept_ids:
                issues.append(f"Dangling target: {rel.target_id}")

        # Check for cycles in causal graph
        nx_g = self._get_nx()
        if nx_g is not None:
            try:
                import networkx as nx
                causal_edges = [
                    (u, v) for u, v, d in nx_g.edges(data=True)
                    if d.get("relation_type") == "cause"
                ]
                if causal_edges:
                    causal_subgraph = nx.DiGraph(causal_edges)
                    cycles = list(nx.simple_cycles(causal_subgraph))
                    for cycle in cycles:
                        issues.append(f"Causal cycle: {' -> '.join(cycle)}")
            except Exception:
                pass

        return issues


# ── Global Singleton ──────────────────────────────────────────────────────────

_graph: Optional[SymbolicGraph] = None


def get_symbolic_graph() -> SymbolicGraph:
    """Get (or create) the global SymbolicGraph singleton."""
    global _graph
    if _graph is None:
        _graph = SymbolicGraph()
    return _graph


def reset_symbolic_graph():
    """Reset the global singleton (for testing)."""
    global _graph
    _graph = None


def parse_graph_ops(text: str) -> List[GraphOperation]:
    """
    Parse graph operations from planner output.

    The planner outputs structured operations in this format:
      OBSERVE: label="user wants X", utterances={"en": "user wants X"}
      CAUSE: source="A", target="B"
      ...

    Returns a list of GraphOperation objects.
    """
    ops = []
    for line in text.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # Parse "OP: key=value, key=value" format
        colon_idx = line.find(":")
        if colon_idx == -1:
            continue

        op_name = line[:colon_idx].strip().upper()
        args_str = line[colon_idx + 1:].strip()

        try:
            op_type = GraphOp(op_name.lower())
        except ValueError:
            warning(f"Unknown graph op: {op_name}")
            continue

        # Parse key=value pairs (handles quoted strings and dicts)
        args = {}
        for part in _split_args(args_str):
            eq_idx = part.find("=")
            if eq_idx == -1:
                continue
            key = part[:eq_idx].strip()
            val = part[eq_idx + 1:].strip()
            # Remove surrounding quotes
            if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                val = val[1:-1]
            # Try to parse as JSON (for dicts/lists)
            elif val.startswith("{") or val.startswith("["):
                try:
                    val = json.loads(val)
                except json.JSONDecodeError:
                    pass
            args[key] = val

        ops.append(GraphOperation(op=op_type, args=args))

    return ops


def _split_args(args_str: str) -> List[str]:
    """Split argument string respecting quoted strings and nested dicts."""
    parts = []
    current = ""
    depth = 0
    in_quote = None

    for ch in args_str:
        if ch in ('"', "'") and not in_quote:
            in_quote = ch
            current += ch
        elif ch == in_quote:
            in_quote = None
            current += ch
        elif ch == "{" and not in_quote:
            depth += 1
            current += ch
        elif ch == "}" and not in_quote:
            depth -= 1
            current += ch
        elif ch == "," and depth == 0 and not in_quote:
            parts.append(current.strip())
            current = ""
        else:
            current += ch

    if current.strip():
        parts.append(current.strip())

    return parts
