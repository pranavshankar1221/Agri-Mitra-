# Deploy AgriMitra on Render

AgriMitra serves its frontend and FastAPI API from one process, so deploy it as
one Render web service. The root-level `render.yaml` is a Render Blueprint:
it installs the direct Python dependencies from the root `requirements.txt`,
starts Uvicorn on Render's assigned port, and uses `/health` as its health check.

The root `requirements.txt` lists the direct runtime dependencies from
`backend/pyproject.toml`. `pip` resolves and installs their transitive
dependencies automatically. Keep both files in sync when changing the
project's direct runtime dependencies. The fully resolved `backend/uv.lock`
remains available for reproducible local installs.

## Before pushing to GitHub

1. Confirm `.env` contains your local secrets and remains untracked. Never add
   API keys to GitHub, frontend files, or `render.yaml`.
2. From the project root, review what Git would include:

   ```bash
   git status --short
   git check-ignore .env backend/.venv backend/agrimitra.db
   ```

3. Create a new empty GitHub repository without a README, license, or
   `.gitignore`, then from this folder:

   ```bash
   git add .
   git status
   git commit -m "Prepare AgriMitra for Render"
   git branch -M main
   git remote add origin https://github.com/<your-account>/<your-repository>.git
   git push -u origin main
   ```

   Check `git status` before committing. The root `.gitignore` excludes `.env`,
   Python virtual environments, generated Python files, and local SQLite
   databases. If a secret was ever committed in the past, remove it from Git
   history and rotate it; adding `.gitignore` does not remove an existing
   tracked secret.

## Create the Render service

1. Sign in to Render and choose **New > Blueprint**.
2. Connect the GitHub repository you pushed above and select its `main` branch.
3. Keep the service **Root Directory** at the repository root (`.` or blank),
   not `backend`. The Blueprint sets `rootDir: .`; the root contains
   `requirements.txt` and `render.yaml`.
4. Render reads the root `render.yaml`. During the initial Blueprint setup,
   provide values for `NVIDIA_API_KEY` and `DATA_GOV_API_KEY` in Render's
   environment-variable prompt. Enter the keys directly in Render; do not put
   them in the YAML file or GitHub. For later Blueprint updates, add new secrets
   in the service's **Environment** settings because `sync: false` values are
   not prompted again.
5. Confirm the service is created with a persistent disk mounted at
   `/var/data`, then wait for the deploy to finish.
6. Open the Render service URL. Confirm `/health` returns
   `{"status":"ok","environment":"production"}`, then check `/`, `/chat.html`,
   and `/market.html`.

## Fix an existing failed web service

The Render log shown for AgriMitra has the Uvicorn launch command under **Running
build command**, followed by `uvicorn: command not found`. In that service's
**Settings > Build & Deploy**, set:

- **Root Directory:** blank (repository root) or `.`, never `backend`.
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `cd backend && uvicorn app.main:app --host 0.0.0.0 --port $PORT`

Save the settings and redeploy the latest commit. The command that installs
dependencies must run during the build; the command that launches Uvicorn must
run only after that, as the start command. If the service is managed by a
Blueprint, push the updated root `render.yaml` and redeploy/sync the Blueprint
instead of leaving old dashboard command overrides in place.

The Blueprint uses a paid `starter` web service because Render persistent disks
are available only to paid services. The disk stores
`/var/data/agrimitra.db`, including the observed market history used for trend
calculations. The service is intentionally configured as a single instance:
Render does not support scaling a service with an attached persistent disk.

If you choose a free web service instead, remove the `disk` block and change
`DATABASE_URL` to a SQLite file path such as `sqlite:////tmp/agrimitra.db`.
That option is for a temporary demo only: database history is on ephemeral
storage and can be lost on restarts or deploys. In-process cache contents are
also temporary and are not shared between instances.

## Environment variables

The Blueprint sets these non-secret application values:

| Variable | Render value |
| --- | --- |
| `APP_ENV` | `production` |
| `DATABASE_URL` | `sqlite:////var/data/agrimitra.db` |
| `NVIDIA_MODEL` | `nvidia/nemotron-3.5-lightning-30b-a3b` |
| `OPENAI_API_BASE` | `https://integrate.api.nvidia.com/v1` |
| `NVIDIA_REQUEST_TIMEOUT_SECONDS` | `60` |
| `DATA_GOV_RESOURCE_ID` | `9ef84268-d588-465a-a308-a864a43d0070` |
| `DATA_GOV_API_BASE` | `https://api.data.gov.in/resource` |
| `DATA_GOV_CACHE_TTL_SECONDS` | `300` |
| `DATA_GOV_CONNECT_TIMEOUT_SECONDS` | `5` |
| `DATA_GOV_READ_TIMEOUT_SECONDS` | `15` |

Set the two secrets in Render's environment settings:

- `NVIDIA_API_KEY`: the NVIDIA API key used by the chatbot.
- `DATA_GOV_API_KEY`: the data.gov.in API key used by the mandi-price feature.

Do not set `BACKEND_CORS_ORIGINS` for this single-origin deployment. Set it only
if the frontend is later hosted on a separate origin, using a JSON array of
exact trusted origins.

## After deployment

- Test an ordinary question at `/chat.html` and a price lookup at `/market.html`.
- Check Render logs for startup errors, HTTP failures, and provider/model
  timeouts. Never paste secret values into logs, issues, or support requests.
- Confirm a successful market lookup sets `history_saved` to true before relying
  on newly collected data for historical trends.
- Keep provider keys in Render's secret environment settings and rotate any key
  that was exposed.

The deployment does not add authentication or request-rate limiting. The
application should not be treated as production-ready for unrestricted public
use until those controls, monitoring, and an operational backup/recovery plan
are in place. Third-party model and government API availability and quotas are
outside the application's control.
