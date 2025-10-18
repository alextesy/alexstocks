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

