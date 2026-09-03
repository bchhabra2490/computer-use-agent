"""Evidence-backed temporal knowledge graph for durable agent memory.

SQLite is the authoritative store.  Graphify and other visualizers should
consume exports from this database rather than becoming runtime dependencies.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from collections import deque
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


DEFAULT_MEMORY_DIR = Path(__file__).resolve().parent / "memory"
ENTITY_TYPES = frozenset(
    {
        "person", "project", "organization", "application", "document",
        "repository", "website", "concept", "task", "decision", "workflow",
    }
)
PREDICATES = frozenset(
    {
        "WORKS_ON", "USES", "OPENED", "CREATED", "EDITED", "DISCUSSED",
        "DECIDED", "PREFERS", "DEPENDS_ON", "RELATED_TO", "ASSIGNED_TO",
        "BLOCKED_BY", "PART_OF", "PERFORMED_STEP", "FOLLOWED_BY",
        "INSPIRED_BY",
    }
)
EPISTEMIC_STATUSES = frozenset({"observed", "extracted", "inferred", "user_confirmed"})
_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{0,31}:[a-z0-9][a-z0-9._-]{0,127}$")
_SECRET_RE = re.compile(
    r"(?i)\b(password|passwd|api[_-]?key|secret|otp|one[- ]time(?: code)?)\b\s*[:=]"
    r"|sk-[A-Za-z0-9]{10,}|ghp_[A-Za-z0-9]{10,}|github_pat_[A-Za-z0-9_]{10,}"
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _root(memory_dir: Path | None) -> Path:
    return Path(memory_dir) if memory_dir is not None else DEFAULT_MEMORY_DIR


def database_path(memory_dir: Path | None = None) -> Path:
    return _root(memory_dir) / "graph" / "memory.sqlite3"


@contextmanager
def _connect(memory_dir: Path | None = None):
    path = database_path(memory_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10)
    try:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        db.executescript(
            """
        CREATE TABLE IF NOT EXISTS observations (
            id TEXT PRIMARY KEY,
            started_at TEXT,
            ended_at TEXT,
            source TEXT NOT NULL DEFAULT 'macos',
            app TEXT,
            title TEXT,
            url TEXT,
            sensitivity TEXT NOT NULL DEFAULT 'normal',
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS entities (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            label TEXT NOT NULL,
            sensitivity TEXT NOT NULL DEFAULT 'normal',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS claims (
            id TEXT PRIMARY KEY,
            subject_id TEXT NOT NULL REFERENCES entities(id),
            predicate TEXT NOT NULL,
            object_id TEXT NOT NULL REFERENCES entities(id),
            status TEXT NOT NULL DEFAULT 'accepted',
            epistemic_status TEXT NOT NULL,
            confidence REAL NOT NULL,
            valid_from TEXT,
            valid_to TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(subject_id, predicate, object_id)
        );
        CREATE TABLE IF NOT EXISTS claim_evidence (
            claim_id TEXT NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
            observation_id TEXT NOT NULL REFERENCES observations(id) ON DELETE CASCADE,
            support REAL NOT NULL DEFAULT 1.0,
            excerpt TEXT,
            PRIMARY KEY (claim_id, observation_id)
        );
        CREATE TABLE IF NOT EXISTS graph_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_claims_subject ON claims(subject_id, status);
        CREATE INDEX IF NOT EXISTS idx_claims_object ON claims(object_id, status);
        CREATE INDEX IF NOT EXISTS idx_entities_label ON entities(label);
            """
        )
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _clean_entity(row: Any) -> dict[str, str] | None:
    if not isinstance(row, dict):
        return None
    entity_id = str(row.get("id") or "").strip().lower()
    kind = str(row.get("type") or "").strip().lower()
    label = " ".join(str(row.get("label") or "").split()).strip()
    sensitivity = str(row.get("sensitivity") or "normal").strip().lower()
    if not _ID_RE.fullmatch(entity_id) or kind not in ENTITY_TYPES or not label:
        return None
    if not entity_id.startswith(f"{kind}:") or _SECRET_RE.search(label):
        return None
    if sensitivity not in {"normal", "personal", "work", "sensitive"}:
        sensitivity = "normal"
    return {"id": entity_id, "type": kind, "label": label[:240], "sensitivity": sensitivity}


def normalize_graph_changes(payload: Any) -> dict[str, list[dict[str, Any]]]:
    """Validate untrusted extractor output against the deliberately small ontology."""
    graph = payload.get("graph_changes") if isinstance(payload, dict) else None
    if not isinstance(graph, dict):
        graph = payload if isinstance(payload, dict) else {}
    entities = [item for row in (graph.get("entities") or graph.get("nodes") or []) if (item := _clean_entity(row))]
    entity_ids = {row["id"] for row in entities}
    claims: list[dict[str, Any]] = []
    for row in graph.get("claims") or graph.get("edges") or []:
        if not isinstance(row, dict):
            continue
        subject = str(row.get("subject_id") or row.get("subject") or "").strip().lower()
        object_id = str(row.get("object_id") or row.get("object") or "").strip().lower()
        predicate = str(row.get("predicate") or row.get("relation") or "").strip().upper()
        epistemic = str(row.get("epistemic_status") or "inferred").strip().lower()
        try:
            confidence = max(0.0, min(float(row.get("confidence", 0.5)), 1.0))
        except (TypeError, ValueError):
            continue
        if subject not in entity_ids or object_id not in entity_ids or predicate not in PREDICATES:
            continue
        if epistemic not in EPISTEMIC_STATUSES:
            epistemic = "inferred"
        excerpt = " ".join(str(row.get("evidence") or row.get("excerpt") or "").split())[:500]
        if _SECRET_RE.search(excerpt):
            excerpt = ""
        claims.append(
            {
                "subject_id": subject,
                "predicate": predicate,
                "object_id": object_id,
                "epistemic_status": epistemic,
                "confidence": confidence,
                "valid_from": str(row.get("valid_from") or "").strip() or None,
                "valid_to": str(row.get("valid_to") or "").strip() or None,
                "evidence": excerpt,
            }
        )
    return {"entities": entities, "claims": claims}


def _claim_id(subject: str, predicate: str, object_id: str) -> str:
    raw = f"{subject}\0{predicate}\0{object_id}".encode("utf-8")
    return "claim_" + hashlib.sha256(raw).hexdigest()[:24]


def apply_observation_graph(
    observation_id: str,
    observation: dict[str, Any],
    graph_changes: dict[str, Any] | None = None,
    *,
    memory_dir: Path | None = None,
) -> dict[str, int]:
    """Atomically journal an observation and auto-accept its validated graph claims."""
    changes = normalize_graph_changes(graph_changes or {})
    focus = observation.get("focus") or {}
    segments = observation.get("segments") or []
    started = next((str(s.get("events", [{}])[0].get("t") or "") for s in segments if s.get("events")), "")
    ended = next((str(s.get("events", [{}])[-1].get("t") or "") for s in reversed(segments) if s.get("events")), "")
    now = _now()
    with _connect(memory_dir) as db:
        db.execute(
            """INSERT OR IGNORE INTO observations
               (id, started_at, ended_at, source, app, title, url, sensitivity, payload_json, created_at)
               VALUES (?, ?, ?, 'macos', ?, ?, ?, 'normal', ?, ?)""",
            (observation_id, started or None, ended or None, str(focus.get("app") or ""),
             str(focus.get("title") or ""), str(focus.get("url") or ""),
             json.dumps(observation, ensure_ascii=False, separators=(",", ":")), now),
        )
        for entity in changes["entities"]:
            db.execute(
                """INSERT INTO entities (id, type, label, sensitivity, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET label=excluded.label,
                   sensitivity=excluded.sensitivity, updated_at=excluded.updated_at""",
                (entity["id"], entity["type"], entity["label"], entity["sensitivity"], now, now),
            )
        for claim in changes["claims"]:
            cid = _claim_id(claim["subject_id"], claim["predicate"], claim["object_id"])
            db.execute(
                """INSERT INTO claims
                   (id, subject_id, predicate, object_id, status, epistemic_status,
                    confidence, valid_from, valid_to, created_at, updated_at)
                   VALUES (?, ?, ?, ?, 'accepted', ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(subject_id, predicate, object_id) DO UPDATE SET
                   status='accepted', epistemic_status=excluded.epistemic_status,
                   confidence=MAX(claims.confidence, excluded.confidence),
                   valid_to=excluded.valid_to, updated_at=excluded.updated_at""",
                (cid, claim["subject_id"], claim["predicate"], claim["object_id"],
                 claim["epistemic_status"], claim["confidence"], claim["valid_from"] or started or None,
                 claim["valid_to"], now, now),
            )
            db.execute(
                """INSERT OR REPLACE INTO claim_evidence
                   (claim_id, observation_id, support, excerpt) VALUES (?, ?, ?, ?)""",
                (cid, observation_id, claim["confidence"], claim["evidence"]),
            )
    maybe_compact_graph(memory_dir=memory_dir)
    export_graphify(memory_dir=memory_dir)
    return {"observations": 1, "entities": len(changes["entities"]), "claims": len(changes["claims"])}


def compact_graph(
    *,
    memory_dir: Path | None = None,
    raw_retention_days: int | None = None,
    evidence_per_claim: int | None = None,
    orphan_retention_days: int | None = None,
    now: datetime | None = None,
) -> dict[str, int]:
    """Compact raw evidence while preserving accepted claims and their provenance.

    Old observation payloads become small metadata summaries. Repeated evidence
    for the same claim is capped, then old observations no longer referenced by
    any claim are removed. Accepted entities and claims are never age-deleted.
    """
    raw_days = max(1, raw_retention_days if raw_retention_days is not None else int(os.environ.get("MEMORY_GRAPH_RAW_DAYS", "30")))
    evidence_limit = max(1, evidence_per_claim if evidence_per_claim is not None else int(os.environ.get("MEMORY_GRAPH_EVIDENCE_PER_CLAIM", "20")))
    orphan_days = max(1, orphan_retention_days if orphan_retention_days is not None else int(os.environ.get("MEMORY_GRAPH_ORPHAN_DAYS", "7")))
    clock = now or datetime.now(timezone.utc)
    raw_cutoff = (clock - timedelta(days=raw_days)).isoformat()
    orphan_cutoff = (clock - timedelta(days=orphan_days)).isoformat()
    stats = {"payloads_compacted": 0, "evidence_pruned": 0, "observations_deleted": 0}
    with _connect(memory_dir) as db:
        old_rows = db.execute(
            "SELECT id, app, title, url, payload_json FROM observations WHERE created_at < ?",
            (raw_cutoff,),
        ).fetchall()
        for row in old_rows:
            try:
                payload = json.loads(row["payload_json"])
            except (TypeError, json.JSONDecodeError):
                payload = {}
            if isinstance(payload, dict) and payload.get("compacted") is True:
                continue
            segments = payload.get("segments") if isinstance(payload, dict) else []
            events = payload.get("events") if isinstance(payload, dict) else []
            if not events and isinstance(segments, list):
                events = [event for segment in segments if isinstance(segment, dict) for event in (segment.get("events") or [])]
            summary = {
                "compacted": True,
                "focus": {"app": row["app"] or "", "title": row["title"] or "", "url": row["url"] or ""},
                "n_segments": len(segments) if isinstance(segments, list) else 0,
                "n_events": len(events) if isinstance(events, list) else 0,
                "event_kinds": sorted({str(event.get("kind") or "") for event in events if isinstance(event, dict) and event.get("kind")}),
            }
            db.execute(
                "UPDATE observations SET payload_json=? WHERE id=?",
                (json.dumps(summary, ensure_ascii=False, separators=(",", ":")), row["id"]),
            )
            stats["payloads_compacted"] += 1

        doomed = db.execute(
            """SELECT rowid FROM (
                   SELECT ce.rowid,
                          ROW_NUMBER() OVER (
                              PARTITION BY ce.claim_id
                              ORDER BY o.created_at DESC, ce.observation_id DESC
                          ) AS rank
                   FROM claim_evidence ce
                   JOIN observations o ON o.id=ce.observation_id
               ) WHERE rank > ?""",
            (evidence_limit,),
        ).fetchall()
        if doomed:
            db.executemany("DELETE FROM claim_evidence WHERE rowid=?", [(row[0],) for row in doomed])
            stats["evidence_pruned"] = len(doomed)

        cursor = db.execute(
            """DELETE FROM observations
               WHERE created_at < ?
                 AND NOT EXISTS (
                     SELECT 1 FROM claim_evidence ce WHERE ce.observation_id=observations.id
                 )""",
            (orphan_cutoff,),
        )
        stats["observations_deleted"] = max(0, cursor.rowcount)
        db.execute(
            "INSERT OR REPLACE INTO graph_meta(key, value) VALUES ('last_compacted_at', ?)",
            (clock.isoformat(),),
        )
    return stats


def maybe_compact_graph(*, memory_dir: Path | None = None) -> dict[str, int] | None:
    """Run graph compaction every configured number of observation writes."""
    interval = max(1, int(os.environ.get("MEMORY_GRAPH_COMPACT_EVERY", "100")))
    with _connect(memory_dir) as db:
        row = db.execute("SELECT value FROM graph_meta WHERE key='writes_since_compact'").fetchone()
        writes = int(row[0]) + 1 if row else 1
        db.execute(
            "INSERT OR REPLACE INTO graph_meta(key, value) VALUES ('writes_since_compact', ?)",
            (str(writes),),
        )
    if writes < interval:
        return None
    result = compact_graph(memory_dir=memory_dir)
    with _connect(memory_dir) as db:
        db.execute(
            "INSERT OR REPLACE INTO graph_meta(key, value) VALUES ('writes_since_compact', '0')"
        )
    return result


def export_graphify(*, memory_dir: Path | None = None, output_path: Path | None = None) -> Path:
    """Write a rebuildable Graphify-compatible projection of accepted memory."""
    target = Path(output_path) if output_path is not None else _root(memory_dir) / "graph" / "graphify-out" / "graph.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    with _connect(memory_dir) as db:
        nodes = [
            {
                "id": row["id"],
                "label": row["label"],
                "type": row["type"],
                "file_type": "memory",
                "sensitivity": row["sensitivity"],
                "_origin": "memory",
                "norm_label": row["label"].lower(),
            }
            for row in db.execute(
                """SELECT DISTINCT e.id, e.label, e.type, e.sensitivity FROM entities e
                   JOIN claims c ON (c.subject_id=e.id OR c.object_id=e.id)
                   WHERE c.status='accepted' ORDER BY e.id"""
            )
        ]
        links = [
            {
                "source": row["subject_id"],
                "target": row["object_id"],
                "relation": row["predicate"].lower(),
                "confidence": row["epistemic_status"].upper(),
                "confidence_score": row["confidence"],
                "claim_id": row["id"],
                "valid_from": row["valid_from"],
                "valid_to": row["valid_to"],
                "_origin": "memory",
                "weight": 1.0,
            }
            for row in db.execute(
                """SELECT id, subject_id, predicate, object_id, epistemic_status,
                          confidence, valid_from, valid_to FROM claims
                   WHERE status='accepted' ORDER BY id"""
            )
        ]
    payload = {
        "directed": True,
        "multigraph": False,
        "graph": {"kind": "personal-memory", "generated_at": _now()},
        "nodes": nodes,
        "links": links,
        "hyperedges": [],
    }
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(target)
    return target


def search_graph(query: str, *, limit: int = 10, memory_dir: Path | None = None) -> list[dict[str, Any]]:
    terms = [term.lower() for term in re.findall(r"[a-z0-9._-]+", query or "") if len(term) > 1]
    if not terms:
        return []
    with _connect(memory_dir) as db:
        rows = db.execute(
            """SELECT c.id, c.predicate, c.epistemic_status, c.confidence,
                      s.id subject_id, s.label subject_label,
                      o.id object_id, o.label object_label
               FROM claims c JOIN entities s ON s.id=c.subject_id
               JOIN entities o ON o.id=c.object_id WHERE c.status='accepted'"""
        ).fetchall()
    scored = []
    for row in rows:
        item = dict(row)
        haystack = " ".join(str(v).lower() for v in item.values())
        score = sum(1 for term in terms if term in haystack)
        if score:
            item["score"] = score
            scored.append(item)
    scored.sort(key=lambda row: (-row["score"], -row["confidence"], row["id"]))
    return scored[: max(1, min(limit, 50))]


def format_graph_memories(query: str, *, limit: int = 5, memory_dir: Path | None = None) -> str:
    hits = search_graph(query, limit=limit, memory_dir=memory_dir)
    if not hits:
        return ""
    lines = ["Relevant accepted memory-graph relationships:"]
    for hit in hits:
        lines.append(
            f"  - {hit['subject_label']} --{hit['predicate']}--> {hit['object_label']} "
            f"({hit['epistemic_status']}, confidence {hit['confidence']:.2f}, claim {hit['id']})"
        )
    return "\n".join(lines)


def find_path(source: str, target: str, *, max_hops: int = 5, memory_dir: Path | None = None) -> list[dict[str, Any]]:
    """Return a shortest accepted directed path between entity IDs."""
    with _connect(memory_dir) as db:
        rows = [dict(r) for r in db.execute(
            "SELECT id, subject_id, predicate, object_id, confidence FROM claims WHERE status='accepted'"
        )]
    adjacent: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        adjacent.setdefault(row["subject_id"], []).append(row)
    queue = deque([(source, [])])
    seen = {source}
    while queue:
        node, path = queue.popleft()
        if len(path) >= max_hops:
            continue
        for edge in adjacent.get(node, []):
            next_path = path + [edge]
            if edge["object_id"] == target:
                return next_path
            if edge["object_id"] not in seen:
                seen.add(edge["object_id"])
                queue.append((edge["object_id"], next_path))
    return []
