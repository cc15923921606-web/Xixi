from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator


_FOLLOW_UP_RE = re.compile(
    r"(?:提醒我|别忘了|记得提醒|之后(?:再|帮我)|下次(?:再|继续)|到时候|"
    r"帮我(?:持续)?关注|过(?:一会|几天|段时间)|明天|后天|下周|以后再)"
)
_QUESTION_ONLY_RE = re.compile(r"^(?:你会|能不能|可不可以|怎么|如何|为什么|是否).*[？?]?$", re.I)
_RISK_BY_CAPABILITY = {
    "chat": "read_only",
    "research": "network",
    "memory": "local_write",
    "qq_relay": "external_write",
    "game_control": "device_control",
    "autonomy": "external_write",
}
_DEFAULT_RULES = {
    "chat": "auto",
    "research": "auto",
    "memory": "auto",
    "qq_relay": "owner_only",
    "game_control": "manual_only",
    "autonomy": "auto",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _row(row: sqlite3.Row | None) -> dict[str, Any]:
    return dict(row) if row is not None else {}


class AgentWorkspace:
    """Persistent execution, growth and policy state shared by app and QQ chat."""

    SCHEMA_VERSION = 1

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._write_lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        with self._write_lock:
            connection = self._connect()
            try:
                yield connection
                connection.commit()
            finally:
                connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS workspace_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS workspace_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS agent_goals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'active',
                    source TEXT NOT NULL DEFAULT 'manual',
                    session_id TEXT NOT NULL DEFAULT '',
                    due_at TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS agent_runs (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    user_id TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL DEFAULT 'chat',
                    request_text TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'running',
                    risk_level TEXT NOT NULL DEFAULT 'read_only',
                    model_name TEXT NOT NULL DEFAULT '',
                    reply_excerpt TEXT NOT NULL DEFAULT '',
                    error TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    finished_at TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_agent_runs_created
                    ON agent_runs(created_at DESC);
                CREATE TABLE IF NOT EXISTS agent_steps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    step_index INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    instruction TEXT NOT NULL,
                    kind TEXT NOT NULL DEFAULT 'content',
                    side_effect TEXT NOT NULL DEFAULT 'none',
                    capability TEXT NOT NULL DEFAULT 'chat',
                    risk_level TEXT NOT NULL DEFAULT 'read_only',
                    status TEXT NOT NULL DEFAULT 'pending',
                    result TEXT NOT NULL DEFAULT '',
                    depends_on_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(run_id, step_index),
                    FOREIGN KEY(run_id) REFERENCES agent_runs(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS tool_receipts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL DEFAULT '',
                    step_id INTEGER NOT NULL DEFAULT 0,
                    capability TEXT NOT NULL,
                    risk_level TEXT NOT NULL DEFAULT 'read_only',
                    status TEXT NOT NULL,
                    request_json TEXT NOT NULL DEFAULT '{}',
                    result TEXT NOT NULL DEFAULT '',
                    error TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    finished_at TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS autonomy_policy (
                    id INTEGER PRIMARY KEY CHECK(id = 1),
                    paused INTEGER NOT NULL DEFAULT 0,
                    quiet_start_hour INTEGER NOT NULL DEFAULT 23,
                    quiet_end_hour INTEGER NOT NULL DEFAULT 8,
                    daily_action_limit INTEGER NOT NULL DEFAULT 12,
                    daily_budget_yuan REAL NOT NULL DEFAULT 2.0,
                    capability_rules_json TEXT NOT NULL DEFAULT '{}',
                    privacy_snapshot_json TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS pending_threads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    user_id TEXT NOT NULL DEFAULT '',
                    content TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open',
                    follow_up_at TEXT NOT NULL DEFAULT '',
                    source_run_id TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_pending_threads_status
                    ON pending_threads(status, updated_at DESC);
                CREATE TABLE IF NOT EXISTS conversation_summaries (
                    session_id TEXT PRIMARY KEY,
                    summary TEXT NOT NULL,
                    compacted_messages INTEGER NOT NULL DEFAULT 0,
                    source_hash TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS growth_reflections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    period_type TEXT NOT NULL,
                    period_key TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    mood TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL DEFAULT 'xixi',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(period_type, period_key)
                );
                CREATE TABLE IF NOT EXISTS model_usage_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    capability TEXT NOT NULL,
                    provider TEXT NOT NULL DEFAULT '',
                    model_name TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    latency_ms INTEGER NOT NULL DEFAULT 0,
                    estimated_input_tokens INTEGER NOT NULL DEFAULT 0,
                    estimated_output_tokens INTEGER NOT NULL DEFAULT 0,
                    estimated_cost_yuan REAL NOT NULL DEFAULT 0,
                    error TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_model_usage_created
                    ON model_usage_events(created_at DESC);
                CREATE TABLE IF NOT EXISTS model_profiles (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    capability TEXT NOT NULL DEFAULT 'language',
                    base_url TEXT NOT NULL,
                    model_name TEXT NOT NULL,
                    api_type TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    priority INTEGER NOT NULL DEFAULT 100,
                    use_primary_key INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS model_providers (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    base_url TEXT NOT NULL,
                    api_type TEXT NOT NULL DEFAULT 'auto',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS model_provider_models (
                    id TEXT PRIMARY KEY,
                    provider_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    model_name TEXT NOT NULL,
                    capabilities TEXT NOT NULL DEFAULT 'language',
                    cache_price REAL NOT NULL DEFAULT 0,
                    input_price REAL NOT NULL DEFAULT 0,
                    output_price REAL NOT NULL DEFAULT 0,
                    currency TEXT NOT NULL DEFAULT 'CNY',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(provider_id, model_name),
                    FOREIGN KEY(provider_id) REFERENCES model_providers(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_model_provider_models_provider
                    ON model_provider_models(provider_id, created_at);
                """
            )
            provider_model_columns = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(model_provider_models)").fetchall()
            }
            if "cache_price" not in provider_model_columns:
                connection.execute(
                    "ALTER TABLE model_provider_models ADD COLUMN cache_price REAL NOT NULL DEFAULT 0"
                )
            connection.execute(
                "INSERT OR IGNORE INTO workspace_migrations(version, applied_at) VALUES (?, ?)",
                (self.SCHEMA_VERSION, _now()),
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO autonomy_policy(
                    id, capability_rules_json, updated_at
                ) VALUES (1, ?, ?)
                """,
                (json.dumps(_DEFAULT_RULES, ensure_ascii=False), _now()),
            )

    def migration_status(self) -> dict[str, Any]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT version, applied_at FROM workspace_migrations ORDER BY version"
            ).fetchall()
        current = max((int(item["version"]) for item in rows), default=0)
        return {
            "current_version": current,
            "target_version": self.SCHEMA_VERSION,
            "up_to_date": current == self.SCHEMA_VERSION,
            "applied": [dict(item) for item in rows],
        }

    def get_state(self, key: str, default: str = "") -> str:
        """Read a small piece of persistent application state."""
        with self._connection() as connection:
            row = connection.execute(
                "SELECT value FROM workspace_state WHERE key=?", (str(key),)
            ).fetchone()
        return str(row["value"]) if row is not None else default

    def set_state(self, key: str, value: str) -> None:
        """Persist a small piece of application state without creating a new file."""
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO workspace_state(key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value=excluded.value, updated_at=excluded.updated_at
                """,
                (str(key), str(value), _now()),
            )

    def model_provider_seed_completed(self) -> bool:
        return self.get_state("model_provider_seed_completed") == "1"

    def mark_model_provider_seed_completed(self) -> None:
        self.set_state("model_provider_seed_completed", "1")

    @staticmethod
    def _capability_for_step(step: Any) -> str:
        if getattr(step, "side_effect", "") == "group_message":
            return "qq_relay"
        if str(getattr(step, "side_effect", "")).startswith("memory_"):
            return "memory"
        if getattr(step, "action", "") == "research":
            return "research"
        return "chat"

    def begin_turn(
        self,
        *,
        session_id: str,
        user_id: str,
        source: str,
        request_text: str,
        frame: Any,
        model_name: str,
    ) -> str:
        steps = tuple(getattr(frame, "task_plan", ()) or ())
        meaningful = (
            len(steps) > 1
            or getattr(frame, "side_effect", "none") != "none"
            or getattr(frame, "action", "chat") not in {"chat", "answer"}
        )
        self.capture_pending_thread(
            session_id=session_id,
            user_id=user_id,
            content=request_text,
        )
        now = _now()
        with self._connection() as connection:
            # Brain calls are serialized. Any older running row here belongs to a
            # turn that exited before it could report a final state.
            connection.execute(
                """
                UPDATE agent_steps
                SET status='failed', result='上一轮执行意外中断', updated_at=?
                WHERE status='running'
                """,
                (now,),
            )
            connection.execute(
                """
                UPDATE agent_runs
                SET status='failed', error='上一轮执行意外中断',
                    updated_at=?, finished_at=?
                WHERE status='running'
                """,
                (now, now),
            )
        if not meaningful:
            return ""
        run_id = uuid.uuid4().hex
        capabilities = [self._capability_for_step(step) for step in steps]
        risk = max(
            (_RISK_BY_CAPABILITY.get(item, "read_only") for item in capabilities),
            key=lambda item: ["read_only", "network", "local_write", "external_write", "device_control"].index(item),
            default="read_only",
        )
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO agent_runs(
                    id, session_id, user_id, source, request_text, risk_level,
                    model_name, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (run_id, session_id, user_id, source, request_text[:4000], risk, model_name, now, now),
            )
            for index, step in enumerate(steps or (), start=1):
                capability = self._capability_for_step(step)
                connection.execute(
                    """
                    INSERT INTO agent_steps(
                        run_id, step_index, action, instruction, kind, side_effect,
                        capability, risk_level, status, depends_on_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'running', ?, ?, ?)
                    """,
                    (
                        run_id,
                        int(getattr(step, "id", index)),
                        str(getattr(step, "action", "respond")),
                        str(getattr(step, "instruction", request_text))[:2000],
                        str(getattr(step, "kind", "content")),
                        str(getattr(step, "side_effect", "none")),
                        capability,
                        _RISK_BY_CAPABILITY.get(capability, "read_only"),
                        json.dumps(list(getattr(step, "depends_on", ()) or ())),
                        now,
                        now,
                    ),
                )
        return run_id

    def finish_turn(self, run_id: str, reply: str, *, partial: bool = False) -> None:
        if not run_id:
            return
        now = _now()
        status = "partial" if partial else "completed"
        with self._connection() as connection:
            connection.execute(
                "UPDATE agent_steps SET status=?, result=?, updated_at=? WHERE run_id=? AND status='running'",
                (status, reply[:1000], now, run_id),
            )
            connection.execute(
                """
                UPDATE agent_runs SET status=?, reply_excerpt=?, updated_at=?, finished_at=?
                WHERE id=?
                """,
                (status, reply[:1000], now, now, run_id),
            )

    def fail_turn(self, run_id: str, error: str) -> None:
        if not run_id:
            return
        now = _now()
        with self._connection() as connection:
            connection.execute(
                "UPDATE agent_steps SET status='failed', result=?, updated_at=? WHERE run_id=? AND status='running'",
                (error[:1000], now, run_id),
            )
            connection.execute(
                "UPDATE agent_runs SET status='failed', error=?, updated_at=?, finished_at=? WHERE id=?",
                (error[:1000], now, now, run_id),
            )

    def record_tool(
        self,
        *,
        capability: str,
        status: str,
        risk_level: str = "read_only",
        run_id: str = "",
        request: dict[str, Any] | None = None,
        result: str = "",
        error: str = "",
    ) -> int:
        now = _now()
        with self._connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO tool_receipts(
                    run_id, capability, risk_level, status, request_json,
                    result, error, created_at, finished_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    capability,
                    risk_level,
                    status,
                    json.dumps(request or {}, ensure_ascii=False)[:8000],
                    result[:2000],
                    error[:1000],
                    now,
                    now,
                ),
            )
            return int(cursor.lastrowid)

    def runs(self, limit: int = 80) -> dict[str, Any]:
        limit = max(1, min(300, int(limit)))
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM agent_runs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
            items = []
            for row in rows:
                item = dict(row)
                steps = connection.execute(
                    "SELECT * FROM agent_steps WHERE run_id=? ORDER BY step_index", (row["id"],)
                ).fetchall()
                item["steps"] = [dict(step) for step in steps]
                items.append(item)
        return {"items": items}

    def create_goal(self, title: str, description: str = "", session_id: str = "") -> dict[str, Any]:
        title = re.sub(r"\s+", " ", title).strip()
        if not title or len(title) > 200:
            raise ValueError("目标名称应为 1 至 200 个字符")
        now = _now()
        with self._connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO agent_goals(title, description, session_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (title, description.strip()[:2000], session_id[:160], now, now),
            )
            row = connection.execute("SELECT * FROM agent_goals WHERE id=?", (cursor.lastrowid,)).fetchone()
        return _row(row)

    def goals(self) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM agent_goals ORDER BY status='active' DESC, updated_at DESC"
            ).fetchall()
        return [dict(item) for item in rows]

    def update_goal(self, goal_id: int, status: str) -> dict[str, Any]:
        if status not in {"active", "completed", "cancelled"}:
            raise ValueError("目标状态无效")
        with self._connection() as connection:
            connection.execute(
                "UPDATE agent_goals SET status=?, updated_at=? WHERE id=?",
                (status, _now(), int(goal_id)),
            )
            row = connection.execute("SELECT * FROM agent_goals WHERE id=?", (int(goal_id),)).fetchone()
        if row is None:
            raise ValueError("找不到这个目标")
        return _row(row)

    def capture_pending_thread(self, *, session_id: str, user_id: str, content: str) -> int:
        cleaned = re.sub(r"\s+", " ", content).strip()[:500]
        if not cleaned or not _FOLLOW_UP_RE.search(cleaned) or _QUESTION_ONLY_RE.fullmatch(cleaned):
            return 0
        with self._connection() as connection:
            existing = connection.execute(
                """
                SELECT id FROM pending_threads
                WHERE status='open' AND session_id=? AND content=? LIMIT 1
                """,
                (session_id, cleaned),
            ).fetchone()
            if existing:
                return int(existing["id"])
            now = _now()
            cursor = connection.execute(
                """
                INSERT INTO pending_threads(session_id, user_id, content, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, user_id, cleaned, now, now),
            )
            return int(cursor.lastrowid)

    def pending_threads(self, status: str = "open", limit: int = 80) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM pending_threads WHERE status=? ORDER BY updated_at DESC LIMIT ?",
                (status, max(1, min(300, int(limit)))),
            ).fetchall()
        return [dict(item) for item in rows]

    def update_thread(self, thread_id: int, status: str) -> dict[str, Any]:
        if status not in {"open", "completed", "cancelled"}:
            raise ValueError("跟进状态无效")
        with self._connection() as connection:
            connection.execute(
                "UPDATE pending_threads SET status=?, updated_at=? WHERE id=?",
                (status, _now(), int(thread_id)),
            )
            row = connection.execute("SELECT * FROM pending_threads WHERE id=?", (int(thread_id),)).fetchone()
        if row is None:
            raise ValueError("找不到这条待跟进事项")
        return _row(row)

    def compact_conversation(
        self,
        session_id: str,
        history: Iterable[dict[str, str]],
        *,
        keep_messages: int = 12,
    ) -> dict[str, Any]:
        messages = [item for item in history if item.get("content")]
        if len(messages) <= keep_messages:
            return self.context_summary(session_id)
        compacted = messages[:-keep_messages]
        source = "\n".join(f"{item.get('role')}:{item.get('content')}" for item in compacted)
        source_hash = hashlib.sha256(source.encode("utf-8", errors="ignore")).hexdigest()
        current = self.context_summary(session_id)
        if current.get("source_hash") == source_hash:
            return current
        lines = []
        for item in compacted[-20:]:
            role = "用户" if item.get("role") == "user" else "昔夕"
            content = re.sub(r"\s+", " ", str(item.get("content") or "")).strip()
            if content:
                lines.append(f"{role}：{content[:240]}")
        previous = str(current.get("summary") or "").strip()
        summary = "\n".join((["较早摘要：" + previous[:1200]] if previous else []) + lines)
        summary = summary[-3500:]
        now = _now()
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO conversation_summaries(
                    session_id, summary, compacted_messages, source_hash, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    summary=excluded.summary,
                    compacted_messages=conversation_summaries.compacted_messages + excluded.compacted_messages,
                    source_hash=excluded.source_hash,
                    updated_at=excluded.updated_at
                """,
                (session_id, summary, len(compacted), source_hash, now),
            )
        return self.context_summary(session_id)

    def context_summary(self, session_id: str) -> dict[str, Any]:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM conversation_summaries WHERE session_id=?", (session_id,)
            ).fetchone()
        return _row(row)

    def context_usage(self, session_id: str, history: Iterable[dict[str, str]], max_messages: int) -> dict[str, Any]:
        messages = list(history)
        summary = self.context_summary(session_id)
        used_chars = sum(len(str(item.get("content") or "")) for item in messages)
        estimated_max = max(4000, max_messages * 500)
        return {
            "session_id": session_id,
            "messages": len(messages),
            "max_messages": max_messages,
            "used_chars": used_chars,
            "estimated_max_chars": estimated_max,
            "percent": min(100, round(used_chars / estimated_max * 100)),
            "has_summary": bool(summary),
            "compacted_messages": int(summary.get("compacted_messages") or 0),
            "summary_updated_at": str(summary.get("updated_at") or ""),
        }

    def save_reflection(
        self,
        *,
        period_type: str,
        period_key: str,
        title: str,
        content: str,
        mood: str = "",
        source: str = "xixi",
    ) -> dict[str, Any]:
        if period_type not in {"daily", "weekly"}:
            raise ValueError("成长记录类型无效")
        if not content.strip():
            raise ValueError("成长记录不能为空")
        now = _now()
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO growth_reflections(
                    period_type, period_key, title, content, mood, source, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(period_type, period_key) DO UPDATE SET
                    title=excluded.title, content=excluded.content, mood=excluded.mood,
                    source=excluded.source, updated_at=excluded.updated_at
                """,
                (period_type, period_key, title[:200], content[:12000], mood[:100], source[:40], now, now),
            )
            row = connection.execute(
                "SELECT * FROM growth_reflections WHERE period_type=? AND period_key=?",
                (period_type, period_key),
            ).fetchone()
        return _row(row)

    def reflections(
        self,
        limit: int = 90,
        *,
        start_date: str = "",
        end_date: str = "",
    ) -> list[dict[str, Any]]:
        start = start_date.strip()
        end = end_date.strip()
        if start:
            date.fromisoformat(start)
        if end:
            date.fromisoformat(end)
        if start and end and end <= start:
            raise ValueError("成长记录结束日期必须晚于开始日期")

        conditions: list[str] = []
        parameters: list[Any] = []
        if start:
            conditions.append("period_key >= ?")
            parameters.append(start)
        if end:
            conditions.append("period_key < ?")
            parameters.append(end)
        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        parameters.append(max(1, min(366, int(limit))))
        with self._connection() as connection:
            rows = connection.execute(
                f"SELECT * FROM growth_reflections{where} "
                "ORDER BY period_key DESC, period_type ASC LIMIT ?",
                parameters,
            ).fetchall()
        return [dict(item) for item in rows]

    def record_model_usage(
        self,
        *,
        capability: str,
        provider: str,
        model_name: str,
        success: bool,
        latency_ms: int,
        input_chars: int = 0,
        output_chars: int = 0,
        error: str = "",
    ) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO model_usage_events(
                    capability, provider, model_name, success, latency_ms,
                    estimated_input_tokens, estimated_output_tokens, error, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    capability,
                    provider[:240],
                    model_name[:200],
                    int(success),
                    max(0, int(latency_ms)),
                    max(0, int(input_chars / 3.5)),
                    max(0, int(output_chars / 3.5)),
                    error[:1000],
                    _now(),
                ),
            )

    def usage_summary(self, days: int = 30) -> dict[str, Any]:
        since = (datetime.now(timezone.utc) - timedelta(days=max(1, min(365, int(days))))).isoformat(timespec="seconds")
        with self._connection() as connection:
            totals = connection.execute(
                """
                SELECT COUNT(*) AS requests, SUM(success) AS successes,
                       COALESCE(AVG(latency_ms), 0) AS average_latency_ms,
                       COALESCE(SUM(estimated_input_tokens), 0) AS input_tokens,
                       COALESCE(SUM(estimated_output_tokens), 0) AS output_tokens,
                       COALESCE(SUM(estimated_cost_yuan), 0) AS estimated_cost_yuan
                FROM model_usage_events WHERE created_at>=?
                """,
                (since,),
            ).fetchone()
            models = connection.execute(
                """
                SELECT model_name, provider, COUNT(*) AS requests, SUM(success) AS successes,
                       ROUND(AVG(latency_ms)) AS average_latency_ms
                FROM model_usage_events WHERE created_at>=?
                GROUP BY model_name, provider ORDER BY requests DESC
                """,
                (since,),
            ).fetchall()
        payload = _row(totals)
        requests = int(payload.get("requests") or 0)
        payload["success_rate"] = round(int(payload.get("successes") or 0) / requests * 100, 1) if requests else 0
        payload["models"] = [dict(item) for item in models]
        payload["days"] = days
        return payload

    def policy(self) -> dict[str, Any]:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM autonomy_policy WHERE id=1").fetchone()
        payload = _row(row)
        payload["paused"] = bool(payload.get("paused"))
        try:
            payload["capability_rules"] = {**_DEFAULT_RULES, **json.loads(payload.pop("capability_rules_json", "{}"))}
        except (TypeError, json.JSONDecodeError):
            payload["capability_rules"] = dict(_DEFAULT_RULES)
        payload.pop("privacy_snapshot_json", None)
        return payload

    def update_policy(self, values: dict[str, Any]) -> dict[str, Any]:
        current = self.policy()
        rules = dict(current["capability_rules"])
        incoming_rules = values.get("capability_rules")
        if isinstance(incoming_rules, dict):
            for capability, mode in incoming_rules.items():
                if capability in _DEFAULT_RULES and mode in {"auto", "owner_only", "manual_only", "deny"}:
                    rules[capability] = mode
        paused = bool(values.get("paused", current["paused"]))
        quiet_start = max(0, min(23, int(values.get("quiet_start_hour", current["quiet_start_hour"]))))
        quiet_end = max(0, min(23, int(values.get("quiet_end_hour", current["quiet_end_hour"]))))
        daily_limit = max(0, min(200, int(values.get("daily_action_limit", current["daily_action_limit"]))))
        budget = max(0.0, min(10000.0, float(values.get("daily_budget_yuan", current["daily_budget_yuan"]))))
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE autonomy_policy SET paused=?, quiet_start_hour=?, quiet_end_hour=?,
                    daily_action_limit=?, daily_budget_yuan=?, capability_rules_json=?, updated_at=?
                WHERE id=1
                """,
                (int(paused), quiet_start, quiet_end, daily_limit, budget, json.dumps(rules, ensure_ascii=False), _now()),
            )
        return self.policy()

    def capability_allowed(self, capability: str, *, is_owner: bool = False, manual: bool = False) -> bool:
        policy = self.policy()
        if policy["paused"] and capability not in {"chat", "memory"}:
            return False
        mode = policy["capability_rules"].get(capability, "deny")
        allowed = (
            mode == "auto"
            or mode == "owner_only" and is_owner
            or mode == "manual_only" and manual
        )
        if not allowed or capability != "autonomy" or manual:
            return allowed
        local_now = datetime.now().astimezone()
        start = int(policy["quiet_start_hour"])
        end = int(policy["quiet_end_hour"])
        in_quiet_hours = start <= local_now.hour < end if start < end else (
            local_now.hour >= start or local_now.hour < end
        )
        if in_quiet_hours:
            return False
        local_midnight = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
        since = local_midnight.astimezone(timezone.utc).isoformat(timespec="seconds")
        with self._connection() as connection:
            count = int(connection.execute(
                """
                SELECT COUNT(*) FROM tool_receipts
                WHERE capability='autonomy' AND status='completed' AND created_at>=?
                """,
                (since,),
            ).fetchone()[0])
        return count < int(policy["daily_action_limit"])

    def model_profiles(self, capability: str = "") -> list[dict[str, Any]]:
        query = "SELECT * FROM model_profiles"
        params: tuple[Any, ...] = ()
        if capability:
            query += " WHERE capability=?"
            params = (capability,)
        query += " ORDER BY priority, created_at"
        with self._connection() as connection:
            rows = connection.execute(query, params).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["enabled"] = bool(item["enabled"])
            item["use_primary_key"] = bool(item["use_primary_key"])
            result.append(item)
        return result

    @staticmethod
    def _split_capabilities(value: str) -> list[str]:
        allowed = {"language", "vision"}
        return [item for item in str(value or "").split(",") if item in allowed]

    def model_providers(self) -> list[dict[str, Any]]:
        with self._connection() as connection:
            providers = connection.execute(
                "SELECT * FROM model_providers ORDER BY name COLLATE NOCASE, created_at"
            ).fetchall()
            models = connection.execute(
                "SELECT * FROM model_provider_models ORDER BY provider_id, created_at"
            ).fetchall()
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in models:
            item = dict(row)
            item["enabled"] = bool(item["enabled"])
            item["capabilities"] = self._split_capabilities(item["capabilities"])
            grouped.setdefault(str(item["provider_id"]), []).append(item)
        result: list[dict[str, Any]] = []
        for row in providers:
            item = dict(row)
            item["enabled"] = bool(item["enabled"])
            item["models"] = grouped.get(str(item["id"]), [])
            result.append(item)
        return result

    def save_model_provider(self, payload: dict[str, Any]) -> dict[str, Any]:
        provider_id = re.sub(r"[^a-zA-Z0-9_-]", "", str(payload.get("id") or "")) or uuid.uuid4().hex[:16]
        name = str(payload.get("name") or "新供应商").strip()[:80]
        base_url = str(payload.get("base_url") or "").strip().rstrip("/")
        api_type = str(payload.get("api_type") or "auto").strip()
        if not name:
            raise ValueError("供应商名称不能为空")
        if not base_url:
            raise ValueError("供应商 API 地址不能为空")
        if api_type not in {"auto", "openai_chat", "openai_responses", "ollama", "anthropic", "gemini"}:
            raise ValueError("供应商接口类型无效")
        now = _now()
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO model_providers(id, name, base_url, api_type, enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name, base_url=excluded.base_url, api_type=excluded.api_type,
                    enabled=excluded.enabled, updated_at=excluded.updated_at
                """,
                (provider_id, name, base_url, api_type, int(bool(payload.get("enabled", True))), now, now),
            )
        return next((item for item in self.model_providers() if item["id"] == provider_id), {})

    def save_model_provider_model(self, payload: dict[str, Any]) -> dict[str, Any]:
        model_id = re.sub(r"[^a-zA-Z0-9_-]", "", str(payload.get("id") or "")) or uuid.uuid4().hex[:16]
        provider_id = str(payload.get("provider_id") or "").strip()
        name = str(payload.get("name") or payload.get("model_name") or "模型").strip()[:100]
        model_name = str(payload.get("model_name") or "").strip()[:200]
        capabilities = self._split_capabilities(",".join(payload.get("capabilities", [])) if isinstance(payload.get("capabilities"), list) else str(payload.get("capabilities") or payload.get("capability") or "language"))
        if not provider_id or not any(item["id"] == provider_id for item in self.model_providers()):
            raise ValueError("供应商不存在")
        if not model_name:
            raise ValueError("模型名称不能为空")
        if not capabilities:
            raise ValueError("至少选择一种模型能力")
        now = _now()
        with self._connection() as connection:
            existing = connection.execute(
                "SELECT id FROM model_provider_models WHERE provider_id=? AND model_name=?",
                (provider_id, model_name),
            ).fetchone()
            if existing is not None:
                model_id = str(existing["id"])
            connection.execute(
                """
                INSERT INTO model_provider_models(
                    id, provider_id, name, model_name, capabilities, cache_price, input_price,
                    output_price, currency, enabled, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    provider_id=excluded.provider_id, name=excluded.name,
                    model_name=excluded.model_name, capabilities=excluded.capabilities,
                    cache_price=excluded.cache_price, input_price=excluded.input_price,
                    output_price=excluded.output_price,
                    currency=excluded.currency, enabled=excluded.enabled, updated_at=excluded.updated_at
                """,
                (
                    model_id, provider_id, name, model_name, ",".join(capabilities),
                    max(0.0, float(payload.get("cache_price", 0) or 0)),
                    max(0.0, float(payload.get("input_price", 0) or 0)),
                    max(0.0, float(payload.get("output_price", 0) or 0)),
                    str(payload.get("currency") or "CNY")[:8], int(bool(payload.get("enabled", True))),
                    now, now,
                ),
            )
            row = connection.execute(
                "SELECT * FROM model_provider_models WHERE id=?", (model_id,)
            ).fetchone()
        item = dict(row)
        item["enabled"] = bool(item["enabled"])
        item["capabilities"] = self._split_capabilities(item["capabilities"])
        return item

    def model_provider_model(self, model_id: str) -> dict[str, Any]:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT m.*, p.name AS provider_name, p.base_url, p.api_type
                FROM model_provider_models m JOIN model_providers p ON p.id=m.provider_id
                WHERE m.id=?
                """, (model_id,)
            ).fetchone()
        item = dict(row)
        if item:
            item["enabled"] = bool(item["enabled"])
            item["capabilities"] = self._split_capabilities(item["capabilities"])
        return item

    def delete_model_provider_model(self, model_id: str) -> bool:
        with self._connection() as connection:
            cursor = connection.execute("DELETE FROM model_provider_models WHERE id=?", (model_id,))
        return cursor.rowcount > 0

    def delete_model_provider(self, provider_id: str) -> bool:
        with self._connection() as connection:
            cursor = connection.execute("DELETE FROM model_providers WHERE id=?", (provider_id,))
        return cursor.rowcount > 0

    def save_model_profile(self, payload: dict[str, Any]) -> dict[str, Any]:
        profile_id = re.sub(r"[^a-zA-Z0-9_-]", "", str(payload.get("id") or "")) or uuid.uuid4().hex[:16]
        name = str(payload.get("name") or payload.get("model_name") or "备用模型").strip()[:80]
        capability = str(payload.get("capability") or "language").strip()
        base_url = str(payload.get("base_url") or "").strip().rstrip("/")
        model_name = str(payload.get("model_name") or "").strip()
        api_type = str(payload.get("api_type") or "openai_chat").strip()
        if capability not in {"language", "vision"}:
            raise ValueError("模型能力无效")
        if api_type not in {"openai_chat", "openai_responses", "ollama"}:
            raise ValueError("模型接口类型无效")
        if not base_url or not model_name:
            raise ValueError("备用模型需要 API 地址和模型名称")
        now = _now()
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO model_profiles(
                    id, name, capability, base_url, model_name, api_type,
                    enabled, priority, use_primary_key, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name, capability=excluded.capability,
                    base_url=excluded.base_url, model_name=excluded.model_name,
                    api_type=excluded.api_type, enabled=excluded.enabled,
                    priority=excluded.priority, use_primary_key=excluded.use_primary_key,
                    updated_at=excluded.updated_at
                """,
                (
                    profile_id, name, capability, base_url, model_name, api_type,
                    int(bool(payload.get("enabled", True))),
                    max(1, min(999, int(payload.get("priority", 100)))),
                    int(bool(payload.get("use_primary_key", True))), now, now,
                ),
            )
            row = connection.execute("SELECT * FROM model_profiles WHERE id=?", (profile_id,)).fetchone()
        return {**_row(row), "enabled": bool(row["enabled"]), "use_primary_key": bool(row["use_primary_key"])}

    def delete_model_profile(self, profile_id: str) -> bool:
        with self._connection() as connection:
            cursor = connection.execute("DELETE FROM model_profiles WHERE id=?", (profile_id,))
        return cursor.rowcount > 0

    def dashboard(self) -> dict[str, Any]:
        runs = self.runs(40)["items"]
        pending = self.pending_threads(limit=40)
        return {
            "goals": self.goals(),
            "runs": runs,
            "pending_threads": pending,
            "policy": self.policy(),
            "usage": self.usage_summary(30),
            "reflections": self.reflections(45),
            "migrations": self.migration_status(),
            "summary": {
                "active_goals": sum(item["status"] == "active" for item in self.goals()),
                "running_tasks": sum(item["status"] == "running" for item in runs),
                "failed_tasks": sum(item["status"] == "failed" for item in runs),
                "pending_threads": len(pending),
            },
        }


def current_week_key(value: date | None = None) -> str:
    current = value or date.today()
    monday = current - timedelta(days=current.weekday())
    return monday.isoformat()
