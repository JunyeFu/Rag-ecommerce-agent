# Connectors

Provider adapters implement reviewed contracts and deterministic fixtures.
Live marketplace credentials and traffic are external gates.

`GowuDemoPriceClient` is an optional read-only sandbox adapter. Its prices are
always `THIRD_PARTY_DEMO`: useful for a small external-data demonstration, but
never LIVE evidence and never a substitute for the project-authored 60-SKU RAG
catalog. Run one explicit check with:

```powershell
$application = Invoke-RestMethod -Method Post "https://api.gowu-ai.com/open/access-clients/apply"
$env:GOWU_DEMO_APP_KEY = $application.appKey
uv run python scripts/check_gowu_demo_prices.py "降噪耳机"
```

Apply once per demo session. The client performs one search request and does
not retry, persist the key, or fall back to fixtures.
