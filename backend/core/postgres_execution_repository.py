"""PostgreSQL transaction boundary for production execution persistence.

The connection is injected so deployment code controls pooling, TLS, and
credentials. This module intentionally does not create a broker or read keys.
It requires a DB driver only when this repository is selected.
"""
import json


class PostgresExecutionRepository:
    def __init__(self, connection_factory):
        if not callable(connection_factory):
            raise ValueError("connection_factory가 필요합니다.")
        self.connection_factory = connection_factory

    def commit_plan(self, *, deployment_id, schedule_key, decision, intents, snapshot_id=None):
        conn = self.connection_factory()
        try:
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute(
                        """insert into v2_strategy_runs(deployment_id,schedule_key,decision,snapshot_id)
                           values(%s,%s,%s,%s)
                           on conflict(deployment_id,schedule_key) do update set decision=v2_strategy_runs.decision
                           returning id""",
                        (deployment_id, schedule_key, json.dumps(decision, default=str), snapshot_id),
                    )
                    run_id = cur.fetchone()[0]
                    for intent in intents:
                        cur.execute(
                            """insert into v2_order_intents
                               (run_id,account_id,client_order_id,symbol,side,quantity,reference_price,pause_epoch)
                               values(%s,%s,%s,%s,%s,%s,%s,%s)
                               on conflict(account_id,client_order_id) do nothing""",
                            (run_id, intent.account_id, intent.client_order_id, intent.symbol, intent.side,
                             str(intent.quantity), str(intent.reference_price), intent.pause_epoch),
                        )
                        cur.execute(
                            """insert into v2_outbox(event_key,payload)
                               values(%s,%s) on conflict(event_key) do nothing""",
                            (f"submit:{intent.client_order_id}", json.dumps({"client_order_id": intent.client_order_id}, default=str)),
                        )
            return {"run_id": str(run_id), "intent_count": len(intents)}
        finally:
            conn.close()

    def mark_submitted(self, client_order_id, result):
        conn = self.connection_factory()
        try:
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute("update v2_order_intents set status='SUBMITTED' where client_order_id=%s", (client_order_id,))
                    cur.execute("update v2_outbox set status='DONE', attempts=attempts+1, payload=%s where event_key=%s",
                                (json.dumps(result, default=str), f"submit:{client_order_id}"))
        finally:
            conn.close()
