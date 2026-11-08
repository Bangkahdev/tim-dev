"""Local RAG knowledge base: Ollama embeddings when available, SQLite FTS fallback.

No external vector database is required for the local-first MVP. Documents are chunked,
optionally embedded through Ollama's /api/embed endpoint, and retrieved semantically
when vectors exist. Full-text BM25 remains available without an embedding model.
"""
from __future__ import annotations

import json
import math
import os
import re
import sqlite3
import urllib.request
import urllib.error
import uuid
from datetime import datetime
from pathlib import Path

from core.office_store import DB_PATH, ROSTER

BASE_DIR = Path(__file__).resolve().parents[1]
EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text").strip()
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").strip()


def _now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _should_index_for_agents(rel: str) -> bool:
    """Return False for files that would leak hidden Milestone 1 answers.

    Agent-facing RAG may include the behavior spec and normal source/docs, but
    never the reference implementation, the hidden verifier, or old pilot
    workspaces that still contain the deterministic reference output.
    """
    rel = str(rel or "").replace("\\", "/").lstrip("./")
    if rel in {"core/business_cycle.py", "docs/MILESTONE-1-PLAYBOOK.md"}:
        return False
    if rel.startswith("tools/") or "verify_milestone" in rel:
        return False
    if rel.startswith("tests/"):
        return False
    if rel.startswith("workspace/projects/"):
        parts = rel.split("/")
        # workspace/projects/<project-key>/...
        if len(parts) >= 3 and parts[2].startswith("milestone1"):
            return False
    return True


def _chunks(text: str, size=1100, overlap=140):
    text = str(text or "").strip()
    if not text:
        return []
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    out, current = [], ""
    for paragraph in paragraphs:
        while len(paragraph) > size:
            if current:
                out.append(current)
                current = ""
            out.append(paragraph[:size])
            paragraph = paragraph[size-overlap:]
        if len(current) + len(paragraph) + 2 > size and current:
            out.append(current)
            current = current[-overlap:] + "\n" + paragraph
        else:
            current = (current + "\n\n" + paragraph).strip()
    if current:
        out.append(current)
    return out


class KnowledgeBase:
    def __init__(self, db_path=DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._embedding_unavailable = False
        self._init_db()

    def _connect(self):
        db = sqlite3.connect(self.db_path, timeout=15)
        db.row_factory = sqlite3.Row
        return db

    def _init_db(self):
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS knowledge_documents (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, source TEXT NOT NULL DEFAULT 'manual',
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS knowledge_chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, doc_id TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL, content TEXT NOT NULL, embedding TEXT,
                    FOREIGN KEY(doc_id) REFERENCES knowledge_documents(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_knowledge_doc ON knowledge_chunks(doc_id);
            """)
            try:
                db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(title, content)")
            except sqlite3.OperationalError:
                # LIKE retrieval below is used on SQLite builds without FTS5.
                pass

    def _embed_many(self, texts):
        if not texts:
            return []
        if self._embedding_unavailable:
            return [None] * len(texts)
        payload = json.dumps({"model": EMBED_MODEL, "input": texts}).encode()
        request = urllib.request.Request(
            OLLAMA_URL.rstrip("/") + "/api/embed", data=payload,
            headers={"Content-Type": "application/json"}, method="POST"
        )
        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                data = json.loads(response.read().decode("utf-8"))
            vectors = data.get("embeddings")
            if isinstance(vectors, list) and len(vectors) == len(texts):
                return vectors
            self._embedding_unavailable = True
            return [None] * len(texts)
        except urllib.error.HTTPError as error:
            # Only older Ollama versions need the legacy endpoint. A 400 usually
            # means the embedding model is not installed, so do not retry every query.
            if error.code not in (404, 405):
                self._embedding_unavailable = True
                return [None] * len(texts)
        except Exception:
            self._embedding_unavailable = True
            return [None] * len(texts)

        vectors = []
        for text in texts:
            try:
                body = json.dumps({"model": EMBED_MODEL, "prompt": text}).encode()
                req = urllib.request.Request(
                    OLLAMA_URL.rstrip("/") + "/api/embeddings", data=body,
                    headers={"Content-Type": "application/json"}, method="POST"
                )
                with urllib.request.urlopen(req, timeout=5) as response:
                    vectors.append(json.loads(response.read().decode("utf-8")).get("embedding"))
            except Exception:
                self._embedding_unavailable = True
                return [None] * len(texts)
        return vectors

    def add_document(self, title: str, content: str, source="manual"):
        title = str(title or "").strip()[:200]
        content = str(content or "").strip()
        if not title or not content:
            raise ValueError("Judul dan isi dokumen wajib diisi.")
        if len(content) > 2_000_000:
            raise ValueError("Dokumen terlalu besar (maksimal 2 MB teks).")
        chunks = _chunks(content)
        vectors = self._embed_many(chunks)
        doc_id = str(uuid.uuid4())
        now = _now()
        with self._connect() as db:
            db.execute("INSERT INTO knowledge_documents(id,title,source,created_at,updated_at) VALUES(?,?,?,?,?)",
                       (doc_id, title, str(source)[:300], now, now))
            for idx, chunk in enumerate(chunks):
                vector = vectors[idx] if idx < len(vectors) else None
                cur = db.execute("INSERT INTO knowledge_chunks(doc_id,chunk_index,content,embedding) VALUES(?,?,?,?)",
                                  (doc_id, idx, chunk, json.dumps(vector) if vector else None))
                chunk_id = cur.lastrowid
                try:
                    db.execute("INSERT INTO knowledge_fts(rowid,title,content) VALUES(?,?,?)", (chunk_id, title, chunk))
                except sqlite3.OperationalError:
                    pass
        return {"id": doc_id, "title": title, "source": source, "chunks": len(chunks),
                "embedded": sum(1 for v in vectors if v)}

    def list_documents(self):
        with self._connect() as db:
            rows = db.execute("""SELECT d.id,d.title,d.source,d.created_at,COUNT(c.id) chunks,
                SUM(CASE WHEN c.embedding IS NOT NULL THEN 1 ELSE 0 END) embedded
                FROM knowledge_documents d LEFT JOIN knowledge_chunks c ON c.doc_id=d.id
                GROUP BY d.id ORDER BY d.updated_at DESC""").fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _cosine(a, b):
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(float(x) * float(y) for x, y in zip(a, b))
        na = math.sqrt(sum(float(x) ** 2 for x in a))
        nb = math.sqrt(sum(float(y) ** 2 for y in b))
        return dot / (na * nb) if na and nb else 0.0

    def search(self, query: str, limit=5):
        query = str(query or "").strip()
        if not query:
            return []
        limit = max(1, min(int(limit), 12))
        query_vector = (self._embed_many([query]) or [None])[0]
        with self._connect() as db:
            if query_vector:
                rows = db.execute("""SELECT c.id,c.content,c.embedding,d.title,d.source
                    FROM knowledge_chunks c JOIN knowledge_documents d ON d.id=c.doc_id
                    WHERE c.embedding IS NOT NULL ORDER BY c.id DESC LIMIT 800""").fetchall()
                scored = []
                for row in rows:
                    try:
                        vector = json.loads(row["embedding"])
                        score = self._cosine(query_vector, vector)
                    except (TypeError, ValueError, json.JSONDecodeError):
                        continue
                    if score > 0:
                        scored.append((score, row))
                if scored:
                    scored.sort(key=lambda item: item[0], reverse=True)
                    return [{"title": r["title"], "source": r["source"], "content": r["content"],
                             "score": round(score, 4), "method": "ollama-vector"}
                            for score, r in scored[:limit]]
            tokens = list(dict.fromkeys(t.lower() for t in re.findall(r"[\w-]{3,}", query)))[:12]
            if not tokens:
                return []
            match = " OR ".join('"' + token.replace('"', '') + '"' for token in tokens)
            try:
                rows = db.execute("""SELECT d.title,d.source,c.content,bm25(knowledge_fts) AS rank
                    FROM knowledge_fts JOIN knowledge_chunks c ON c.id=knowledge_fts.rowid
                    JOIN knowledge_documents d ON d.id=c.doc_id
                    WHERE knowledge_fts MATCH ? ORDER BY rank LIMIT ?""", (match, limit)).fetchall()
                return [{"title": r["title"], "source": r["source"], "content": r["content"],
                         "score": round(1 / (1 + abs(float(r["rank"]))), 4), "method": "sqlite-fts"}
                        for r in rows]
            except sqlite3.OperationalError:
                pass
            clauses = " OR ".join(["c.content LIKE ?" for _ in tokens])
            rows = db.execute(f"""SELECT d.title,d.source,c.content FROM knowledge_chunks c
                JOIN knowledge_documents d ON d.id=c.doc_id WHERE {clauses} LIMIT ?""",
                tuple(f"%{t}%" for t in tokens) + (limit,)).fetchall()
        return [{"title": r["title"], "source": r["source"], "content": r["content"],
                 "score": 0.25, "method": "sqlite-like"} for r in rows]

    def _remove_source_versions(self, source_prefix: str):
        """Replace an old indexed revision of one file instead of keeping stale copies."""
        with self._connect() as db:
            rows = db.execute(
                "SELECT id FROM knowledge_documents WHERE source=? OR source LIKE ?",
                (source_prefix, source_prefix + ":%"),
            ).fetchall()
            for row in rows:
                chunk_ids = [r[0] for r in db.execute(
                    "SELECT id FROM knowledge_chunks WHERE doc_id=?", (row["id"],)
                ).fetchall()]
                if chunk_ids:
                    placeholders = ",".join("?" for _ in chunk_ids)
                    try:
                        db.execute(f"DELETE FROM knowledge_fts WHERE rowid IN ({placeholders})", chunk_ids)
                    except sqlite3.OperationalError:
                        pass
                db.execute("DELETE FROM knowledge_documents WHERE id=?", (row["id"],))

    def ensure_seed_documents(self):
        """Index office docs and relevant source files for grounded answers and agents."""
        sources = {item["source"] for item in self.list_documents()}
        pending = []

        roster_source = "system:roster"
        roster = "\n".join(
            f"{name} ({employee_id}) — {role}; ruangan awal: {room}."
            for employee_id, (name, role, room) in ROSTER.items()
        )
        if roster_source in sources:
            existing = next((item for item in self.list_documents() if item["source"] == roster_source), None)
            if existing:
                self._remove_source_versions(roster_source)
                pending.append(("Bangkah Office — Struktur Tim", roster, roster_source))
        else:
            pending.append(("Bangkah Office — Struktur Tim", roster, roster_source))

        # Root-level entry points matter: agents should retrieve the real application design,
        # not only a README summary.
        root_files = [BASE_DIR / name for name in (
            "README.md", "main.py", "office_server.py", "config.py", ".env.example"
        )]
        # NOTE: `tests/` is intentionally NOT indexed here. It can contain verifier
        # fixtures/mutants and reference answers (e.g. Milestone 1). `tools/` and
        # verifier scripts live outside these roots. Keep agent-facing RAG free of
        # hidden-test inputs and reference implementations.
        roots = [
            BASE_DIR / "core", BASE_DIR / "web",
            BASE_DIR / "reports", BASE_DIR / "workspace" / "projects", BASE_DIR / "docs",
        ]
        allowed_suffixes = {
            ".md", ".txt", ".rst", ".yaml", ".yml", ".py", ".js", ".html",
            ".css", ".json", ".toml", ".ini",
        }
        candidates = [(path, path.name) for path in root_files if path.is_file()]
        skip_dirs = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", "data", "build", "dist", "tools"}
        for root in roots:
            if not root.exists():
                continue
            for path in root.rglob("*"):
                if not path.is_file() or path.suffix.lower() not in allowed_suffixes:
                    continue
                rel = path.relative_to(BASE_DIR).as_posix()
                if any(part in skip_dirs or part.startswith(".") for part in path.relative_to(BASE_DIR).parts):
                    continue
                if not _should_index_for_agents(rel):
                    self._remove_source_versions(f"file:{rel}")
                    continue
                candidates.append((path, rel))

        seen = set()
        for path, label in candidates:
            try:
                relative = path.relative_to(BASE_DIR).as_posix()
                if relative in seen:
                    continue
                seen.add(relative)
                stat = path.stat()
                if stat.st_size > 250_000:
                    continue
                content = path.read_text(encoding="utf-8", errors="replace")
                if not content.strip():
                    continue
                base_source = f"file:{relative}"
                source = f"{base_source}:{stat.st_mtime_ns}"
                if source in sources:
                    continue
                self._remove_source_versions(base_source)
                title = label.replace("_", " ").replace("-", " ").rsplit(".", 1)[0].title()
                pending.append((title, content, source))
            except (OSError, ValueError):
                continue

        # Indexing each document separately repeats model startup/HTTP overhead. Keep the
        # existing single-document interface for uploads, but make the initial scan bounded.
        for title, content, source in pending:
            self.add_document(title, content, source)


KNOWLEDGE = KnowledgeBase()
