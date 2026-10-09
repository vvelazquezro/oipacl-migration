# Akamai Configuration Management Tool

A Flask web application for automating the auditing, migration, and activation of Akamai property configurations through the **Property Manager API (PAPI)**. It allows you to bulk update security and performance behaviors (such as SiteShield, Origin IP ACL, Tiered Distribution, and SureRoute) and generate compliance reports across your Akamai account.

Each Audit/Migrate/Activate submission runs as an isolated background job with a live streaming log and a downloadable result CSV. Credentials are entered per-session in the browser and are never persisted.

---

## Features

- **Comprehensive Auditing** — Scan a list of properties to report on the status of Origin IP ACL, Tiered Distribution, SiteShield, and SureRoute configurations.
- **Automated Migrations** — Safely evaluate and update rule trees to replace SiteShield with modern standards in a single pass.
- **Smart Fallback Resolution** — Automatically resolves properties by `propertyName`, `hostname`, or `edgeHostname` to minimize API miss rates.
- **Bulk Activation** — Seamlessly activate updated property versions to staging or production environments.
- **Concurrent, isolated jobs** — Multiple users can run jobs at the same time; each job gets its own credentials, log stream, and result files.

---

## Prerequisites

- Python 3.11+
- Akamai EdgeGrid API credentials (host, client token, client secret, access token) and an account switch key — entered in the browser per job, not stored in this repo.

---

## Project Structure

```
├── app.py            # WSGI entry point (flask run / gunicorn)
├── webapp/            # Flask web UI: routes, forms, background jobs, templates
├── akamai_core/        # Shared PAPI logic: API client, rule-tree transforms, audit/migrate/activate
├── AkamaiRequests.py    # Internal Akamai API wrapper library (do not distribute externally)
└── requirements.txt     # Python dependencies
```

---

## Running Locally

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
FLASK_SECRET_KEY=dev APP_ROOT_PATH=/ss-migrator python3 app.py
# visit http://localhost:8080/ss-migrator/
```

The app listens on plain HTTP port `8080` and must be reachable under `APP_ROOT_PATH` (a reverse proxy is expected to forward the full path, including the prefix, without stripping it).

---

## Using the App

1. On first visit, a **Connect to Akamai** dialog pops up asking for your EdgeGrid credentials (host, client token, client secret, access token) and account switch key. Submit once per browser session — a header pill shows "Ready to use" once both credentials and an account switch key are set, with **Change credentials** / **Disconnect** actions available any time. Audit, Migrate, and Activate are unavailable until the pill reads "Ready to use".
2. Choose **Audit**, **Migrate**, or **Activate**.
3. Provide the property list, either by uploading a CSV (first column, header row ignored) or pasting names/hostnames (one per line). Activation expects `name,version` rows instead.
4. Submit. You'll be redirected to a job page showing a progress bar and a friendly status message as properties are processed.
5. Toggle **Show advanced mode** to reveal the raw, terminal-style streaming log (useful for troubleshooting a specific property).
6. When the job finishes, a summary (e.g. counts migrated/skipped/failed) and download link(s) for the result CSV appear:
   - **Audit** → `audit_results.csv` (Property Name, Version, OIPACL, Tiered Distribution, SiteShield, SureRoute Type)
   - **Migrate** → `migrated_properties_<accountKey>.csv` (always auto-downloaded; successfully migrated versions), `migration_skipped.csv` (properties that needed no changes), and `migration_errors.csv` (actual failures with reasons). Migrating never activates on its own — a **Proceed to Deploy →** button (next to **← Back to Migrate options**) carries the migrated list forward into the Activate form. A collapsible **Go to Properties** list also links each migrated property straight to its Control Center config page.
   - **Activate** → `activation_results.csv` (Configuration name, version, Network, Status/error). Network can be Staging, Production, or Both; activating to Production or Both requires a Peer Reviewer email and a Pull Request link (appended to the activation comments).

---

## Credentials & Security

- Credentials are submitted once per browser session through the connect dialog and held only in server memory (never written to disk), referenced by a random id.
- That reference id is the *only* thing stored in the browser, inside Flask's session cookie — which is HMAC-signed (via itsdangerous) using `FLASK_SECRET_KEY`, so it cannot be read or forged client-side. The secret key itself lives in `.env` (gitignored), never in code.
- Both the credential reference and each job's own temporary `.edgerc`-style file expire automatically (`CREDENTIAL_TTL_SECONDS`, default 1 hour).
- Forms are CSRF-protected; uploads are limited by size and validated by file type.
- Jobs run in a bounded background thread pool so multiple users can work concurrently without one job blocking another.

---

## Environment Variables

Copy `.env.example` to `.env` and fill in real values for local runs (`.env` is gitignored).

| Variable | Sensitive? | Description |
|---|---|---|
| `APP_ROOT_PATH` | No | Sub-path the app is mounted under (e.g. `/ss-migrator`). Empty/unset serves from `/`. |
| `FLASK_SECRET_KEY` | **Yes (secret)** | Signs the session cookie (HMAC via itsdangerous) and CSRF tokens. Required in production; an ephemeral key is generated with a warning if omitted. |
| `SESSION_COOKIE_SECURE` | No | Set to `false` only for local plain-HTTP testing; defaults to `true`. |
| `MAX_CONCURRENT_JOBS` | No | Max number of Audit/Migrate/Activate jobs run in parallel (default `5`). |
| `MAX_PROPERTIES_PER_JOB` | No | Max property rows accepted per job submission (default `1000`). |
| `CREDENTIAL_TTL_SECONDS` | No | How long a connected session's credentials stay in server memory before expiring (default `3600`). |

No Akamai credentials are supplied via environment variables — they are entered once per session through the connect dialog.

---

## Support

For issues related to:

- **Akamai APIs** — Check Akamai's official Property Manager API documentation.
- **EdgeGrid Setup** — Refer to Akamai's EdgeGrid documentation.
