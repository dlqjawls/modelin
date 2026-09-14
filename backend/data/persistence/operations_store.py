"""Small transactional store for paper operations.

This is the local implementation of the repository boundary. It can later be
replaced by the PostgreSQL repository without changing the API contract.
"""
import json
import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock


class OperationsStore:
    def __init__(self, path="modelin-paper.sqlite3"):
        self.path = str(Path(path))
        self._lock = RLock()
        db = sqlite3.connect(self.path)
        try:
            db.executescript("""
            create table if not exists operation_accounts(
              id text primary key, name text not null, mode text not null,
              market text not null, currency text not null, initial_cash text not null,
              status text not null, created_at text not null);
            create table if not exists operation_deployments(
              id text primary key, account_id text not null, mode text not null,
              strategy text not null, allocation_amount text not null, cash_buffer text not null,
              desired_state text not null, observed_state text not null,
              pause_epoch integer not null, revision integer not null, last_error text);
            create index if not exists operation_deployments_account on operation_deployments(account_id);
            create table if not exists operation_api_requests(
              scope text not null, endpoint text not null, idem_key text not null,
              request_hash text not null, status_code integer not null,
              response_json text not null, created_at text not null,
              primary key(scope, endpoint, idem_key));
            """)
            db.commit()
        finally:
            db.close()

    def _db(self):
        db = sqlite3.connect(self.path, timeout=30, isolation_level="IMMEDIATE")
        db.row_factory = sqlite3.Row
        return db

    def create_account(self, item):
        with self._lock:
            db = self._db()
            try:
                db.execute("insert into operation_accounts values(?,?,?,?,?,?,?,?)",
                           (item["id"], item["name"], item["mode"], item["market"], item["currency"], item["initial_cash"], item["status"], item["created_at"]))
                db.commit()
            finally:
                db.close()
        return item

    def accounts(self):
        db = self._db()
        try:
            rows = [dict(row) for row in db.execute("select * from operation_accounts order by created_at desc")]
            # Repeated local setup calls can create identical paper account
            # profiles. Keep the newest record visible while preserving the
            # underlying audit rows and account IDs.
            unique = {}
            for row in rows:
                key = (row["name"], row["mode"], row["market"], row["currency"], row["initial_cash"])
                unique.setdefault(key, row)
            return list(unique.values())
        finally: db.close()

    def account(self, account_id):
        db = self._db()
        try:
            row = db.execute("select * from operation_accounts where id=?", (account_id,)).fetchone()
            return dict(row) if row else None
        finally: db.close()

    def create_deployment(self, item):
        with self._lock:
            db = self._db()
            try:
                active = db.execute("select id from operation_deployments where account_id=? and observed_state != 'ARCHIVED'", (item["account_id"],)).fetchone()
                if active:
                    raise ValueError("계좌에 활성 deployment가 이미 있습니다.")
                db.execute("insert into operation_deployments values(?,?,?,?,?,?,?,?,?,?,?)",
                           (item["id"], item["account_id"], item["mode"], json.dumps(item["strategy"]), item["allocation_amount"], item["cash_buffer"], item["desired_state"], item["observed_state"], item["pause_epoch"], item["revision"], item["last_error"]))
                db.commit()
            finally: db.close()
        return item

    def deployment(self, deployment_id):
        db = self._db()
        try:
            row = db.execute("select * from operation_deployments where id=?", (deployment_id,)).fetchone()
            if not row: return None
            item = dict(row); item["strategy"] = json.loads(item["strategy"]); return item
        finally: db.close()

    def update_deployment(self, item):
        with self._lock:
            db = self._db()
            try:
                db.execute("update operation_deployments set desired_state=?,observed_state=?,pause_epoch=?,revision=?,last_error=? where id=?",
                           (item["desired_state"], item["observed_state"], item["pause_epoch"], item["revision"], item.get("last_error"), item["id"]))
                db.commit()
            finally: db.close()
        return item

    def update_deployment_if_revision(self, item, expected_revision):
        """Atomically apply a control transition only once."""
        with self._lock:
            db = self._db()
            try:
                cursor = db.execute(
                    "update operation_deployments set desired_state=?,observed_state=?,pause_epoch=?,revision=?,last_error=? where id=? and revision=?",
                    (item["desired_state"], item["observed_state"], item["pause_epoch"], item["revision"], item.get("last_error"), item["id"], expected_revision),
                )
                db.commit()
                return cursor.rowcount == 1
            finally:
                db.close()

    def deployments(self):
        db = self._db()
        try:
            result = []
            for row in db.execute("select * from operation_deployments order by id"):
                item = dict(row); item["strategy"] = json.loads(item["strategy"]); result.append(item)
            return result
        finally:
            db.close()

    @staticmethod
    def request_hash(payload):
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def idempotent_response(self, *, scope, endpoint, key, payload):
        """Return a prior response, or None when this key is unused.

        A reused key with a different canonical request body is rejected by
        the caller. The unique primary key also protects concurrent retries.
        """
        if not key:
            return None
        db = self._db()
        try:
            row = db.execute("select request_hash,status_code,response_json from operation_api_requests where scope=? and endpoint=? and idem_key=?", (scope, endpoint, key)).fetchone()
            if not row:
                return None
            if row["request_hash"] != self.request_hash(payload):
                raise ValueError("Idempotency-Key가 다른 요청 본문과 재사용되었습니다.")
            return {"status_code": row["status_code"], "response": json.loads(row["response_json"])}
        finally:
            db.close()

    def save_idempotent_response(self, *, scope, endpoint, key, payload, status_code, response):
        if not key:
            return
        with self._lock:
            db = self._db()
            try:
                db.execute("insert or ignore into operation_api_requests values(?,?,?,?,?,?,?)",
                           (scope, endpoint, key, self.request_hash(payload), status_code,
                            json.dumps(response, ensure_ascii=False, separators=(",", ":")),
                            datetime.now(timezone.utc).isoformat()))
                db.commit()
            finally:
                db.close()
