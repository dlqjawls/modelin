"""Durable paper execution journal used before broker submission.

The journal is deliberately broker neutral: a future live worker can use the
same plan/outbox boundary with PostgreSQL while the local paper mode remains
fully restartable.
"""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from uuid import uuid4


class ExecutionJournal:
    def __init__(self, path="modelin-paper.sqlite3"):
        self.path = str(Path(path))
        self._lock = RLock()
        db = sqlite3.connect(self.path)
        try:
            db.executescript("""
            create table if not exists execution_runs(
              id text primary key, deployment_id text not null,
              schedule_key text not null, decision_json text not null,
              created_at text not null, unique(deployment_id, schedule_key));
            create table if not exists execution_intents(
              id text primary key, run_id text not null, client_order_id text not null unique,
              symbol text not null, side text not null, quantity text not null,
              reference_price text not null, status text not null default 'PENDING',
              result_json text, created_at text not null);
            create table if not exists execution_outbox(
              event_key text primary key, intent_id text not null,
              status text not null default 'PENDING', attempts integer not null default 0,
              created_at text not null);
            """)
            db.commit()
        finally:
            db.close()

    def _db(self):
        db = sqlite3.connect(self.path, timeout=30, isolation_level="IMMEDIATE")
        db.row_factory = sqlite3.Row
        return db

    def commit_plan(self, *, deployment_id, schedule_key, decision, intents):
        """Atomically persist one decision, all intents, and outbox entries."""
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            db = self._db()
            try:
                existing = db.execute("select id from execution_runs where deployment_id=? and schedule_key=?", (deployment_id, schedule_key)).fetchone()
                if existing:
                    rows = db.execute("select * from execution_intents where run_id=? order by id", (existing["id"],)).fetchall()
                    return existing["id"], [dict(row) for row in rows]
                run_id = str(uuid4())
                db.execute("insert into execution_runs values(?,?,?,?,?)", (run_id, deployment_id, schedule_key, json.dumps(decision, default=str), now))
                saved = []
                for intent in intents:
                    intent_id = str(uuid4())
                    client_id = intent.client_order_id
                    db.execute("insert into execution_intents values(?,?,?,?,?,?,?,?,?,?)", (intent_id, run_id, client_id, intent.symbol, intent.side, str(intent.quantity), str(intent.reference_price), "PENDING", None, now))
                    db.execute("insert into execution_outbox values(?,?,?,?,?)", (f"submit:{client_id}", intent_id, "PENDING", 0, now))
                    saved.append(intent_id)
                db.commit()
                rows = db.execute("select * from execution_intents where run_id=? order by id", (run_id,)).fetchall()
                return run_id, [dict(row) for row in rows]
            finally:
                db.close()

    def has_run(self, deployment_id, schedule_key):
        db = self._db()
        try:
            return db.execute(
                "select 1 from execution_runs where deployment_id=? and schedule_key=?",
                (deployment_id, schedule_key),
            ).fetchone() is not None
        finally:
            db.close()

    def mark_submitted(self, client_order_id, result):
        with self._lock:
            db = self._db()
            try:
                db.execute("update execution_intents set status='SUBMITTED',result_json=? where client_order_id=?", (json.dumps(result, default=str), client_order_id))
                db.execute("update execution_outbox set status='DONE',attempts=attempts+1 where event_key=?", (f"submit:{client_order_id}",))
                db.commit()
            finally:
                db.close()

    def pending(self):
        db = self._db()
        try:
            return [dict(row) for row in db.execute("select * from execution_intents where status='PENDING' order by created_at")]
        finally:
            db.close()

    def mark_recovery_unknown(self, client_order_id):
        """Quarantine an intent whose broker outcome cannot be proven."""
        with self._lock:
            db = self._db()
            try:
                db.execute("update execution_intents set status='RECOVERY_UNKNOWN' where client_order_id=?", (client_order_id,))
                db.execute("update execution_outbox set status='BLOCKED',attempts=attempts+1 where event_key=?", (f"submit:{client_order_id}",))
                db.commit()
            finally:
                db.close()
