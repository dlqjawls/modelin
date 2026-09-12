"""Fencing lease for one account's worker.

The lease is a coordination aid, not proof of exactly-once delivery. External
order lookup and client order IDs remain required during recovery.
"""
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import RLock


class AccountLeaseStore:
    def __init__(self, path="modelin-paper.sqlite3"):
        self.path = str(Path(path))
        self._lock = RLock()
        db = sqlite3.connect(self.path)
        try:
            db.execute("create table if not exists account_leases(account_id text primary key, lease_owner text not null, lease_until text not null, fencing_token integer not null)")
            db.commit()
        finally:
            db.close()

    def acquire(self, account_id, owner, *, now=None, ttl_seconds=30):
        now = now or datetime.now(timezone.utc)
        until = now + timedelta(seconds=ttl_seconds)
        with self._lock:
            db = sqlite3.connect(self.path, timeout=30, isolation_level="IMMEDIATE")
            try:
                row = db.execute("select lease_owner,lease_until,fencing_token from account_leases where account_id=?", (account_id,)).fetchone()
                if row and row[1] > now.isoformat() and row[0] != owner:
                    db.rollback()
                    return None
                token = (row[2] + 1) if row else 1
                db.execute("insert or replace into account_leases values(?,?,?,?)", (account_id, owner, until.isoformat(), token))
                db.commit()
                return {"account_id": account_id, "owner": owner, "fencing_token": token, "lease_until": until.isoformat()}
            finally:
                db.close()

    def valid(self, account_id, owner, fencing_token, *, now=None):
        now = now or datetime.now(timezone.utc)
        db = sqlite3.connect(self.path)
        try:
            row = db.execute("select lease_owner,lease_until,fencing_token from account_leases where account_id=?", (account_id,)).fetchone()
            return bool(row and row[0] == owner and row[2] == fencing_token and row[1] > now.isoformat())
        finally:
            db.close()
