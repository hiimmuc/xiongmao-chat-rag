# Operations

Commands are for PowerShell on Windows, run from `infra\` unless noted, with the AWS CLI configured and `$env:AWS_REGION` set.

## Open a shell on the server

```powershell
aws ssm start-session --target (terraform output -raw server_instance_id)
```

Inside the session:

```bash
sudo -i
cd /opt/xiongmao
docker compose ps                 # what is running
docker compose logs -f api        # follow API logs (also: worker, caddy, db, migrate)
docker compose restart api
```

## Deploy

- **Normal:** push or merge to `main`. The Deploy workflow tests, ships the backend, then the frontend.
- **Re-run without a code change** (for example, after changing an SSM parameter): `gh workflow run deploy.yml`.
- **Change a setting:** edit `terraform.tfvars` and run `terraform apply` (non-secret settings), or `aws ssm put-parameter --overwrite` (secrets). Then re-run the deploy so `.env` is rebuilt.

## Roll back the backend

ECR keeps the last 5 images, tagged with their commit SHA. In a server shell:

```bash
sudo bash /opt/xiongmao/deploy.sh <ECR_REPOSITORY_URL>:<older-commit-sha>
```

Migrations only move forward. Keep them backward-compatible so an older image still works with a newer schema. For the frontend, revert the commit and push to `main`.

## Backups and restore

- Data Lifecycle Manager snapshots the data disk daily and keeps 7 (`snapshot_retention_days`).
- For an extra logical backup:

  ```bash
  docker compose exec -T db pg_dump -U chatbot chatbot | gzip > /data/backup.sql.gz
  ```

**Restore the data disk from a snapshot:**

1. In a server shell, run `docker compose down`.
2. In the EC2 console, create a volume from the snapshot in the same Availability Zone.
3. Point Terraform at the new volume:

   ```powershell
   terraform state rm aws_ebs_volume.data aws_volume_attachment.data
   terraform import aws_ebs_volume.data <new-volume-id>
   terraform apply     # replaces the server, which then mounts the restored volume
   gh workflow run deploy.yml
   ```

4. Delete the old volume yourself once everything works.

Deletions made after the snapshot was taken come back with it. Repeat them.

## Replace or resize the server

```powershell
terraform apply -replace="aws_instance.server"          # fresh Ubuntu, same data disk and IP
# or change instance_type in terraform.tfvars, then: terraform apply
gh workflow run deploy.yml                               # start the app on the new server
```

## Stuck jobs and unknown usage

Jobs left in `processing` after a worker crash are not picked up again. Check the document's usage rows first: a paid call may already have been made. Then mark the job failed and use **Retry** on the document in the app. Answers left `pending` or `streaming` after a crash should be marked `interrupted`, and their usage `unknown`. Never record unknown usage as zero.

```bash
docker compose exec db psql -U chatbot chatbot
```

## Tear down

`terraform destroy` refuses to run while the data disk is protected by `prevent_destroy`. Choose one:

- **Keep the data disk:** run `terraform state rm aws_ebs_volume.data aws_volume_attachment.data`, then `terraform destroy`.
- **Delete everything:** remove the `prevent_destroy` line from `infra/server.tf`, then `terraform destroy`.

Afterwards, delete the snapshots and the Cloudflare records yourself.
