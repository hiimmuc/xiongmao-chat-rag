# Cost: how production runs for about $10 a month, and how it grows

Production costs **about $12 a month on-demand, or about $10 with a 1-year Savings Plan**. Almost all of it is the one EC2 server that runs the backend and the database. The frontend is almost free.

Prices are AWS us-east-1 list prices at the time of writing, for a month of 730 hours. Check the [AWS Pricing Calculator](https://calculator.aws/) before you decide anything. AI provider charges (Gemini) are billed by Google and are not included.

## The path at a glance

```mermaid
flowchart LR
    t0["<b>Now: ~$10–12 / month</b><br/>1 EC2: API + worker + PostgreSQL<br/>S3 + CloudFront frontend<br/>GitHub Actions"]
    t1["<b>Comfortable budget: ~$45 / month</b><br/>EC2: API + worker<br/>RDS PostgreSQL<br/>Amplify frontend<br/>S3 for uploads"]
    t2["<b>High traffic: ~$250+ / month</b><br/>Load balancer + several EC2<br/>many API containers<br/>RDS Multi-AZ, Redis<br/>Amplify, S3"]
    t0 -- "need managed backups,<br/>less ops work" --> t1
    t1 -- "many customers,<br/>no single point of failure" --> t2
```

```mermaid
xychart-beta
    title "Approximate AWS cost per month (USD)"
    x-axis ["Now", "Comfortable budget", "High traffic"]
    y-axis "USD / month" 0 --> 280
    bar [12, 45, 250]
```

## Now: where the ~$12 goes

```mermaid
pie showData
    title Production, USD per month (on-demand)
    "EC2 t4g.micro (backend + database)" : 6.13
    "Public IPv4 address" : 3.65
    "EBS disks (system + data)" : 1.60
    "Data disk snapshots" : 0.30
    "S3, CloudFront, ECR, SSM" : 0.20
```

```mermaid
flowchart LR
    browser([Browser])
    subgraph frontend["Frontend · ~$0.20"]
        cf[CloudFront] --> s3[(S3<br/>React build)]
    end
    subgraph server["Backend · ~$11.70 · one EC2 t4g.micro"]
        caddy[Caddy] --> api[API container]
        worker[Worker container]
        api --> db[(PostgreSQL container)]
        worker --> db
        db --- disk[(EBS data disk<br/>daily snapshots)]
    end
    gh["GitHub Actions<br/>CI/CD · $0"]
    browser --> cf
    browser --> caddy
    gh -. deploys .-> server
    gh -. deploys .-> frontend
```

| Item | What it is | USD / month |
| --- | --- | --- |
| EC2 t4g.micro | 2 vCPU (burstable), 1 GiB memory + 2 GiB swap, Graviton (arm64). Runs Caddy, the API, the worker and PostgreSQL as Docker containers. | 6.13 |
| Public IPv4 address | The Elastic IP for `api.xiong-mao.net`. AWS bills every public IPv4 address. | 3.65 |
| EBS gp3 | 10 GiB system disk + 10 GiB data disk (database, uploads, certificates) | 1.60 |
| Snapshots | 7 daily snapshots of the data disk, incremental | ~0.30 |
| S3 + CloudFront | The web app is a few MB of static files. CloudFront's always-free tier covers 1 TB of transfer and 10 million requests a month. | ~0.05 |
| ECR | Last 5 API images | ~0.10 |
| SSM, Data Lifecycle Manager, ACM, IAM | Parameter Store (standard), Run Command, Session Manager, snapshot scheduling, the frontend certificate | 0 |
| **Total, on-demand** | | **~12** |
| **Total, 1-year Compute Savings Plan** (no upfront) | The plan lowers the EC2 price; everything else stays the same | **~10** |

## The choices that keep it low

```mermaid
flowchart TB
    subgraph used["What production uses · ~$12"]
        u1[PostgreSQL in a container]
        u2[Caddy on the server]
        u3[Public subnet,<br/>only ports 80 / 443]
        u4[Docker Compose on 1 EC2]
        u5[SSM Parameter Store]
        u6[Cloudflare DNS]
        u7[GitHub Actions]
    end
    subgraph avoided["Avoided services · would add ~$90+"]
        a1["RDS PostgreSQL<br/>+$14 to +$26"]
        a2["Application Load Balancer<br/>+$16 to +$25"]
        a3["NAT gateway<br/>+$33"]
        a4["ECS on Fargate<br/>+$14 per task"]
        a5["Secrets Manager<br/>+$1.20"]
        a6["Route 53 hosted zone<br/>+$0.50"]
        a7["CodePipeline + CodeBuild<br/>+$1 and up"]
    end
    u1 -. instead of .-> a1
    u2 -. instead of .-> a2
    u3 -. instead of .-> a3
    u4 -. instead of .-> a4
    u5 -. instead of .-> a5
    u6 -. instead of .-> a6
    u7 -. instead of .-> a7
```

| Choice | Instead of | Saves per month | Trade-off |
| --- | --- | --- | --- |
| **PostgreSQL as a container on the same EC2 server**, with pgvector in the same database | RDS PostgreSQL (db.t4g.micro ~$12 + storage, or db.t4g.small ~$23) plus a separate vector database | ~$14–26 | Backups are disk snapshots, not point-in-time restore. Upgrades are done by us. |
| **Caddy** for HTTPS, with free Let's Encrypt certificates | Application Load Balancer | ~$16–25 | No load balancing, which one server doesn't need. |
| **Public subnet** with a firewall that allows only 80/443 | Private subnet + NAT gateway | ~$33 | The server has a public address, but nothing else is exposed and there is no SSH. |
| **Docker Compose on one server** | ECS on Fargate (one task with 0.5 vCPU and 1 GB is ~$14) | ~$14 per container | One server is one point of failure. |
| **Graviton t4g.micro** with standard CPU credits | x86 t3.micro, or unlimited credits | ~$1.50, and no surprise CPU bills | 1 GiB of memory, helped by 2 GiB of swap |
| **S3 + CloudFront** for the web app | A web server, or Amplify Hosting | ~$1–5 | We wire it up ourselves in Terraform. |
| **SSM Parameter Store** (standard tier) | Secrets Manager ($0.40 per secret) | ~$1.20 | No automatic secret rotation |
| **SSM Session Manager + Run Command** | A bastion host, SSH keys, or a VPN | ~$4+ | None: it is also more secure. |
| **Cloudflare DNS** (free) | Route 53 | $0.50 + queries | DNS lives outside AWS. |
| **GitHub Actions** for CI/CD | CodePipeline + CodeBuild | ~$1 and up | None |
| **ECR keeps 5 images; 7 snapshots** | Keeping everything | Stops storage growing forever | Older releases can't be rolled back to. |

**GitHub Actions is free here:** public repositories get unlimited minutes. Private repositories on the Free plan get 2,000 minutes a month. One deploy uses roughly 15–20 runner minutes (tests, the arm64 image build, the frontend upload), so about 100 deploys a month fit.

## With a comfortable budget: managed database, easy frontend (~$45 / month)

When paying more is fine and the goal is less operations work, move the database to a managed service and the frontend to a managed host. The backend stays on one EC2 server.

```mermaid
flowchart LR
    browser([Browser])
    amplify["Amplify Hosting<br/>frontend: build, CDN, HTTPS"]
    subgraph vpc[VPC]
        subgraph ec2["EC2 t4g.small · Docker Compose"]
            caddy[Caddy] --> api[API container]
            worker[Worker container]
        end
        rds[("RDS PostgreSQL<br/>+ pgvector<br/>automated backups")]
    end
    s3[("S3<br/>uploaded files")]
    gh[GitHub] -- "push to main" --> amplify
    gh -- "GitHub Actions:<br/>backend deploy" --> ec2
    browser --> amplify
    browser --> caddy
    api --> rds
    worker --> rds
    api --> s3
    worker --> s3
```

| Item | USD / month |
| --- | --- |
| EC2 t4g.small (2 GiB): API + worker containers + Caddy | 12.26 |
| Public IPv4 address | 3.65 |
| EBS gp3 10 GiB (system only; no data disk needed) | 0.80 |
| RDS PostgreSQL db.t4g.small, Single-AZ, 20 GiB gp3, 7-day automated backups | ~25.70 |
| S3 for uploads (a few GB) | ~0.50 |
| Amplify Hosting (builds, storage, transfer for a small app) | ~1–5 |
| ECR, SSM | ~0.20 |
| **Total** | **~$45** |

What each change buys:

| Change | Benefit |
| --- | --- |
| **RDS PostgreSQL** (supports pgvector) | Automated backups with point-in-time restore to any second in the last 7 days, managed minor upgrades, and a one-click switch to Multi-AZ later. There is no data disk to look after. |
| **Amplify Hosting** for the frontend | Connects to the GitHub repository, then builds and hosts the app with CDN and HTTPS. Pull requests can get preview sites. It replaces the S3 bucket, CloudFront, ACM and their Terraform. |
| **S3 for uploads** | The EC2 server holds no data, so it can be replaced at any time. This is also the first step towards several servers. |
| **t4g.small** | Twice the memory. PostgreSQL has moved off the server, so the API and worker get it all. |

Changes needed in this repository:

1. `backend/app/core/storage.py`: store uploads and the deletion journal in S3 instead of on disk. The API and worker get an IAM role for that bucket.
2. `deploy/compose.yaml`: remove the `db` service. `DATABASE_URL` points to the RDS endpoint, and the password goes into Parameter Store.
3. `infra/`: add RDS (in private subnets that only the server's security group can reach), the uploads bucket and an Amplify app. Remove the data disk, `frontend.tf`, and the frontend job in `deploy.yml`.
4. Move the existing data once: `pg_dump` from the container, `pg_restore` into RDS, and copy `/data/storage` to S3.

## With many customers: scale out (~$250+ / month)

For lots of traffic, run several API containers on several servers behind a load balancer, so one failure does not take the app down. The cost below is for the AWS base; traffic and the AI provider come on top, and at this size the AI provider is usually the biggest bill.

```mermaid
flowchart LR
    browser([Many browsers])
    amplify["Amplify Hosting<br/>frontend"]
    browser --> amplify
    browser --> alb
    subgraph vpc["VPC · 2 Availability Zones"]
        alb["Application Load Balancer<br/>HTTPS (ACM)"]
        subgraph asg["Auto Scaling group · ECS on EC2"]
            subgraph e1["EC2 t4g.medium · AZ a"]
                a1[API]
                a2[API]
                a3[API]
            end
            subgraph e2["EC2 t4g.medium · AZ b"]
                b1[API]
                b2[API]
                b3[API]
            end
        end
        workers["Worker containers<br/>scale with the job queue"]
        redis[("ElastiCache<br/>Redis / Valkey")]
        subgraph rds["RDS PostgreSQL Multi-AZ"]
            primary[(Primary · AZ a)] -. sync copy .-> standby[(Standby · AZ b)]
        end
    end
    s3[("S3<br/>uploads")]
    alb --> a1 & a2 & a3 & b1 & b2 & b3
    a1 & b1 --> primary
    workers --> primary
    a1 & b1 --> redis
    a1 & b1 & workers --> s3
```

| Item | USD / month |
| --- | --- |
| Application Load Balancer (base + light traffic) | ~25 |
| 2 × EC2 t4g.medium (4 GiB each) running several API containers, in an Auto Scaling group | ~49 |
| Worker capacity (1 × t4g.small to start) | ~12 |
| Public IPv4 for the instances (public subnets that only the load balancer can reach, so no NAT gateway) | ~11 |
| RDS PostgreSQL db.t4g.medium **Multi-AZ**, 100 GiB gp3 | ~118 |
| ElastiCache (cache.t4g.micro): shared rate limits and caches | ~10 |
| Amplify + S3 at higher traffic | ~10–30 |
| **Total base** | **~$250**, then add more instances as traffic grows |

How it scales:

| Part | How it grows |
| --- | --- |
| API | ECS runs many API containers on each EC2 server, and the Auto Scaling group adds servers on CPU or request count. The load balancer spreads traffic and drops unhealthy containers (`/api/v1/health/ready`). |
| Worker | More worker containers when the job queue grows. The queue already claims jobs with `FOR UPDATE SKIP LOCKED`, so two workers never take the same job. |
| Database | Multi-AZ fails over automatically. Add a read replica for heavy reads, then a bigger instance class. |
| Frontend | Amplify's CDN scales by itself. |

Changes needed in this repository, on top of the comfortable-budget ones:

1. **Shared sign-in limits:** failed sign-ins are counted in each API process's memory (`backend/app/services/auth.py`). With many containers, move the counter to Redis or the database.
2. **Worker crash recovery:** give jobs a lease, so a job left in `processing` by a crashed worker is retried automatically, without replaying a paid call. Today an operator steps in.
3. **Streaming through the load balancer:** raise the load balancer's idle timeout to about 300 seconds, so long streamed answers are never cut.
4. **Deploys:** an ECS rolling update replaces `deploy.sh`. Migrations run as a one-off task before the new containers start. GitHub Actions stays the CI/CD tool.

## Summary

| | Now | Comfortable budget | High traffic |
| --- | --- | --- | --- |
| Monthly AWS cost | **~$10–12** | **~$45** | **~$250+** |
| Backend | 1 EC2, Docker Compose | 1 EC2, Docker Compose | Load balancer + Auto Scaling, ECS on EC2 |
| Database | PostgreSQL container on the same EC2 | RDS PostgreSQL | RDS PostgreSQL Multi-AZ (+ replicas) |
| Frontend | S3 + CloudFront | Amplify Hosting | Amplify Hosting |
| Uploads | EBS data disk | S3 | S3 |
| Backups | Daily disk snapshots | Point-in-time restore | Point-in-time restore + standby |
| One server fails | App down until it's back (about a minute) | App down until it's back; data safe in RDS | No downtime |
| CI/CD | GitHub Actions (free) | GitHub Actions + Amplify | GitHub Actions |
| Best for | A small user base, lowest cost | A small team that wants less ops work | Many customers, high availability |
