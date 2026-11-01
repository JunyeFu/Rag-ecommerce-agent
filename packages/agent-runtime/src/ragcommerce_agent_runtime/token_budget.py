"""PostgreSQL pre-call reservations shared by API, Workers and acceptance runs.

Unknown usage keeps its reservation and blocks further paid requests. There is
no automatic refund for interrupted requests and no key/prompt/media storage.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import psycopg


class BudgetRefused(RuntimeError):
    pass


class PostgresTokenBudget:
    def __init__(
        self,
        dsn: str,
        session_id: str,
        total_limit: int = 2_000_000,
        *,
        require_scenario: bool = False,
    ) -> None:
        self.dsn = dsn.replace("postgresql+psycopg://", "postgresql://", 1)
        self.session_id = session_id
        self.total_limit = total_limit
        self.require_scenario = require_scenario

    def start_scenario(
        self,
        scenario_id: str,
        owner_id: UUID,
        group: str,
        phase: str = "first",
        root_cause_ref: str | None = None,
        *,
        additional_retest_slot: str | None = None,
        additional_retest_position: int = 0,
        authorize_model_calls: bool = True,
    ) -> None:
        caps = {"golden": 10, "media": 4, "android": 10}
        if group not in caps or phase not in {"first", "retest"}:
            raise BudgetRefused("unknown authorized scenario group or phase")
        if phase == "retest" and not root_cause_ref:
            raise BudgetRefused("retest requires a documented corrected root cause")
        with psycopg.connect(self.dsn) as connection:
            connection.execute(
                "INSERT INTO model_budget_sessions(session_id,total_limit,blocked) VALUES (%s,%s,false) ON CONFLICT DO NOTHING",
                (self.session_id, self.total_limit),
            )
            limit, blocked = connection.execute(
                "SELECT total_limit,blocked FROM model_budget_sessions WHERE session_id=%s FOR UPDATE",
                (self.session_id,),
            ).fetchone()
            if blocked or limit != self.total_limit:
                raise BudgetRefused("budget session blocked or its authorized limit differs")
            existing = connection.execute(
                "SELECT 1 FROM model_budget_scenarios WHERE session_id=%s AND (scenario_id=%s OR (owner_id=%s AND finished_at IS NULL))",
                (self.session_id, scenario_id, owner_id),
            ).fetchone()
            if existing:
                raise BudgetRefused("scenario slot already used or owner has an active scenario")
            count = connection.execute(
                "SELECT COUNT(*) FROM model_budget_scenarios WHERE session_id=%s AND phase=%s AND (%s='retest' OR scenario_group=%s)",
                (self.session_id, phase, phase, group),
            ).fetchone()[0]
            extra_authorized = (
                phase == "retest"
                and count == 6 + additional_retest_position
                and scenario_id == additional_retest_slot
            )
            if count >= (6 if phase == "retest" else caps[group]) and not extra_authorized:
                raise BudgetRefused("authorized scenario slots exhausted")
            connection.execute(
                "INSERT INTO model_budget_scenarios(session_id,scenario_id,owner_id,scenario_group,phase,root_cause_ref,active,started_at) VALUES (%s,%s,%s,%s,%s,%s,%s,CURRENT_TIMESTAMP)",
                (
                    self.session_id,
                    scenario_id,
                    owner_id,
                    group,
                    phase,
                    root_cause_ref,
                    authorize_model_calls,
                ),
            )

    def finish_scenario(self, scenario_id: str, result: str) -> None:
        if result not in {"passed", "failed", "blocked"}:
            raise BudgetRefused("unknown scenario result")
        with psycopg.connect(self.dsn) as connection:
            row = connection.execute(
                "UPDATE model_budget_scenarios SET active=false,result=%s,finished_at=CURRENT_TIMESTAMP WHERE session_id=%s AND scenario_id=%s AND finished_at IS NULL RETURNING scenario_id",
                (result, self.session_id, scenario_id),
            ).fetchone()
            if not row:
                raise BudgetRefused("scenario already finished or does not exist")

    def reserve(
        self, run_id: UUID, run_limit: int, input_upper: int, output_limit: int, model: str
    ) -> tuple[UUID, int]:
        with psycopg.connect(self.dsn) as connection:
            connection.execute(
                "INSERT INTO model_budget_sessions(session_id,total_limit,blocked) VALUES (%s,%s,false) ON CONFLICT DO NOTHING",
                (self.session_id, self.total_limit),
            )
            limit, blocked = connection.execute(
                "SELECT total_limit,blocked FROM model_budget_sessions WHERE session_id=%s FOR UPDATE",
                (self.session_id,),
            ).fetchone()
            if blocked or limit != self.total_limit:
                raise BudgetRefused("budget session blocked or its authorized limit differs")
            scenario_id = None
            if self.require_scenario:
                scenario = connection.execute(
                    "SELECT s.scenario_id FROM model_budget_scenarios s JOIN api_turns t ON t.owner_id=s.owner_id "
                    "WHERE s.session_id=%s AND s.active AND t.run_id=%s",
                    (self.session_id, run_id),
                ).fetchone()
                if not scenario:
                    raise BudgetRefused(
                        "paid call has no active authorized scenario for this owner"
                    )
                scenario_id = scenario[0]
            total, run_total = connection.execute(
                "SELECT COALESCE(SUM(COALESCE(used_tokens,reserved_tokens)),0), "
                "COALESCE(SUM(CASE WHEN run_id=%s THEN COALESCE(used_tokens,reserved_tokens) ELSE 0 END),0) "
                "FROM model_budget_calls WHERE session_id=%s",
                (run_id, self.session_id),
            ).fetchone()
            reserved = min(limit - total, run_limit - run_total)
            completion = min(output_limit, reserved - input_upper)
            if completion < 256:
                raise BudgetRefused(
                    "remaining authorized tokens cannot cover input plus output margin"
                )
            call_id = uuid4()
            connection.execute(
                "INSERT INTO model_budget_calls(call_id,session_id,run_id,reserved_tokens,model,status,created_at,scenario_id) "
                "VALUES (%s,%s,%s,%s,%s,'pending',CURRENT_TIMESTAMP,%s)",
                (call_id, self.session_id, run_id, reserved, model, scenario_id),
            )
            return call_id, completion

    def settle(self, call_id: UUID, total_tokens: int | None, status: str) -> None:
        with psycopg.connect(self.dsn) as connection:
            connection.execute(
                "SELECT session_id FROM model_budget_sessions WHERE session_id=%s FOR UPDATE",
                (self.session_id,),
            )
            reserved, old_status = connection.execute(
                "SELECT reserved_tokens,status FROM model_budget_calls WHERE call_id=%s AND session_id=%s FOR UPDATE",
                (call_id, self.session_id),
            ).fetchone()
            if old_status != "pending":
                raise BudgetRefused("call already settled")
            connection.execute(
                "UPDATE model_budget_calls SET used_tokens=%s,status=%s,settled_at=CURRENT_TIMESTAMP WHERE call_id=%s",
                (total_tokens, status if total_tokens is not None else "usage_unknown", call_id),
            )
            if total_tokens is None or total_tokens > reserved:
                connection.execute(
                    "UPDATE model_budget_sessions SET blocked=true WHERE session_id=%s",
                    (self.session_id,),
                )
        if total_tokens is None or total_tokens > reserved:
            raise BudgetRefused(
                "provider usage missing or exceeded the reserved bound; paid execution stopped"
            )

    def summary(self) -> dict[str, int | bool | str]:
        with psycopg.connect(self.dsn) as connection:
            row = connection.execute(
                "SELECT s.total_limit,s.blocked,COALESCE(SUM(c.used_tokens),0),"
                "COALESCE(SUM(CASE WHEN c.used_tokens IS NULL THEN c.reserved_tokens ELSE 0 END),0),COUNT(c.call_id) "
                "FROM model_budget_sessions s LEFT JOIN model_budget_calls c USING(session_id) "
                "WHERE s.session_id=%s GROUP BY s.session_id",
                (self.session_id,),
            ).fetchone()
        if row is None:
            return {
                "session_id": self.session_id,
                "limit": self.total_limit,
                "used": 0,
                "held": 0,
                "calls": 0,
                "blocked": False,
            }
        return {
            "session_id": self.session_id,
            "limit": row[0],
            "blocked": row[1],
            "used": row[2],
            "held": row[3],
            "calls": row[4],
        }
