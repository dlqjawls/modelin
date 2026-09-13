"""SQLite-backed paper broker for local development and paper deployment.

SQLite is a local fallback until the configured PostgreSQL/Supabase repository
is available.  It uses transactions so a process restart does not erase the
paper account.
"""
import sqlite3
from decimal import Decimal
from pathlib import Path
from threading import RLock
from uuid import uuid4


def account_database_path(base_path: str, account_id: str) -> str:
    """Return a stable isolated SQLite path for one paper account."""
    base = Path(base_path)
    safe_id = "".join(ch for ch in str(account_id) if ch.isalnum() or ch in "-_")
    if not safe_id:
        raise ValueError("account_id가 필요합니다.")
    return str(base.with_name(f"{base.stem}.{safe_id}{base.suffix}"))

class PersistentPaperBroker:
    def __init__(self, path: str = "modelin-paper.sqlite3", initial_cash: Decimal = Decimal("10000000"), fee_rate: Decimal = Decimal("0.00015")):
        self.path = str(Path(path))
        self.fee_rate = Decimal(str(fee_rate))
        self._lock = RLock()
        db = self._connect()
        try:
            db.executescript("""
            create table if not exists paper_account (id integer primary key check(id=1), cash text not null, fee_rate text not null);
            create table if not exists paper_positions (market text not null, symbol text not null, quantity text not null, avg_price text not null, primary key(market,symbol));
            create table if not exists paper_orders (id text primary key, client_order_id text not null unique, symbol text, market text, side text, quantity text, requested_price text, filled_quantity text, average_price text, status text, fee text, created_at text);
            create table if not exists paper_order_events (id integer primary key autoincrement, order_id text not null, event_type text not null, payload text not null, created_at text not null);
            """)
            if db.execute("select 1 from paper_account where id=1").fetchone() is None:
                db.execute("insert into paper_account values(1,?,?)", (str(initial_cash), str(self.fee_rate)))
            db.commit()
        finally:
            db.close()

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=30, isolation_level="IMMEDIATE")
        db.row_factory = sqlite3.Row
        return db

    @staticmethod
    def _positive(value):
        result = Decimal(str(value))
        if not result.is_finite() or result <= 0:
            raise ValueError("금액과 수량은 유한한 양수여야 합니다.")
        return result

    def order(self, *, symbol, market, side, quantity, price, client_order_id=None):
        if side not in {"buy", "sell"}:
            raise ValueError("side는 buy 또는 sell이어야 합니다.")
        qty, px = self._positive(quantity), self._positive(price)
        client_order_id = client_order_id or str(uuid4())
        order_id = str(uuid4())
        with self._lock:
            db = self._connect()
            try:
                account = db.execute("select cash,fee_rate from paper_account where id=1").fetchone()
                existing = db.execute("select * from paper_orders where client_order_id=?", (client_order_id,)).fetchone()
                if existing:
                    return dict(existing)
                cash, fee_rate = Decimal(account["cash"]), Decimal(account["fee_rate"])
                row = db.execute("select quantity,avg_price from paper_positions where market=? and symbol=?", (market, symbol)).fetchone()
                current_qty = Decimal(row["quantity"]) if row else Decimal("0")
                current_avg = Decimal(row["avg_price"]) if row else Decimal("0")
                gross, fee = qty * px, qty * px * fee_rate
                if side == "buy":
                    if cash < gross + fee: raise ValueError("주문가능 현금이 부족합니다.")
                    cash -= gross + fee
                    new_qty = current_qty + qty
                    new_avg = ((current_qty * current_avg) + gross + fee) / new_qty
                else:
                    if current_qty < qty: raise ValueError("보유 수량보다 많이 매도할 수 없습니다.")
                    cash += gross - fee
                    new_qty, new_avg = current_qty - qty, current_avg
                db.execute("update paper_account set cash=? where id=1", (str(cash),))
                if new_qty:
                    db.execute("insert or replace into paper_positions values(?,?,?,?)", (market, symbol, str(new_qty), str(new_avg)))
                else:
                    db.execute("delete from paper_positions where market=? and symbol=?", (market, symbol))
                created = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
                db.execute("insert into paper_orders values(?,?,?,?,?,?,?,?,?,?,?,?)", (order_id, client_order_id, symbol, market, side, str(qty), str(px), str(qty), str(px), "filled", str(fee), created))
                db.execute("insert into paper_order_events(order_id,event_type,payload,created_at) values(?,?,?,?)", (order_id, "FILLED", "{}", created))
                db.commit()
            finally:
                db.close()
        return {"id": order_id, "client_order_id": client_order_id, "symbol": symbol, "market": market, "side": side, "quantity": str(qty), "filled_quantity": str(qty), "average_price": str(px), "status": "filled", "fee": str(fee), "created_at": created}

    def snapshot(self):
        db = self._connect()
        try:
            cash = db.execute("select cash from paper_account where id=1").fetchone()["cash"]
            positions = [dict(r) for r in db.execute("select market,symbol,quantity,avg_price from paper_positions")]
            orders = [dict(r) for r in db.execute("select * from paper_orders order by created_at desc")]
            events = [dict(r) for r in db.execute("select * from paper_order_events order by id desc")]
            return {"cash": cash, "positions": positions, "orders": orders, "events": events, "persistence": "sqlite"}
        finally:
            db.close()
