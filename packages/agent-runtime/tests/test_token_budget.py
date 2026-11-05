import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import psycopg
import pytest
from ragcommerce_agent_runtime import OpenAICompatibleProvider, ProviderBudgetExceeded, TurnCommand
from ragcommerce_agent_runtime.token_budget import BudgetRefused, PostgresTokenBudget


class BudgetProbe:
    def __init__(self):
        self.reserved = False
        self.settled = False

    def reserve(self, run_id, run_limit, input_upper, output_limit, model):
        assert input_upper > 1024
        self.reserved = True
        return uuid4(), 512

    def settle(self, call_id, total, status):
        self.settled = True
        if total is None:
            raise BudgetRefused("unknown usage")


def test_paid_boundary_reserves_before_call_and_limits_completion():
    budget = BudgetProbe()

    class Transport:
        async def post_json(self, url, headers, payload, timeout_seconds):
            assert budget.reserved
            assert payload["max_completion_tokens"] == 512
            return 200, {
                "choices": [{"message": {"content": "请补充用途"}}],
                "usage": {"total_tokens": 100},
            }

    provider = OpenAICompatibleProvider(
        "https://model.example/v1",
        "test-only",
        "test-model",
        transport=Transport(),
        token_budget=budget,
    )
    asyncio.run(
        request_response(
            provider, TurnCommand(uuid4(), uuid4(), uuid4(), "budget-test", "买耳机"), ()
        )
    )
    assert budget.settled


def test_missing_usage_is_not_charged_as_zero():
    class Transport:
        async def post_json(self, *args):
            return 200, {"choices": [{"message": {"content": "请补充用途"}}]}

    provider = OpenAICompatibleProvider(
        "https://model.example/v1",
        "test-only",
        "test-model",
        transport=Transport(),
        token_budget=BudgetProbe(),
    )
    with pytest.raises(ProviderBudgetExceeded, match="unknown usage"):
        asyncio.run(
            request_response(
                provider, TurnCommand(uuid4(), uuid4(), uuid4(), "budget-test", "买耳机"), ()
            )
        )


def test_network_transport_cannot_execute_without_shared_ledger():
    provider = OpenAICompatibleProvider("https://model.example/v1", "test-only", "test-model")
    with pytest.raises(ProviderBudgetExceeded, match="shared PostgreSQL"):
        asyncio.run(
            request_response(
                provider, TurnCommand(uuid4(), uuid4(), uuid4(), "budget-test", "买耳机"), ()
            )
        )


@pytest.mark.integration
def test_pg_reservations_across_independent_clients_and_unknown_usage():
    dsn = os.environ.get("API_DATABASE_URL")
    if not dsn:
        pytest.skip("API_DATABASE_URL required")
    session = f"budget-integration-{uuid4().hex}"
    run = uuid4()

    def attempt(index):
        budget = PostgresTokenBudget(dsn, session, 96_000)
        try:
            return budget.reserve(run if index < 4 else uuid4(), 48_000, 2000, 2048, "test-only")
        except BudgetRefused:
            return None

    try:
        with ThreadPoolExecutor(max_workers=8) as executor:
            reservations = list(executor.map(attempt, range(8)))
        calls = [item for item in reservations if item is not None]
        assert len(calls) == 2
        budget = PostgresTokenBudget(dsn, session, 96_000)
        assert budget.summary()["held"] == 96_000
        budget.settle(calls[0][0], 1000, "http_200")
        assert budget.summary()["used"] == 1000
        with pytest.raises(BudgetRefused, match="missing"):
            budget.settle(calls[1][0], None, "timeout")
        with pytest.raises(BudgetRefused, match="blocked"):
            PostgresTokenBudget(dsn, session, 96_000).reserve(
                uuid4(), 48_000, 2000, 2048, "test-only"
            )
    finally:
        with psycopg.connect(
            dsn.replace("postgresql+psycopg://", "postgresql://", 1)
        ) as connection:
            connection.execute("DELETE FROM model_budget_calls WHERE session_id=%s", (session,))
            connection.execute("DELETE FROM model_budget_sessions WHERE session_id=%s", (session,))


@pytest.mark.integration
def test_scenario_slots_refuse_duplicate_and_unapproved_paid_calls():
    dsn = os.environ.get("API_DATABASE_URL")
    if not dsn:
        pytest.skip("API_DATABASE_URL required")
    session = f"scenario-integration-{uuid4().hex}"
    owner = uuid4()
    budget = PostgresTokenBudget(dsn, session, require_scenario=True)
    try:
        budget.start_scenario("G01", owner, "golden")
        with pytest.raises(BudgetRefused, match="active"):
            budget.start_scenario("G02", owner, "golden")
        with pytest.raises(BudgetRefused, match="no active"):
            budget.reserve(uuid4(), 48_000, 2000, 2048, "test-only")
        budget.finish_scenario("G01", "failed")
        with pytest.raises(BudgetRefused, match="already used"):
            budget.start_scenario("G01", owner, "golden")
        with pytest.raises(BudgetRefused, match="root cause"):
            budget.start_scenario("G01-R1", owner, "golden", "retest")
        for index in range(6):
            slot = f"G01-R{index + 1}"
            budget.start_scenario(slot, owner, "golden", "retest", "docs/defects/test.md#fixed")
            budget.finish_scenario(slot, "passed")
        with pytest.raises(BudgetRefused, match="exhausted"):
            budget.start_scenario("G01-R7", owner, "golden", "retest", "docs/defects/test.md#fixed")
        budget.start_scenario(
            "A01-R1",
            owner,
            "android",
            "retest",
            "docs/defects/test.md#fixed",
            additional_retest_slot="A01-R1",
        )
        budget.finish_scenario("A01-R1", "passed")
        with pytest.raises(BudgetRefused, match="exhausted"):
            budget.start_scenario(
                "A02-R1",
                owner,
                "android",
                "retest",
                "docs/defects/test.md#fixed",
                additional_retest_slot="A01-R1",
            )
        budget.start_scenario(
            "A06-R1",
            owner,
            "android",
            "retest",
            "docs/defects/test.md#fixed",
            additional_retest_slot="A06-R1",
            additional_retest_position=1,
            authorize_model_calls=False,
        )
        with psycopg.connect(
            dsn.replace("postgresql+psycopg://", "postgresql://", 1)
        ) as connection:
            assert connection.execute(
                "SELECT active,finished_at FROM model_budget_scenarios WHERE session_id=%s AND scenario_id='A06-R1'",
                (session,),
            ).fetchone() == (False, None)
        with pytest.raises(BudgetRefused, match="active"):
            budget.start_scenario("A03", owner, "android")
        with pytest.raises(BudgetRefused, match="no active"):
            budget.reserve(uuid4(), 48_000, 2000, 2048, "test-only")
        budget.finish_scenario("A06-R1", "passed")
        with pytest.raises(BudgetRefused, match="already finished"):
            budget.finish_scenario("A06-R1", "passed")
        with pytest.raises(BudgetRefused, match="exhausted"):
            budget.start_scenario(
                "A06-R2", owner, "android", "retest", "docs/defects/test.md#fixed"
            )
    finally:
        with psycopg.connect(
            dsn.replace("postgresql+psycopg://", "postgresql://", 1)
        ) as connection:
            connection.execute("DELETE FROM model_budget_calls WHERE session_id=%s", (session,))
            connection.execute("DELETE FROM model_budget_scenarios WHERE session_id=%s", (session,))
            connection.execute("DELETE FROM model_budget_sessions WHERE session_id=%s", (session,))


async def request_response(provider, command, results=()):
    provider._begin_run(command)
    return await provider._request(
        {"max_completion_tokens": 512, "messages": [{"role": "user", "content": command.text}]}
    )
