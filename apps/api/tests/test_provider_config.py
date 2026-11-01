from ragcommerce_api.provider_config import configured_provider


def test_real_demo_profile_matches_acceptance(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER_MODE", "openai_compatible")
    monkeypatch.setenv("OPENAI_COMPATIBLE_BASE_URL", "https://model.example/v1")
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "test-only")
    monkeypatch.setenv("OPENAI_COMPATIBLE_MODEL", "test-model")
    monkeypatch.setenv("DATABASE_URL", "postgresql://localdev@127.0.0.1:5433/ragcommerce")
    monkeypatch.setenv("MODEL_BUDGET_SESSION", "unit-config-only-no-connection")
    provider = configured_provider()
    assert provider.timeout_seconds == 180
    assert provider.max_total_tokens == 48_000
