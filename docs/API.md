# API

## GET /api/mentions/hourly

Returns hourly mention counts for the last N hours for one or more tickers.

Query params:
- tickers: comma-separated symbols (e.g., AAPL,TSLA,NVDA)
- hours: trailing hours to include (default 24)

Response:
```json
{
  "labels": ["2025-01-01T12:00:00+00:00", "2025-01-01T13:00:00+00:00", "..."],
  "series": [
    { "symbol": "AAPL", "data": [1,0,2, ...] },
    { "symbol": "TSLA", "data": [0,3,1, ...] }
  ],
  "hours": 24
}
```

Notes:
- Hours are aligned in UTC and zero-filled when counts are missing.
- Currently computed live from `article` and `article_ticker` tables.

## Rate limits

Per-IP, per-endpoint limits are enforced (60 requests per minute by default). Exceeding the limit returns HTTP 429 with a `Retry-After` header and JSON body (FastAPI wraps payload under `detail`):

```
{
  "detail": {
    "error": "Too Many Requests",
    "retry_after": 42
  }
}
```

Limits can be adjusted via settings.

## Parameter caps

To protect service stability, the following caps apply:
- Articles list `limit` ≤ 100
- Tickers list `limit` ≤ 100
- Sentiment time-series `days` ≤ 90
- Mentions hourly `hours` ≤ 168
- Maximum offset (page × limit) ≤ 5000

Oversized values are rejected by validation (422) or return a 400 when maximum offset is exceeded.

