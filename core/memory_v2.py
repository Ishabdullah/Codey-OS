#!/usr/bin/env python3
"""
Hierarchical Memory for Codey-V3 (v3.0.0 — Symbolic Graph Integration).

Five-tier memory system:
1. Working Memory   — currently edited files (LRU eviction by turn + token limit)
2. Project Memory   — key project files (CODEY.md, config) — never evicted
3. Long-term Memory — semantic search via multilingual embeddings (SQLite-backed)
4. Episodic Memory  — raw observations with language tags
5. Symbolic Memory  — concept graph (language-agnostic UUIDs, typed relations)

The symbolic graph sits between planner and coder:
  - Planner output -> graph operations -> graph state -> coder input
  - RAG queries first hit the symbolic graph, then fetch language renderings
  - All embeddings are in a multilingual vector space

SQLite schema additions:
  sg_concepts:    abstract nodes (language-agnostic UUIDs)
  sg_relations:   edges between concepts with typed predicates
  sg_utterances:  multilingual text renderings of concepts
  sg_episodes:    raw observations with graph snapshots
  longterm_embeddings: multilingual vector representations
"""

import os
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from core.tokens import estimate_tokens
from utils.config import MODEL_CONFIG
from utils.logger import info, warning

# ── Token budget constants ───────────────────────────────────────────────────
CTX_TOTAL = MODEL_CONFIG["n_ctx"]
BUDGET_SUMMARY = 1200
BUDGET_FILES = 6000
MAX_FILE_CONTEXT_TOKENS = 12000
LRU_EVICT_AFTER = 3


# ────────────────────────────────────────────────────────────────────────────
# Tier 1 — Working Memory
# ────────────────────────────────────────────────────────────────────────────


@dataclass
class WorkingMemoryItem:
    file_path: str
    content: str
    tokens: int
    loaded_at: int
    last_used_at: int
    last_used_turn: int = 0
    access_count: int = 1

    @property
    def name(self) -> str:
        return Path(self.file_path).name

    def relevance_score(self, message: str) -> float:
        msg_words = set(re.findall(r"\w+", message.lower()))
        file_words = set(re.findall(r"\w+", self.content.lower()))
        name_words = set(re.findall(r"\w+", self.name.lower()))
        name_overlap = len(msg_words & name_words) * 3
        content_overlap = len(msg_words & file_words)
        if not msg_words:
            return 0.5
        return min(1.0, (name_overlap + content_overlap) / (len(msg_words) + 1))


class WorkingMemory:
    def __init__(self, max_tokens: int = MAX_FILE_CONTEXT_TOKENS):
        self.max_tokens = max_tokens
        self._files: Dict[str, WorkingMemoryItem] = {}
        self._turn: int = 0

    def add(self, file_path: str, content: str, tokens: int):
        now = int(time.time())
        if file_path in self._files:
            item = self._files[file_path]
            item.content = content
            item.tokens = tokens
            item.last_used_at = now
            item.last_used_turn = self._turn
            item.access_count += 1
        else:
            self._files[file_path] = WorkingMemoryItem(
                file_path=file_path,
                content=content,
                tokens=tokens,
                loaded_at=now,
                last_used_at=now,
                last_used_turn=self._turn,
            )
        self._evict_by_tokens()

    def get(self, file_path: str) -> Optional[str]:
        item = self._files.get(file_path)
        if item:
            item.last_used_at = int(time.time())
            item.last_used_turn = self._turn
            item.access_count += 1
            return item.content
        return None

    def touch(self, file_path: str):
        item = self._files.get(file_path)
        if item:
            item.last_used_at = int(time.time())
            item.last_used_turn = self._turn
            item.access_count += 1

    def remove(self, file_path: str):
        if file_path in self._files:
            del self._files[file_path]

    def clear(self):
        count = len(self._files)
        self._files.clear()
        if count:
            info(f"Working memory: cleared {count} files")

    def evict_stale(self):
        stale = [
            k
            for k, item in self._files.items()
            if self._turn - item.last_used_turn > LRU_EVICT_AFTER
        ]
        for k in stale:
            info(f"Working memory: evicted stale file {Path(k).name}")
            del self._files[k]

    def _evict_by_tokens(self):
        total = sum(f.tokens for f in self._files.values())
        while total > self.max_tokens and self._files:
            candidates = {k: v for k, v in self._files.items() if v.last_used_turn < self._turn}
            if not candidates:
                break
            lru = min(candidates, key=lambda k: candidates[k].last_used_at)
            evicted = self._files.pop(lru)
            total -= evicted.tokens
            info(f"Working memory: token-evicted {evicted.name} ({evicted.tokens} tokens)")

    def select_for_context(
        self, message: str, budget: int = BUDGET_FILES
    ) -> List[WorkingMemoryItem]:
        if not self._files:
            return []
        effective = min(budget, MAX_FILE_CONTEXT_TOKENS)
        scored = sorted(
            self._files.values(),
            key=lambda item: (item.relevance_score(message), item.last_used_turn),
            reverse=True,
        )
        selected: List[WorkingMemoryItem] = []
        used = 0
        for item in scored:
            if used + item.tokens <= effective:
                selected.append(item)
                used += item.tokens
            else:
                remaining = effective - used
                marker = "\n...[truncated]"
                code_exts = {".py", ".js", ".ts", ".c", ".cpp", ".h", ".rs", ".go"}
                multiplier = 3 if any(item.file_path.endswith(e) for e in code_exts) else 4
                marker_tokens = len(marker) // multiplier
                if remaining > marker_tokens + 10:
                    max_chars = remaining * multiplier + (multiplier - 1)
                    truncated_content = item.content[: max_chars - len(marker)] + marker
                    trunc_tokens = estimate_tokens(truncated_content, item.file_path)
                    if used + trunc_tokens <= effective:
                        trunc_item = WorkingMemoryItem(
                            file_path=item.file_path,
                            content=truncated_content,
                            tokens=trunc_tokens,
                            loaded_at=item.loaded_at,
                            last_used_at=item.last_used_at,
                            last_used_turn=item.last_used_turn,
                        )
                        selected.append(trunc_item)
                break
        return selected

    def build_file_block(self, message: str) -> str:
        selected = self.select_for_context(message)
        if not selected:
            return ""
        blocks = [f'<file path="{item.name}">\n{item.content}\n</file>' for item in selected]
        return "\n".join(blocks)

    def tick(self):
        self._turn += 1

    def get_all(self) -> Dict[str, str]:
        return {k: v.content for k, v in self._files.items()}

    def get_file_names(self) -> List[str]:
        return list(self._files.keys())

    def status(self) -> dict:
        return {
            "files": len(self._files),
            "file_names": [item.name for item in self._files.values()],
            "total_tokens": sum(item.tokens for item in self._files.values()),
            "turn": self._turn,
        }


# ────────────────────────────────────────────────────────────────────────────
# Tier 2 — Project Memory
# ────────────────────────────────────────────────────────────────────────────


@dataclass
class ProjectMemoryItem:
    file_path: str
    content_hash: str
    loaded_at: int
    is_protected: bool


class ProjectMemory:
    def __init__(self):
        self._files: Dict[str, ProjectMemoryItem] = {}
        self._protected_patterns = [
            "CODEY.md", "codey-v3.md", "README.md", "config.py", "config.json",
        ]

    def add(self, file_path: str, content: str, is_protected: bool = False):
        import hashlib
        content_hash = hashlib.md5(content.encode()).hexdigest()
        self._files[file_path] = ProjectMemoryItem(
            file_path=file_path,
            content_hash=content_hash,
            loaded_at=int(time.time()),
            is_protected=is_protected or self._is_protected(file_path),
        )

    def get(self, file_path: str) -> Optional[str]:
        return file_path if file_path in self._files else None

    def is_tracked(self, file_path: str) -> bool:
        return file_path in self._files

    def _is_protected(self, file_path: str) -> bool:
        return any(p in file_path for p in self._protected_patterns)

    def get_protected_files(self) -> List[str]:
        return [f.file_path for f in self._files.values() if f.is_protected]

    def status(self) -> dict:
        return {
            "files": len(self._files),
            "protected": len(self.get_protected_files()),
        }


# ────────────────────────────────────────────────────────────────────────────
# Tier 3 — Long-term Memory (multilingual embeddings)
# ────────────────────────────────────────────────────────────────────────────


class LongTermMemory:
    """
    Long-term memory with multilingual semantic search.

    Uses paraphrase-multilingual-MiniLM-L12-v2 for embeddings.
    Same concept in English, Arabic, or Spanish maps to the same vector.
    """

    def __init__(self):
        self._store = None
        self._model = None
        self._available = False
        self._init_error: Optional[str] = None
        self._try_init()

    def _try_init(self):
        try:
            from core.embeddings import get_embedding_model, get_embedding_store
            self._store = get_embedding_store()
            self._model = get_embedding_model()
            self._available = True
        except Exception as e:
            self._init_error = str(e)

    def store_file(self, file_path: str, content: str) -> int:
        if not self._available:
            return 0
        try:
            from core.embeddings import chunk_text
            chunks = chunk_text(content)
            embeddings_data = []
            for chunk_text_item, start, end in chunks:
                embedding = self._model.embed(chunk_text_item)
                if embedding:
                    embeddings_data.append((file_path, start, end, embedding))
            if embeddings_data:
                return self._store.store_batch(embeddings_data)
        except Exception as e:
            warning(f"Long-term memory store_file failed: {e}")
        return 0

    def search(self, query: str, limit: int = 5) -> List[Dict]:
        if not self._available:
            return []
        try:
            query_embedding = self._model.embed(query)
            if not query_embedding:
                return []
            return self._store.search(query_embedding, limit)
        except Exception:
            return []

    def remove_file(self, file_path: str) -> int:
        if not self._available:
            return 0
        try:
            return self._store.delete_by_file(file_path)
        except Exception:
            return 0

    def count(self) -> int:
        if not self._available:
            return 0
        try:
            return self._store.count()
        except Exception:
            return 0

    def status(self) -> dict:
        return {
            "available": self._available,
            "embeddings": self.count(),
            "init_error": self._init_error,
        }


# ────────────────────────────────────────────────────────────────────────────
# Tier 4 — Episodic Memory (raw observations)
# ────────────────────────────────────────────────────────────────────────────


class EpisodicMemory:
    """
    Episodic memory — append-only log of observations.

    Stores raw user inputs and observations with language tags.
    Each episode can include a graph snapshot for reconstruction.
    """

    def __init__(self):
        try:
            from core.state import get_state_store
            self._state = get_state_store()
        except Exception:
            self._state = None

    def log(self, action: str, details: str = None):
        if self._state and hasattr(self._state, "log_action"):
            try:
                self._state.log_action(action, details)
            except Exception:
                pass

    def log_observation(self, observation: str, lang: str = "en", graph_snapshot: str = "{}"):
        """Log a raw observation with language tag and optional graph snapshot."""
        if self._state:
            try:
                import json
                self._state.log_action(
                    "observation",
                    json.dumps({
                        "text": observation,
                        "lang": lang,
                        "graph": graph_snapshot,
                    }, ensure_ascii=False),
                )
            except Exception:
                pass

    def get_recent(self, limit: int = 50) -> List[Dict]:
        if self._state and hasattr(self._state, "get_recent_actions"):
            try:
                return self._state.get_recent_actions(limit)
            except Exception:
                pass
        return []

    def get_since(self, timestamp: int) -> List[Dict]:
        if self._state and hasattr(self._state, "get_actions_since"):
            try:
                return self._state.get_actions_since(timestamp)
            except Exception:
                pass
        return []

    def status(self) -> dict:
        return {"recent_actions": len(self.get_recent(10))}


# ────────────────────────────────────────────────────────────────────────────
# Tier 5 — Symbolic Memory (concept graph)
# ────────────────────────────────────────────────────────────────────────────


class SymbolicMemory:
    """
    Symbolic memory layer backed by the SymbolicGraph.

    Provides a high-level interface for:
    - Converting observations to graph operations
    - Querying the graph for related concepts
    - Rendering graph state as natural language
    - Checking logical consistency
    """

    def __init__(self):
        self._graph = None
        self._available = False
        self._init_error: Optional[str] = None
        self._try_init()

    def _try_init(self):
        try:
            from core.symbolic_graph import get_symbolic_graph
            self._graph = get_symbolic_graph()
            self._available = True
        except Exception as e:
            self._init_error = str(e)

    def observe(self, label: str, utterances: Dict[str, str] = None, node_type: str = "entity"):
        """Add an observation to the graph."""
        if not self._available:
            return None
        from core.symbolic_graph import GraphOperation, GraphOp
        op = GraphOperation(
            op=GraphOp.OBSERVE,
            args={"label": label, "utterances": utterances or {}, "node_type": node_type},
        )
        return self._graph.execute(op)

    def relate(self, source: str, target: str, relation_type: str, lang: str = "en"):
        """Add a relation between two concepts."""
        if not self._available:
            return None
        from core.symbolic_graph import GraphOperation, GraphOp
        op_map = {
            "cause": GraphOp.CAUSE,
            "possess": GraphOp.POSSESS,
            "agentive": GraphOp.AGENTIVE,
            "spatial": GraphOp.SPATIAL,
            "temporal": GraphOp.TEMPORAL,
        }
        op_type = op_map.get(relation_type)
        if not op_type:
            return None
        op = GraphOperation(
            op=op_type,
            args={"source": source, "target": target, "lang": lang},
        )
        return self._graph.execute(op)

    def query(self, concept: str = None, relation: str = None, lang: str = "en"):
        """Query the graph for concepts and relations."""
        if not self._available:
            return {"results": []}
        from core.symbolic_graph import GraphOperation, GraphOp
        op = GraphOperation(
            op=GraphOp.QUERY,
            args={"concept": concept, "relation": relation, "lang": lang},
        )
        return self._graph.execute(op)

    def get_state(self) -> Dict:
        """Get the full graph state."""
        if not self._available:
            return {"nodes": [], "edges": []}
        return self._graph.get_graph_state()

    def get_state_json(self) -> str:
        """Get graph state as JSON string."""
        if not self._available:
            return '{"nodes": [], "edges": []}'
        return self._graph.get_graph_state_json()

    def get_adjacency_list(self) -> str:
        """Get NetworkX-style adjacency list for training data."""
        if not self._available:
            return '{"nodes": [], "edges": []}'
        return self._graph.get_adjacency_list()

    def to_natural_language(self, lang: str = "en") -> str:
        """Render graph state as natural language."""
        if not self._available:
            return ""
        return self._graph.to_natural_language(lang)

    def check_consistency(self) -> List[str]:
        """Check graph for logical inconsistencies."""
        if not self._available:
            return []
        return self._graph.check_consistency()

    def clear(self):
        """Clear the entire graph."""
        if self._available:
            self._graph.clear()

    def status(self) -> dict:
        if not self._available:
            return {"available": False, "init_error": self._init_error}
        graph_status = self._graph.status()
        return {
            "available": True,
            "concepts": graph_status["concepts"],
            "relations": graph_status["relations"],
        }


# ────────────────────────────────────────────────────────────────────────────
# Unified Memory — combines all five tiers
# ────────────────────────────────────────────────────────────────────────────


class Memory:
    """
    Unified hierarchical memory system with symbolic graph integration.

    Five tiers:
    1. Working Memory  — currently loaded files
    2. Project Memory  — protected project files
    3. Long-term Memory — multilingual semantic search
    4. Episodic Memory — action log with observations
    5. Symbolic Memory — concept graph (language-agnostic)
    """

    def __init__(self):
        self.working = WorkingMemory()
        self.project = ProjectMemory()
        self.longterm = LongTermMemory()
        self.episodic = EpisodicMemory()
        self.symbolic = SymbolicMemory()
        self._turn = 0
        self._summary = ""

    # ── File API ────────────────────────────────────────────────────────────

    def load_file(self, path: str, content: str = None) -> bool:
        p = Path(path).expanduser()
        if content is None:
            if not p.exists():
                p = Path(os.getcwd()) / path
            if not p.exists():
                return False
            try:
                content = p.read_text(encoding="utf-8", errors="replace")
            except Exception:
                return False
        key = str(p.resolve())
        tokens = estimate_tokens(content, key)
        self.working.add(key, content, tokens)
        return True

    def unload_file(self, path: str):
        key = str(Path(path).expanduser().resolve())
        self.working.remove(key)

    def touch_file(self, path: str):
        key = str(Path(path).expanduser().resolve())
        self.working.touch(key)

    def list_files(self) -> List[str]:
        return self.working.get_file_names()

    def build_file_block(self, message: str = "") -> str:
        return self.working.build_file_block(message)

    def select_files_for_context(self, message: str, budget: int = BUDGET_FILES) -> list:
        return self.working.select_for_context(message, budget)

    def evict_stale(self):
        self.working.evict_stale()

    # ── Summary ─────────────────────────────────────────────────────────────

    def append_to_summary(self, task: str, result: str):
        entry = f"[Turn {self._turn}] {task[:80]}: {result[:120]}"
        self._summary = (self._summary + "\n" + entry).strip()
        while estimate_tokens(self._summary) > BUDGET_SUMMARY:
            lines = self._summary.splitlines()
            if len(lines) <= 1:
                break
            self._summary = "\n".join(lines[1:])

    def compress_summary(self, history: list) -> list:
        if len(history) < 8:
            return history
        try:
            from core.inference_v2 import infer
            old_turns = history[:-4]
            fresh_turns = history[-4:]
            text = "\n".join(f"{m['role'].upper()}: {m['content'][:200]}" for m in old_turns)
            prompt = [
                {
                    "role": "system",
                    "content": (
                        "Summarize this conversation in 3-5 bullet points. "
                        "Be specific about files created, commands run, and errors fixed. "
                        "Max 200 words."
                    ),
                },
                {"role": "user", "content": text},
            ]
            compressed = infer(prompt, stream=False)
            if compressed and not compressed.startswith("[ERROR]"):
                ts = datetime.now().strftime("%H:%M")
                self._summary = f"[Session work as of {ts}]\n" + compressed.strip()
                info("Compressed old turns into summary.")
            return fresh_turns
        except Exception as e:
            warning(f"compress_summary failed: {e}")
            return history

    def get_summary(self) -> str:
        return self._summary

    # ── Turn management ──────────────────────────────────────────────────────

    def tick(self):
        self._turn += 1
        self.working.tick()
        self.working.evict_stale()
        self.episodic.log("tick", f"Turn {self._turn}")

    def clear(self):
        self.working.clear()
        self._summary = ""

    # ── Higher-level helpers ────────────────────────────────────────────────

    def add_to_working(self, file_path: str, content: str, tokens: int):
        key = str(Path(file_path).expanduser().resolve())
        self.working.add(key, content, tokens)

    def add_to_project(self, file_path: str, content: str, is_protected: bool = False):
        self.project.add(file_path, content, is_protected)

    def store_in_longterm(self, file_path: str, content: str):
        self.longterm.store_file(file_path, content)

    def log_action(self, action: str, details: str = None):
        self.episodic.log(action, details)

    def log_observation(self, observation: str, lang: str = "en"):
        """Log a raw observation and add to symbolic graph."""
        self.episodic.log_observation(observation, lang)
        if self.symbolic._available:
            self.symbolic.observe(observation, utterances={lang: observation})

    def search(self, query: str, limit: int = 5) -> List[Dict]:
        """Semantic search over long-term memory."""
        return self.longterm.search(query, limit)

    def search_symbolic(self, query: str, lang: str = "en") -> List[Dict]:
        """Search symbolic graph for related concepts."""
        result = self.symbolic.query(concept=query, lang=lang)
        return result.get("results", [])

    def get_graph_state(self) -> Dict:
        """Get the symbolic graph state."""
        return self.symbolic.get_state()

    def get_graph_state_json(self) -> str:
        """Get symbolic graph state as JSON."""
        return self.symbolic.get_state_json()

    def to_natural_language(self, lang: str = "en") -> str:
        """Render symbolic graph as natural language."""
        return self.symbolic.to_natural_language(lang)

    def get_working_content(self) -> Dict[str, str]:
        return self.working.get_all()

    def clear_working(self):
        self.working.clear()

    @property
    def _files(self) -> Dict[str, "WorkingMemoryItem"]:
        return self.working._files

    def status(self) -> dict:
        wstatus = self.working.status()
        return {
            "files": wstatus["files"],
            "file_names": wstatus["file_names"],
            "summary_tokens": estimate_tokens(self._summary),
            "turn": self._turn,
            "working": wstatus,
            "project": self.project.status(),
            "longterm": self.longterm.status(),
            "episodic": self.episodic.status(),
            "symbolic": self.symbolic.status(),
        }


# ── Global singleton ──────────────────────────────────────────────────────────

_memory: Optional[Memory] = None


def get_memory() -> Memory:
    global _memory
    if _memory is None:
        _memory = Memory()
    return _memory


def reset_memory():
    global _memory
    _memory = None


memory = get_memory()
