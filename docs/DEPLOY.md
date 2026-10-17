# Running and deploying Bedrock

Bedrock is one container: FalkorDB (the graph database, rules 2/3/4) plus the audit web app. The graph is
restored from a published snapshot at start-up, so nothing needs to be downloaded or rebuilt.

## Try it (judges): one command

```bash
docker compose --profile demo up --build app
```

Open http://127.0.0.1:8765. The first start takes about a minute (the image builds, then the snapshot loads;
`/api/health` answers 503 "not ready" until it is in place). The plain graph audit works with no keys.
To enable the AI agent, put `GROQ_API_KEY=...` (a free Groq key) in a `.env` file next to `docker-compose.yml`.

## What the snapshot is

`deploy/bedrock_slim.rdb.gz` (17 MB) is a Redis `DUMP` of the **slim audit graph**: `Paper` nodes, `CITES` edges
between papers held in the corpus, and `Venue` nodes. It holds no author data at all (rule 6: authors were hashed
in the pipeline and are not part of this graph). `deploy/bedrock_slim.rdb.manifest.json` records its SHA-256,
node/edge counts and the FalkorDB module version (`42201`); `scripts/snapshot.py restore` refuses a file whose
checksum differs.

The slim graph was proven equivalent to the full 2.5 M-node build for the audit: `scripts/verify_slim_graph.py`
compared complete audit results for 2,501 DOIs on both graphs with 0 mismatches
(`docs/DECISIONS.md`, 2026-10-15). Retraction data is Retraction Watch via Crossref (snapshot date in
`deploy/retraction_watch.meta.json`); citations are from OpenAlex (CC0).

`DUMP` payloads only load into a compatible FalkorDB version, which is why the Dockerfile pins the base image by
digest. To rebuild from raw data instead, follow the pipeline in the README (`pull_*` then `load_graph.py --audit-only`)
and export with `python scripts/snapshot.py export`.

## Public demo hosting

The container reads `PORT` and, with `BEDROCK_PUBLIC=1` (the Dockerfile default), enables rate limits:

| Variable | Default | Meaning |
|---|---|---|
| `BEDROCK_AUDIT_PER_IP_HOUR` | 120 | audit/approve requests per visitor per hour |
| `BEDROCK_AGENT_PER_IP_HOUR` | 6 | AI-agent runs per visitor per hour |
| `BEDROCK_AGENT_PER_DAY` | 100 | AI-agent runs for everyone per day (protects the free Groq quota) |

When an agent budget is used up the app falls back to the plain graph audit (same findings, no model tokens).
Behind a proxy the visitor address is the last `X-Forwarded-For` entry. Limits are in memory and reset on restart.
Set `GROQ_API_KEY` as a host environment variable, never in the repository. Redis listens on 127.0.0.1 inside the
container; only the web port is exposed.

Memory: the loaded slim graph is about 138 MB, so the container needs roughly 300-400 MB in total.

## Local development without the app container

```bash
docker compose up -d falkordb        # FalkorDB on 127.0.0.1:6379
python scripts/serve.py              # http://127.0.0.1:8765
```

## Older approach: the demo from the author's PC (not in use)

The live demo is the app container on the author's PC behind a free Cloudflare quick tunnel, whose address can change or be dropped.
`scripts/tunnel_watchdog.py` checks every minute: if the app is down it starts Docker Desktop and the `bedrock-live` container; if the public
address stops answering it starts a new tunnel, writes the address into `site/index.html` and redeploys the product page. The product page is
the stable address to share. A single-instance lock (local port 47831) stops two copies running.

It runs as the Windows scheduled task `BedrockWatchdog` (trigger: at logon; no time limit; runs on battery). To (re)create or remove it:

```powershell
# create (adjust the repo path)
$root = "C:\path\to\bedrock"; $me = whoami
Register-ScheduledTask -TaskName BedrockWatchdog -Force `
  -Action (New-ScheduledTaskAction -Execute "$root\.venv\Scripts\pythonw.exe" -Argument "scripts\tunnel_watchdog.py --port 8780" -WorkingDirectory $root) `
  -Trigger (New-ScheduledTaskTrigger -AtLogOn -User $me) `
  -Settings (New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable -MultipleInstances IgnoreNew) `
  -Principal (New-ScheduledTaskPrincipal -UserId $me -LogonType Interactive -RunLevel Limited)
# remove
Unregister-ScheduledTask -TaskName BedrockWatchdog -Confirm:$false
```

Log: `data/staging/watchdog.log`. It needs the user to be logged in (not just the PC on), `cloudflared` installed and `npx wrangler` logged in.

## The live demo on AWS (in use)

`deploy/aws/userdata.sh` is the boot script of a single EC2 instance (t3.small, Amazon Linux 2023, us-east-1). It installs Docker, clones this
repository, builds the same `Dockerfile` as the local setup and runs it on port 80 with `BEDROCK_PUBLIC=1` (rate limits on). The Groq key is read
from an encrypted AWS Systems Manager parameter (`/bedrock/groq_api_key`) by an instance role that can read only that parameter; it is not in the repo or in
the script. The instance has no SSH. Its security group allows port 80 only from CloudFront (managed prefix list `com.amazonaws.global.cloudfront.origin-facing`),
and a CloudFront distribution (no caching, 60 s origin timeout) provides the permanent https address. The container restarts by itself after a reboot.

To update after a code change: `aws ssm send-command` or reconnect with Session Manager, then `cd /opt/bedrock && git pull && docker build -t bedrock-demo . && docker rm -f bedrock-live && docker run ...` (same flags as the script).

Remove everything when judging is over (stops all charges):

```bash
aws cloudfront get-distribution-config --id <ID>   # disable it first (Enabled=false), wait until Deployed, then delete-distribution
aws ec2 terminate-instances --instance-ids <instance-id>
aws ec2 release-address --allocation-id <eipalloc-id>
aws ec2 delete-security-group --group-id <sg-id>          # after the instance is gone
aws ssm delete-parameter --name /bedrock/groq_api_key
aws iam remove-role-from-instance-profile --instance-profile-name bedrock-demo-ec2 --role-name bedrock-demo-ec2
aws iam delete-instance-profile --instance-profile-name bedrock-demo-ec2
aws iam detach-role-policy --role-name bedrock-demo-ec2 --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore
aws iam delete-role-policy --role-name bedrock-demo-ec2 --policy-name read-groq-key
aws iam delete-role --role-name bedrock-demo-ec2
```
