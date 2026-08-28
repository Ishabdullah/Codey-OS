"""
Domain Router — Multi-Domain Request Splitting & Dependency DAG for CCOS.

Per Track A / Phase A2 Item 4.7:
Taxonomy across domains: system, coding, crm, data, research, vision, speech.
Classifies requests into single vs multi-domain execution pipelines,
generates structured SubGoal DAGs, and maps cross-domain context I/O keys.
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from ccos.core.capability_registry import get_capability_registry


class Domain(str, Enum):
    SYSTEM = "system"
    CODING = "coding"
    CRM = "crm"
    DATA = "data"
    RESEARCH = "research"
    VISION = "vision"
    SPEECH = "speech"


DOMAIN_TAXONOMY: List[str] = [d.value for d in Domain]


DOMAIN_KEYWORDS: Dict[Domain, List[str]] = {
    Domain.SYSTEM: [
        "system", "config", "install", "device", "os", "disk", "hardware",
        "process", "service", "reboot", "daemon", "network", "battery",
        "cpu", "memory usage", "kernel", "sandbox", "env",
    ],
    Domain.CODING: [
        "code", "refactor", "bug", "implement", "function", "class", "patch",
        "git", "repo", "test", "python", "script", "program", "build",
        "debug", "compile", "unit test", "develop",
    ],
    Domain.CRM: [
        "crm", "customer", "lead", "contact", "deal", "invoice", "client",
        "sales", "prospect", "appointment", "schedule meeting", "billing",
        "account", "opportunity",
    ],
    Domain.DATA: [
        "data", "database", "sql", "query", "analytics", "table", "csv",
        "json", "metrics", "aggregate", "dataset", "dataframe", "report",
        "export", "transform",
    ],
    Domain.RESEARCH: [
        "research", "search", "lookup", "docs", "documentation", "find",
        "web", "scrape", "information", "article", "paper", "browse",
        "investigate", "explore",
    ],
    Domain.VISION: [
        "vision", "image", "photo", "screenshot", "ocr", "camera",
        "visual", "picture", "detect image", "recognize image", "scan",
    ],
    Domain.SPEECH: [
        "speech", "voice", "audio", "tts", "stt", "speak", "listen",
        "transcribe", "recording", "synthesize", "say", "sound",
    ],
}


DOMAIN_DEFAULT_CAPABILITIES: Dict[Domain, str] = {
    Domain.SYSTEM: "system.info",
    Domain.CODING: "coding.run_agent",
    Domain.CRM: "crm.customer_query",
    Domain.DATA: "data.process",
    Domain.RESEARCH: "research.search",
    Domain.VISION: "vision.ocr",
    Domain.SPEECH: "speech.tts",
}


@dataclass
class SubGoal:
    """A decomposed sub-goal belonging to a specific domain."""
    id: int
    domain: str
    action: str
    capability: str = ""
    context_in_keys: List[str] = field(default_factory=list)
    context_out_keys: List[str] = field(default_factory=list)
    risk: str = "low"
    depends_on: List[int] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "domain": self.domain,
            "action": self.action,
            "capability": self.capability,
            "context_in_keys": list(self.context_in_keys) if isinstance(self.context_in_keys, (list, tuple)) else self.context_in_keys,
            "context_out_keys": list(self.context_out_keys) if isinstance(self.context_out_keys, (list, tuple)) else self.context_out_keys,
            "risk": self.risk,
            "depends_on": list(self.depends_on),
            "metadata": self.metadata,
        }


class DomainRouter:
    """
    Intelligent domain classification, multi-domain splitting,
    and dependency DAG generation for CCOS requests.
    """

    def __init__(self):
        self._registry = get_capability_registry()

    def detect_domain_for_text(self, text: str) -> Optional[Domain]:
        """Score text against domain keywords and return best matching Domain."""
        text_lower = text.lower()
        best_domain: Optional[Domain] = None
        best_score = 0

        for domain, keywords in DOMAIN_KEYWORDS.items():
            score = 0
            for kw in keywords:
                # Word boundary match or exact substring
                if re.search(r'\b' + re.escape(kw) + r'\b', text_lower):
                    score += 2
                elif kw in text_lower:
                    score += 1
            if score > best_score:
                best_score = score
                best_domain = domain

        return best_domain if best_score > 0 else None

    def assess_risk(self, text: str) -> str:
        """Assess risk level from action text."""
        text_lower = text.lower()
        destructive = [
            "rm -rf", "delete all", "drop table", "truncate",
            "format disk", "mkfs", "dd if=", ":(){:|:&};:",
            "chmod 777 /", "chown root", "> /dev/sda",
        ]
        for kw in destructive:
            if kw in text_lower:
                return "critical"

        high_risk = ["delete", "remove", "rm ", "drop ", "destroy", "kill -9"]
        for kw in high_risk:
            if kw in text_lower:
                return "high"

        med_risk = ["modify", "install", "config", "update", "patch", "system", "service", "daemon"]
        for kw in med_risk:
            if kw in text_lower:
                return "medium"

        return "low"

    def _resolve_capability(self, domain: Domain, action_text: str) -> str:
        """Find best matching capability in registry or default."""
        try:
            # For coding domain, prefer coding.run_agent for coding/script generation tasks
            if domain == Domain.CODING and "commit" not in action_text.lower():
                run_agent = self._registry.get("coding.run_agent")
                if run_agent:
                    return run_agent.name

            candidates = self._registry.find_for_task(action_text)
            if candidates:
                for c in candidates:
                    if c.category == domain.value:
                        return c.name
                return candidates[0].name
        except Exception:
            pass
        return DOMAIN_DEFAULT_CAPABILITIES.get(domain, f"{domain.value}.process")

    def classify_request(self, request: str) -> Dict[str, Any]:
        """
        Classify request into single or multi-domain structure.
        Returns:
            {
                "request": str,
                "is_multi_domain": bool,
                "domains": List[str],
                "sub_goals": List[SubGoal],
            }
        """
        req_clean = request.strip()
        if not req_clean:
            return {
                "request": request,
                "is_multi_domain": False,
                "domains": [Domain.SYSTEM.value],
                "sub_goals": [],
            }

        # Step 1: Split into candidate clauses by sequence conjunctions
        delimiters = [
            r"\band then\b",
            r"\bafter that\b",
            r"\bfollowed by\b",
            r"\band also\b",
            r"\b,?\s*then\b",
            r"\b,?\s*next\b",
            r"\b,?\s*finally\b",
            r";",
        ]
        split_pattern = "|".join(delimiters)
        clauses = [c.strip() for c in re.split(split_pattern, req_clean, flags=re.IGNORECASE) if c.strip()]

        # If only 1 clause, check if " and " separates distinct domains
        if len(clauses) <= 1 and " and " in req_clean.lower():
            and_parts = [p.strip() for p in re.split(r"\band\b", req_clean, flags=re.IGNORECASE) if p.strip()]
            domains_in_parts = [self.detect_domain_for_text(p) for p in and_parts]
            # If parts map to different valid domains, use them
            valid_domains = [d for d in domains_in_parts if d is not None]
            if len(valid_domains) > 1 and len(set(valid_domains)) > 1:
                clauses = and_parts

        # Analyze each clause
        sub_goals: List[SubGoal] = []
        domains_found: List[str] = []
        clause_domains: List[Tuple[str, Domain]] = []

        for idx, clause in enumerate(clauses, 1):
            dom = self.detect_domain_for_text(clause)
            if dom is None:
                # Fallback to general domain based on index or default
                dom = Domain.SYSTEM if idx == 1 else (clause_domains[-1][1] if clause_domains else Domain.SYSTEM)
            clause_domains.append((clause, dom))
            if dom.value not in domains_found:
                domains_found.append(dom.value)

        is_multi = len(domains_found) > 1 and len(clause_domains) > 1

        if not is_multi:
            # Single domain request
            primary_domain = clause_domains[0][1] if clause_domains else (self.detect_domain_for_text(req_clean) or Domain.SYSTEM)
            cap = self._resolve_capability(primary_domain, req_clean)
            risk = self.assess_risk(req_clean)
            sg = SubGoal(
                id=1,
                domain=primary_domain.value,
                action=req_clean,
                capability=cap,
                context_in_keys=[],
                context_out_keys=[f"{primary_domain.value}_output"],
                risk=risk,
                depends_on=[],
                metadata={"domain": primary_domain.value},
            )
            return {
                "request": request,
                "is_multi_domain": False,
                "domains": [primary_domain.value],
                "sub_goals": [sg],
            }

        # Multi-domain request: build chained sub-goals with context handoffs
        for idx, (clause, dom) in enumerate(clause_domains, 1):
            cap = self._resolve_capability(dom, clause)
            risk = self.assess_risk(clause)

            in_keys = []
            out_keys = [f"{dom.value}_output_{idx}"]

            depends_on = []
            if idx > 1:
                # Depends on preceding sub-goal output
                prev_sg = sub_goals[-1]
                in_keys.extend(prev_sg.context_out_keys)
                depends_on.append(prev_sg.id)

            sg = SubGoal(
                id=idx,
                domain=dom.value,
                action=clause,
                capability=cap,
                context_in_keys=in_keys,
                context_out_keys=out_keys,
                risk=risk,
                depends_on=depends_on,
                metadata={"domain": dom.value},
            )
            sub_goals.append(sg)

        return {
            "request": request,
            "is_multi_domain": True,
            "domains": domains_found,
            "sub_goals": sub_goals,
        }

    def build_dependency_dag(self, sub_goals: List[SubGoal]) -> List[SubGoal]:
        """
        Order sub-goals topologically according to dependencies
        (explicit `depends_on` + implicit `context_in_keys` matching `context_out_keys`).

        Returns topologically sorted List[SubGoal] with re-indexed IDs.
        Raises ValueError on cycle.
        """
        if not sub_goals:
            return []

        # Map output keys to producing sub-goal IDs
        out_key_to_sg: Dict[str, int] = {}
        sg_by_id: Dict[int, SubGoal] = {}

        for sg in sub_goals:
            sg_by_id[sg.id] = sg
            for out_k in sg.context_out_keys:
                out_key_to_sg[out_k] = sg.id

        # Build adjacency graph and calculate in-degrees
        # Graph: producer -> list of consumers
        adj: Dict[int, List[int]] = {sg.id: [] for sg in sub_goals}
        in_degree: Dict[int, int] = {sg.id: 0 for sg in sub_goals}

        for sg in sub_goals:
            deps: Set[int] = set(sg.depends_on)
            # Add implicit dependencies from context_in_keys
            for in_k in sg.context_in_keys:
                if in_k in out_key_to_sg and out_key_to_sg[in_k] != sg.id:
                    deps.add(out_key_to_sg[in_k])

            # Update sg's explicit depends_on list
            sg.depends_on = sorted(list(deps))

            for dep_id in deps:
                if dep_id in adj:
                    adj[dep_id].append(sg.id)
                    in_degree[sg.id] += 1

        # Kahn's algorithm for topological sorting
        queue = [sg_id for sg_id, deg in in_degree.items() if deg == 0]
        # Sort queue by original ID to maintain stable order
        queue.sort()

        sorted_goals: List[SubGoal] = []
        old_id_to_new_id: Dict[int, int] = {}

        while queue:
            curr_id = queue.pop(0)
            sorted_goals.append(sg_by_id[curr_id])

            for neighbor in adj.get(curr_id, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
                    queue.sort()

        if len(sorted_goals) != len(sub_goals):
            raise ValueError(f"Cycle detected in sub-goal dependency DAG: sorted {len(sorted_goals)} of {len(sub_goals)} sub-goals")

        # Re-index IDs and update depends_on
        reindexed_goals: List[SubGoal] = []
        for new_idx, sg in enumerate(sorted_goals, 1):
            old_id_to_new_id[sg.id] = new_idx

        for new_idx, sg in enumerate(sorted_goals, 1):
            new_deps = [old_id_to_new_id[d] for d in sg.depends_on if d in old_id_to_new_id]
            reindexed_sg = SubGoal(
                id=new_idx,
                domain=sg.domain,
                action=sg.action,
                capability=sg.capability,
                context_in_keys=list(sg.context_in_keys),
                context_out_keys=list(sg.context_out_keys),
                risk=sg.risk,
                depends_on=sorted(new_deps),
                metadata=dict(sg.metadata),
            )
            reindexed_goals.append(reindexed_sg)

        return reindexed_goals

    def split_multi_domain(self, request: str) -> List[SubGoal]:
        """Convenience method: classify request and return topologically sorted sub-goals."""
        res = self.classify_request(request)
        return self.build_dependency_dag(res["sub_goals"])


# Singleton
_domain_router: Optional[DomainRouter] = None


def get_domain_router() -> DomainRouter:
    global _domain_router
    if _domain_router is None:
        _domain_router = DomainRouter()
    return _domain_router
