# AgriMitra Backend

FastAPI farmer assistant using NVIDIA's OpenAI-compatible API and an optional
server-side data.gov.in mandi market feed. General chat uses the configured LLM;
market-price answers retrieve government records first and provide those records
as the only factual price evidence.

## Setup

The app reads the project-root `.env` and process environment variables. If the
root `.env` does not exist, copy `.env.example` to create it. If it already
exists, preserve its contents and add only the missing variables below:

- `NVIDIA_API_KEY` and `NVIDIA_MODEL` for AgriMitra chat.
- `DATA_GOV_API_KEY` from data.gov.in.
- `DATA_GOV_RESOURCE_ID` for “Current Daily Price of Various Commodities from
  Various Markets (Mandi)” (`9ef84268-d588-465a-a308-a864a43d0070`).
- `DATA_GOV_API_BASE` (default `https://api.data.gov.in/resource`) and
  `DATA_GOV_CACHE_TTL_SECONDS` (default 300 seconds) are optional overrides.
- `DATA_GOV_CONNECT_TIMEOUT_SECONDS` (default 5) and
  `DATA_GOV_READ_TIMEOUT_SECONDS` (default 15) bound provider requests.
- `NVIDIA_REQUEST_TIMEOUT_SECONDS` (default 60) bounds each model request.
- `APP_ENV=production` disables interactive API docs. The same-origin app does
  not need CORS; if the frontend is hosted separately, set
  `BACKEND_CORS_ORIGINS` to a JSON array of exact trusted origins.
- `DATABASE_URL` optionally overrides the default absolute SQLite database path.

In the root `.env`, replace the empty value in `DATA_GOV_API_KEY=` with your
data.gov.in API key. Do not add the key to frontend files or share it in chat.
The app loads the project-root `.env` and environment variables. The API key is
only sent by the backend to data.gov.in; it is never returned to the browser.
Do not commit `.env`. For Render deployment, configure the keys as server-side
environment secrets and follow the project-root `DEPLOYMENT.md` and
`render.yaml`.

From the `backend` directory, run:

```bash
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/chat.html` or `http://127.0.0.1:8000/market.html`.
The default SQLite file is resolved relative to the project, not the shell's
current directory.

## Market API

All endpoints are under `/api/v1/markets`:

- `GET /prices?commodity=Tomato&state=Maharashtra&limit=100&offset=0`
- `GET /commodities` (supports `limit` and `offset`)
- `GET /markets?state=Maharashtra&commodity=Tomato`
- `GET /trends?commodity=Tomato&days=31`

Prices accept `state`, `district`, `market`, `commodity`, `date` (either
`YYYY-MM-DD` or `DD/MM/YYYY`), `limit` (1–1000), `offset`, and `refresh=true`.
Market-related chat questions match the crop against the verified dataset
commodity list and send one filtered request, rather than first downloading an
unfiltered 1,000-record catalog. Normal latest-price questions request a small
page and pass only the latest report-date records to the model. Explicit market
comparisons use a larger source page, calculate candidate rankings server-side,
and pass only the top five current-date rows to the model. Provider and model
stage durations are logged without query text or credentials. Chat context is
limited to six recent, bounded messages; ordinary replies are capped at 512
generated tokens. The backend uses
the data.gov.in resource API's `format=json`, `limit`,
`offset`, and exact `filters[field]` parameters. It identifies itself with an
`AgriMitra/0.1` User-Agent. Provider connection timeouts default to five seconds
and read timeouts to 15 seconds. Slow read timeouts are not retried; connection
errors and upstream 5xx responses receive at most one retry. HTTP 429 is not
retried.
Response rows retain the source values and expose normalized numeric prices in
INR per quintal, source report date, source label, and application retrieval time.
No sample prices are bundled into the interface.

Successful source records are stored in the existing SQLite database table
`market_observations`. Repeated retrieval of the same commodity/market/variety/
location/report-date updates that observation instead of duplicating it.
If observation storage fails, the live verified records are still returned and
the response sets `history_saved` to `false`; the dashboard warns that trend
history may be incomplete.
Trend points are daily averages across stored modal prices matching the selected
filters. 7-day and 30-day changes are only returned when an actual stored report
exists on or before each comparison date; otherwise the change is `null`.
Historical depth therefore grows as source records are retrieved, and no
unavailable history is synthesized. API responses are cached in memory for five
minutes by default; manual refresh bypasses that cache.

Example request:

```text
GET http://127.0.0.1:8000/api/v1/markets/prices?commodity=Tomato&limit=20
```

The response schema is `{ "records": [...], "count": 0, "total": null,
"limit": 20, "offset": 0, "source": "...", "retrieved_at": "..." }`.
Each record contains `state`, `district`, `market`, `commodity`, `variety`,
`grade`, `report_date`, `min_price`, `max_price`, `modal_price`, `unit`,
`source`, `retrieved_at`, and original `source_values`. Actual values are only
returned when the government API supplies them.

An empty successful response (no matching reports) has this shape:

```json
{
  "records": [],
  "count": 0,
  "total": 0,
  "limit": 20,
  "offset": 0,
  "source": "data.gov.in — Current Daily Price of Various Commodities from Various Markets (Mandi)",
  "retrieved_at": "<application retrieval timestamp>"
}
```

The records endpoint was verified with the configured key at
`https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070`:
HTTP 200, `application/json`, and a `records` array containing fields
`state`, `district`, `market`, `commodity`, `variety`, `grade`, `arrival_date`,
`min_price`, `max_price`, and `modal_price`. Provider quotas and rate limits
remain account-specific. 429, timeout, invalid response, missing configuration,
and upstream errors are returned as non-success HTTP responses without fabricated data.

## Deployment readiness

Set `APP_ENV=production`, provide both API keys using the host's secret manager,
and set only exact trusted origins if the frontend is deployed on a separate
origin. The Render Blueprint runs a single web-service instance and stores
SQLite data on its configured persistent disk; its in-process cache is
temporary. The current project has no authentication or request-rate limiting.
Before exposing the service publicly, add the application's intended
authentication and rate limits, configure HTTPS, and monitor `/health` plus
provider/model error rates. A successful local test does not guarantee either
third-party provider will remain available.
