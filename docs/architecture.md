# Architecture

The diagram and cost table are in the [README](../README.md#architecture). This page explains how the parts fit together and why they were chosen.

## Request paths

| Path | Route |
| --- | --- |
| Web app | Browser → Cloudflare DNS → CloudFront (HTTPS, ACM certificate) → private S3 bucket, read through Origin Access Control. Unknown paths return `index.html`, so client routes like `/projects` work. |
| Sign-in | Email and password, handled by the API (`/api/v1/auth`). Passwords are hashed with scrypt. Sign-in returns a 15-minute JWT access token, kept only in the page's memory and sent as `Authorization: Bearer`, plus a 30-day refresh token in an httpOnly, `SameSite=Strict` cookie that only `/api/v1/auth` receives. The database stores just a hash of each refresh token, so signing out or changing the password ends sessions at once. |
| API | Browser → `api.xiong-mao.net` (Elastic IP) → Caddy :443 → `api:8000` on the Docker network. Only ports 80 and 443 are open. PostgreSQL has no published port. |
| Answers | `POST /conversations/{id}/generations` answers with a Server-Sent Events stream. The API retrieves the top 5 document passages, sends the prompt to Gemini's `streamGenerateContent`, and relays each piece as it arrives. Caddy flushes immediately (`flush_interval -1`). |
| Uploads | The API stores the file under `/data/storage` and queues a job. The worker extracts text, splits it into 800-token pieces, embeds them with `gemini-embedding-001` (1536 dimensions) and saves the vectors in pgvector. |

## On the server

`deploy/compose.yaml` runs five containers:

| Service | Image | Notes |
| --- | --- | --- |
| `caddy` | `caddy:2` | Gets and renews the Let's Encrypt certificate (state in `/data/caddy`), adds HSTS and rejects request bodies over 12 MB. |
| `api` | ECR image | `uvicorn app.main:app`, runs as uid 10001. |
| `worker` | same image | `python -m worker.main`. Exactly one must run. |
| `migrate` | same image | `alembic upgrade head`, then exits. `api` and `worker` start only if it succeeds. |
| `db` | `pgvector/pgvector:pg16` | Data in `/data/postgres`. Password generated on the server, in `/data/postgres-password`. |

`/data` is a separate encrypted EBS volume. The first-boot script (`infra/user_data.sh.tftpl`) formats it only when it is blank, so replacing or rebuilding the server keeps every chat and document. Terraform refuses to delete it (`prevent_destroy`). Data Lifecycle Manager snapshots it daily.

## Deployment and secrets

- **No AWS keys in GitHub.** Actions gets short-lived credentials by assuming `xiongmao-github-deploy` through OpenID Connect. Only pushes to `main` of `hiimmuc/xiongmao-chat-rag` can assume it. The role may push one ECR repository, write two buckets, invalidate one distribution, and run commands only on the instance tagged `xiongmao-api`.
- **No SSH.** Deploys use SSM Run Command, and admin shells use SSM Session Manager. Both are free and go through IAM.
- **Secrets stay out of Git and Terraform state.** You add `GEMINI_API_KEY`, `KEY_ENCRYPTION_KEY` and `JWT_SECRET` as SecureString parameters. At deploy time the instance role reads `/xiongmao/prod/*` into a root-only `.env`.
- **The release order is backend, then frontend**, so a new web app never calls an API that does not have its endpoints yet. The worker is stopped before migrations so two workers never overlap.

## Why this shape

| Choice | Reason |
| --- | --- |
| One EC2 server with Docker Compose, not ECS/Fargate/ALB | An ALB alone costs more than the whole target budget. Compose runs all five containers from one short file. |
| PostgreSQL in a container, not RDS | RDS's smallest instance costs more than the server. pgvector runs in the same database, so there is no separate vector service. |
| Caddy, not an ALB or nginx + certbot | Automatic HTTPS from a short config, with correct streaming. |
| Cloudflare DNS only (no proxy) | Free DNS. The proxy is off because it would cut streamed answers after 100 s and block Caddy's certificate challenge. |
| t4g.micro (arm64) | The cheapest instance that fits, helped by 2 GiB swap. Change `instance_type` to `t4g.small` if memory gets tight. |
| Local disk for uploads, not S3 | One fewer service, and files sit next to the database on the snapshotted disk. |
| Gemini for chat and embeddings | One provider key covers everything. OpenAI remains supported as an option. |

## Known limits

- Single server: a reboot or failure is downtime until it is back (usually about a minute; see [operations](operations.md)).
- One worker: a job that is mid-way when the worker crashes stays in `processing` until an operator steps in. Paid calls are never replayed automatically.
- The deletion journal is now on the same disk as the database. Restoring an older snapshot therefore also brings back data deleted after that snapshot. Re-run those deletions after a restore.
