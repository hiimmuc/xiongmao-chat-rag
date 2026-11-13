# Gehihi (xiong-mao.net)

Private AI chat over your own documents. Upload PDFs, text or Markdown files into a project, ask questions, and get streamed answers from Gemini that cite the file, page and passage they come from.

| **Component** | **Technology Stack** |
| --- | --- |
| **Frontend** | React + TypeScript (Vite) |
| **Backend** | FastAPI API + one background worker, Python 3.12 |
| **Database** | PostgreSQL 16 with pgvector (chats, accounts and document vectors in one place) |
| **AI** | Gemini for chat and embeddings; OpenAI optional |
| **Hosting** | AWS (production) and one GCP VM (staging), both deployed by GitHub Actions |

## How it fits together

```mermaid
flowchart LR
    user([Browser])
    subgraph web[Web app]
        react[React build]
    end
    subgraph server[One server, Docker Compose]
        caddy[Caddy<br/>HTTPS]
        api[FastAPI API]
        worker[Worker]
        db[(PostgreSQL<br/>+ pgvector)]
    end
    gemini[Gemini API]

    user --> react
    user -- "REST + streamed answers" --> caddy --> api
    api --> db
    worker --> db
    api -- chat --> gemini
    worker -- embeddings --> gemini
```

Every environment runs the same API image and the same `deploy/compose.yaml`. Only where the web app is served and where the settings come from change:

| | Local | Staging (GCP) | Production (AWS) |
| --- | --- | --- | --- |
| Deploys from | `./scripts/start-local.sh` (Windows: `.\scripts\start-local.ps1`) | push to `staging` | push to `main` |
| Web app | Vite dev server, `localhost:5173` | Caddy on the VM, same domain as the API | S3 + CloudFront, `xiong-mao.net` |
| API | `127.0.0.1:8000` | `https://<domain>/api` | `https://api.xiong-mao.net` |
| Database | project-local PostgreSQL in `.local-postgres/` | container, data in `/data` on the VM | container, data on a separate EBS disk |
| Settings | `.env` | GitHub environment `staging` | SSM Parameter Store |
| Guide | [Run locally](#run-locally) | [docs/staging-gcp.md](docs/staging-gcp.md) | [docs/deploy-aws.md](docs/deploy-aws.md) |

## Documentation

| Read this | When you want to |
| --- | --- |
| [docs/architecture.md](docs/architecture.md) | Understand production: request paths, the server, security, costs and why it is built this way |
| [docs/security.md](docs/security.md) | See how the app and its data are protected, what to do after an attack, and protections left out for budget |
| [docs/cost.md](docs/cost.md) | See how production runs for about $10 a month, and how the setup grows with budget and traffic |
| [docs/deploy-aws.md](docs/deploy-aws.md) | Set up production on AWS from scratch, or understand how a deploy works |
| [docs/staging-gcp.md](docs/staging-gcp.md) | Set up or run the staging VM on GCP |
| [docs/operations.md](docs/operations.md) | Run production: shell access, rollback, backups, restore, resize, tear down |
| [docs/configuration.md](docs/configuration.md) | Look up a setting and where each environment gets it |
| [backend/README.md](backend/README.md) | Find your way around the backend code and add a feature |
| [frontend/README.md](frontend/README.md) | Find your way around the web app code |

## Run locally

Local mode needs no cloud account and no Docker. The database is a project-local PostgreSQL with pgvector (the `pgserver` Python package) in `.local-postgres/`, and uploads go to `.local-storage/`. A PostgreSQL already installed on the machine is not touched.

### Linux and macOS

**1. Install the tools** once: Python 3.12 and Node.js 20 or newer. With [uv](https://docs.astral.sh/uv/), `uv venv --python 3.12` fetches Python 3.12 for you. On macOS, `brew install uv node` is enough. The commands work in bash and zsh. On Windows they also work in WSL and Git Bash, as an alternative to the PowerShell section below.

**2. Install dependencies** from the repository root:

```bash
uv venv --python 3.12 backend/.venv      # or: python3.12 -m venv backend/.venv
uv pip install --python backend/.venv/bin/python -r backend/requirements.lock   # or: backend/.venv/bin/pip install -r ...
uv pip install --python backend/.venv/bin/python -e "backend[test,local]"
(cd frontend && npm ci)
cp .env.example .env      # then put your GEMINI_API_KEY in .env
```

**3. Start and stop**

```bash
./scripts/start-local.sh --paid-calls   # --paid-calls lets the app call the AI provider with your key (costs money)
./scripts/stop-local.sh
```

`start-local.sh` starts the database, applies migrations, then runs three background processes. Their logs are in `.local-run/`.

| Process | Address |
| --- | --- |
| API | <http://127.0.0.1:8000> (interactive docs at `/api/docs`, local only) |
| Worker | none (indexes uploads in the background) |
| Web app | **<http://localhost:5173>** |

Create an account on the sign-in page. Without `--paid-calls` the app runs, but no model is offered. To start over with an empty database, stop everything and delete `.local-postgres/`.

**Browse the database** with `psql`, pgAdmin or DBeaver. On Linux and macOS PostgreSQL listens on a Unix socket only. Print the connection URL, which includes the socket directory in `?host=`:

```bash
backend/.venv/bin/python scripts/local_db.py start
```

**4. Tests** (the same checks CI runs)

```bash
export DATABASE_URL=$(backend/.venv/bin/python scripts/local_db.py start | sed 's#/chatbot?#/chatbot_test?#')   # tests use their own database
cd backend
.venv/bin/python -m pytest            # database tests are skipped if DATABASE_URL is unset
.venv/bin/ruff check app worker migrations tests
cd ../frontend
npm test && npm run build
npx playwright install chromium && npm run test:e2e   # uses a mocked API
```

### Windows

**1. Install the tools** (once, in PowerShell):

```powershell
winget install Python.Python.3.12
winget install OpenJS.NodeJS.LTS
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned   # allow the local .ps1 scripts
```

**2. Install dependencies** (from the repository folder):

```powershell
py -3.12 -m venv backend\.venv
backend\.venv\Scripts\python -m pip install -r backend\requirements.lock
backend\.venv\Scripts\python -m pip install -e "backend[test,local]"
cd frontend; npm ci; cd ..
Copy-Item .env.example .env      # then put your GEMINI_API_KEY in .env
```

**3. Start and stop**

```powershell
.\scripts\start-local.ps1 -PaidCalls
.\scripts\stop-local.ps1
```

This opens three PowerShell windows (API, worker, web app) at the same addresses as above. To browse the database, connect to host `127.0.0.1`, port `55432`, user `postgres`, no password, database `chatbot`. It accepts connections only from this machine.

**4. Tests**

```powershell
$url = backend\.venv\Scripts\python scripts\local_db.py start
cd backend
$env:DATABASE_URL = $url -replace '/chatbot$', '/chatbot_test'
.venv\Scripts\python -m pytest
.venv\Scripts\ruff check app worker migrations tests
cd ..\frontend
npm test; npm run build
npx playwright install chromium; npm run test:e2e
```

## Branches and CI/CD

Each deploy branch owns one environment:

```mermaid
flowchart LR
    other[any other branch<br/>or pull request] -- "tests only" --> ci[CI]
    staging[staging branch] -- "tests, then deploy" --> gcp[GCP VM<br/>staging]
    main[main branch] -- "tests, then deploy" --> aws[AWS<br/>production]
```

| Workflow | Runs on | Does |
| --- | --- | --- |
| `ci.yml` | pull requests and pushes to any other branch | ruff, migrations + `alembic check`, pytest on PostgreSQL, unit tests, production build, Playwright, Terraform validation |
| `staging.yml` | push to `staging` | `ci.yml`, then deploys to the GCP VM over SSH |
| `deploy.yml` | push to `main` | `ci.yml`, then deploys the backend to EC2 and the web app to S3/CloudFront |

A deploy only starts if every test passes.

## Repository layout

```
backend/            FastAPI app, worker, Alembic migrations, tests        -> backend/README.md
frontend/           React + TypeScript web app, unit and Playwright tests -> frontend/README.md
deploy/             What runs on a server: compose.yaml, Caddyfile, deploy.sh
deploy/staging/     GCP staging additions: Caddy also serves the web app, setup-vm.sh, deploy.sh
infra/              Terraform for AWS: network, EC2, S3, CloudFront, ACM, ECR, IAM, SSM
scripts/            start-local.sh/.ps1, stop-local.sh/.ps1, local_db.py for local development
.github/workflows/  ci.yml, staging.yml, deploy.yml
Dockerfile          The API and worker image (one image, two commands)
```

## Features

| Area | What it does |
| --- | --- |
| Chat | Streamed answers, stop, copy, regenerate, branch from any answer, safe Markdown, title search, rename, delete. Tokens and estimated cost under each answer. |
| Projects | Each project has its own documents, chats and search index. Nothing crosses projects. |
| Free chats | Chats outside any project; they use only documents uploaded into that chat. |
| Documents | Text PDF, TXT and Markdown up to 10 MiB and 100 pages, by button or drag and drop. Status, retry, rename, download, delete. Citations show file, page and snippet. |
| Models | The picker lists the chat models each provider offers for the key in use. Settings, Models selects which appear (select all or deselect all per provider family). New accounts start with GPT-4o, GPT-4.1, GPT-4.1 mini, Gemini 3.1 Flash-Lite, Gemini 3.5 Flash-Lite and Gemini 3.6 Flash. |
| Usage | Requests, tokens and estimated cost by day and by model, in your time zone. Unknown values stay unknown. |
| Settings | Light/dark/system mode, color themes, fonts, response styles, model shortlist, personal API keys. |
| Accounts | Email and password sign-up and sign-in, password change (signs out other browsers), profile, account deletion confirmed by password. |

## Limits

- One server, one worker. If the server is down, the app is down. Recovery is in [operations](docs/operations.md).
- Per user: 10 answers a minute, 100 a day, 2 at a time, 100 files, 100 MiB. These are safeguards, not a spending cap.
- Sign-in: 5 wrong passwords lock that email for 15 minutes (20 per IP address). No email verification or emailed password reset yet.
- Documents: no OCR, so scanned PDFs are rejected. Gemini does not report embedding token counts, so indexing cost shows as unknown.
- Failures: no automatic provider retry, and no worker takeover after a crash (paid calls are never replayed on their own).
- Deletion: deleted content is hidden at once and purged by the worker. Copies already sent to Gemini follow Google's retention terms.
