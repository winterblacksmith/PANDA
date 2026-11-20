# Railway to Irene: administrator review and staged rollout

Prepared 2026-11-07. PROPOSED steps, not executed deployment changes.
See IRENE_SESSION_RECORD.md for completed work and evidence.

## What works and what must change first

Irene's authenticated local gateway generated READY from qwen2.5:3b in 4.57s.
It listens only on 127.0.0.1:8000. Ollama has no published host port.
Railway therefore cannot reach it yet. A Mac VPN connection does not place
Railway inside UGA's network.

The integration/irene-fastapi client uses /v1/models and /v1/chat. Irene's
older gateway uses /api/tags and /api/chat. Align the API before routing traffic.
The plan below upgrades only gateway source and adds a small Compose override
to preserve the old Irene configuration, token name, Ollama container and volume.
Do not replace the entire copied Irene project or run docker compose down.

## Administrator decision: choose ONE network route

| Route | Incoming connectivity | Outgoing connectivity | Public backend ports |
| --- | --- | --- | --- |
| A. University-managed HTTPS reverse proxy | TCP 443 to the approved public proxy | Railway to HTTPS proxy | Neither 8000 nor 11434 |
| B. Approved named Cloudflare Tunnel | No new inbound port on Irene | Irene connector to Cloudflare on 7844 TCP (HTTP/2) or UDP (QUIC); Railway to public hostname on TCP 443 | Neither 8000 nor 11434 |

Route A is preferred if UGA already provides a managed HTTPS publishing service.
If the proxy runs on Irene it forwards to 127.0.0.1:8000 and no backend firewall
opening is needed. If it runs on another UGA host, loopback on Irene is not
reachable from that host. The administrator must approve a private interface
binding and firewall rule allowing ONLY that proxy's private address to Irene
TCP 8000, or an approved private transport. That is a separate reviewed change.

TCP 80 is optional for a selected certificate-validation/redirect method, not
inherently required; DNS-based validation can avoid it. Existing SSH TCP 22
access need not be broadened. Do NOT expose Ollama 11434, Docker 2375/2376,
or the gateway 8000 directly to the internet. Do not change Streamlit's ports.
DNS resolution and normal HTTPS egress for connector management/install/update
may also be required under university policy. Admin should use provider's
current documented destinations rather than broad egress rules.

No SSH reverse tunnel, temporary public quick tunnel, personal VPN bridge or
public Ollama endpoint is part of this plan. A tunnel still publishes a service
through a third party, even without an inbound firewall opening; approval is
required for security, data handling, uptime ownership and logging.

## Administrator checklist BEFORE implementation

1. Approve compute allocation, model use and expected concurrency on Irene.
2. Choose A or B and assign an administrator-owned hostname. Examples below
   use inference.example.edu as a PLACEHOLDER, not an existing hostname.
3. Confirm which prompts/data may transit the selected service.
4. Decide who owns TLS certificates, DNS, patching, monitoring and revocation.
5. Approve authenticated API exposure and rate/concurrency/request limits.
   The current token gates the backend, not end users of the public app. Set
   app access controls and usage limits before opening unrestricted public use.
6. Require proxy/backend timeouts long enough for cold starts, initially at
   least 180 seconds where supported. A longer client timeout cannot defeat a
   shorter provider/proxy timeout. Verify selected provider limits.
7. Confirm existing ports/services before any install. Never overwrite a
   shared proxy configuration or restart the shared Docker daemon.

## Phase 1: align gateway with integration client (after approval)

These steps change only the PANDA gateway. Rebuild uses shared CPU/disk and
interrupts the gateway briefly. Stop if any prerequisite differs.

1. Confirm Railway staging will deploy integration/irene-fastapi from
   winterblacksmith/PANDA. Confirm its llm_client.py uses /v1/*.
2. On Irene, create a timestamped backup. Record the printed backup path:

```bash
cd ~/PANDA
PANDA_BACKUP_FILE="$PWD/panda-gateway-backup-$(date +%Y%m%d-%H%M%S).tar"
tar -cpf "$PANDA_BACKUP_FILE" inference_gateway docker-compose.llm.yml docker-compose.irene.yml
printf 'Backup: %s\n' "$PANDA_BACKUP_FILE"
```

This does not back up or display the secret file. Do not commit server backups.
The backup may contain incidental files; keep it private on the server.

3. On the Mac, in a verified checkout of integration/irene-fastapi, run:

```bash
git status --short --branch
git log -1 --oneline
scp inference_gateway/main.py inference_gateway/requirements.txt inference_gateway/Dockerfile shishir@128.192.48.10:~/PANDA/inference_gateway/
```

This replaces exactly three gateway files, not app data or Compose definitions.
Use a reviewed revision; never blindly copy a dirty or different branch.

4. On Irene, use an editor to CREATE docker-compose.gateway-v1.yml with the
   following contents. If it already exists, inspect/back it up before editing:

```yaml
services:
  gateway:
    environment:
      OLLAMA_BASE_URL: http://ollama:11434
      PANDA_ALLOWED_MODELS: qwen2.5:3b
      PANDA_INFERENCE_TOKEN: ${PANDA_LLM_API_TOKEN:?Existing Irene token must be set}
```

This maps the old secret name to the new gateway's name. The secret's value is
NOT written in this YAML. Preserve .env.local-llm and its permissions.

5. Validate without printing the resolved configuration (it contains secrets):

```bash
docker compose --env-file .env.local-llm -f docker-compose.llm.yml -f docker-compose.gateway-v1.yml config --quiet
```

6. Rebuild ONLY the gateway. Do not add the GPU override unnecessarily; do not
   recreate Ollama, pull a model, or remove volumes:

```bash
docker compose --env-file .env.local-llm -f docker-compose.llm.yml -f docker-compose.gateway-v1.yml up -d --build --no-deps gateway
docker ps --filter name=panda-local-llm --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
docker logs --tail 25 panda-local-llm-gateway-1
curl --fail --silent --show-error --max-time 10 http://127.0.0.1:8000/health
```

7. Run the Python verification script in Phase 4 on Irene with:
   PANDA_TEST_URL=http://127.0.0.1:8000. Obtain the existing secret privately.
   Do not feed the old /api/chat test payload to /v1/chat; extra fields such
   as stream/keep_alive are rejected by this API. Confirm 401, models, chat.

## Phase 2A: managed HTTPS reverse proxy (administrator only)

1. Assign DNS and a trusted TLS certificate for the approved hostname.
2. Forward this hostname only to PANDA's gateway, not arbitrary Irene services.
3. Preserve Authorization; disable caching of model/chat responses; suppress
   token/body logging; configure request-size and usage limits.
4. Set proxy connect timeout 10s and read/send timeout 180s or more as agreed.
5. Validate configuration and gracefully reload using the administrator's
   existing deployment process. Do not replace the shared proxy config.

Example Nginx location INSIDE an administrator-managed HTTPS server block,
only when Nginx runs directly on Irene (not a complete install script):

```nginx
location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header Authorization $http_authorization;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_connect_timeout 10s;
    proxy_read_timeout 180s;
    proxy_send_timeout 180s;
    proxy_buffering off;
    proxy_cache off;
    client_max_body_size 2m;
}
```

TLS, authentication hardening, rate limits and firewall rules remain the admin's
responsibility. If 443 is already used, add a hostname virtual host rather than
trying to start a second listener on the same address/port.

## Phase 2B: named Cloudflare Tunnel alternative (administrator only)

1. Approve Cloudflare use and an organization-owned domain/account.
2. Create a NAMED managed tunnel for PANDA, not an ephemeral quick tunnel.
3. Install/run cloudflared using the administrator's approved service manager,
   storing the tunnel credential privately, never in Git or a screenshot.
4. Configure one public hostname with origin http://127.0.0.1:8000 if the
   connector runs on Irene's host. In a container, 127.0.0.1 means that container,
   not Irene; the admin must instead approve a correct private network route.
5. Allow connector egress to Cloudflare's documented endpoints on 7844 with
   the selected protocol. No new inbound Irene port is needed.
6. Keep FastAPI bearer authentication enforced. If adding Cloudflare Access,
   use machine-to-machine service credentials rather than browser login for
   Railway. The current PANDA client DOES NOT send Cloudflare Access service
   headers; implement/test that separately before enabling such a policy.
7. Verify end-to-end request timeout limits, DNS, TLS and external auth tests.

Do not install a system service or select broad firewall rules without admin
instructions. Provider docs:
https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/configure-tunnels/tunnel-with-firewall/

## Phase 3: Railway staging, exact configuration sequence

1. In the PANDA Railway project, create a staging environment/service. Review
   duplication before provisioning extra services/volumes to avoid unintended
   costs. Do not attach the production chat database to staging.
2. Select winterblacksmith/PANDA and integration/irene-fastapi for the staging
   app service. Record the deployed commit. Leave docs service settings alone.
3. Add service-scoped variables to the STAGING APP only:

```dotenv
PANDA_INFERENCE_URL=https://inference.example.edu
PANDA_INFERENCE_TOKEN=<secret matching the gateway, entered privately>
PANDA_OLLAMA_MODEL=qwen2.5:3b
```

Replace the hostname; do not include /v1/chat in the base URL. Never use
127.0.0.1, Irene's SSH address with port 8000, or ollama.railway.internal as
PANDA_INFERENCE_URL. Existing OLLAMA_HOST is direct-Ollama fallback only; the
verified integration client prioritizes PANDA_INFERENCE_URL. The token is a
service secret, never a browser/public frontend variable. For fully isolated
staging/production credentials, use separately configured gateways; the current
gateway accepts one token, so do not claim separate tokens work on one instance.
4. Keep existing Streamlit port/start settings unless the staging deployment
   itself proves they are incorrect. Do not alter the independent Ollama or
   documentation services as part of this switch.
5. Deploy STAGING. Confirm its commit and startup logs.
6. In the running STAGING app's Railway console/SSH session, run Phase 4.
   Run it in the deployed runtime, not railway run on a laptop: local execution
   does not prove reachability from Railway's servers.
7. Test the staging web UI: a brief general question, a factual dataset query,
   and a follow-up. Confirm actual model use, no fallback warning, correct data
   totals, and acceptable response times. Avoid private data during testing.
8. Retain production untouched until tests pass and the administrator approves
   continued exposure and compute usage. Then apply the reviewed branch and
   equivalent variables to production in a scheduled change window.

Railway environments: https://docs.railway.com/environments
Railway variables: https://docs.railway.com/variables

## Phase 4: endpoint checks from the actual runtime

In Railway, PANDA_INFERENCE_URL and PANDA_INFERENCE_TOKEN are already set.
On Irene, run `export PANDA_TEST_URL=http://127.0.0.1:8000` and enter the token
privately at the getpass prompt (never paste a token into a command). Use an
interactive terminal for that prompt.
The generation test uses shared compute; run once with permission.

```bash
python3 - <<'PY'
import getpass, json, os, urllib.request, urllib.error
base = (os.environ.get('PANDA_TEST_URL') or os.environ['PANDA_INFERENCE_URL']).rstrip('/')
token = os.environ.get('PANDA_INFERENCE_TOKEN') or getpass.getpass('Gateway token: ')
def check(path, auth=False, payload=None):
    headers = {'Content-Type': 'application/json'}
    if auth:
        headers['Authorization'] = 'Bearer ' + token
    req = urllib.request.Request(base + path, headers=headers,
        data=json.dumps(payload).encode() if payload is not None else None)
    try:
        with urllib.request.urlopen(req, timeout=180) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        return exc.code, {}
assert check('/health')[0] == 200, 'Health failed'
assert check('/v1/models')[0] == 401, 'Unauthenticated call was not rejected'
status, models = check('/v1/models', True)
assert status == 200, f'Model listing HTTP {status}'
assert any(m.get('model') == 'qwen2.5:3b' for m in models.get('models', [])), 'Model missing'
status, reply = check('/v1/chat', True, {
    'model': 'qwen2.5:3b',
    'messages': [{'role': 'user', 'content': 'Reply with only the word READY.'}],
    'options': {'num_predict': 8},
})
assert status == 200, f'Generation HTTP {status}'
content = reply.get('message', {}).get('content', '').strip()
assert content, 'Empty reply'
print('PASS: health, auth rejection, models, generation. Reply:', content)
PY
```

No TLS verification bypass (-k) is permitted. A proxy login page, HTTP 200 HTML,
or app landing page is not a successful inference test. This script fails if
responses do not meet the contract; exceptions need investigation, not repeated
blind retries.

## Rollback and stopping conditions

- If gateway upgrade fails: stop, collect scoped logs, restore only the backed-up
  gateway directory and retain the original Compose invocation WITHOUT the v1
  override, then rebuild only gateway. Use the exact recorded backup path and
  inspect archive contents before restoring. Do not run compose down or prune.
- If ingress fails: administrator removes only PANDA's new route/connector,
  without changing other hosted services.
- If staging fails: leave production unchanged and revert staging variables or
  deployment. Never delete chat/database volumes as a troubleshooting step.
- If production fails: restore its previous reviewed deployment and variables.
  Do not claim reverting code alone restores separate Railway variables.
- Record each executed command and redacted outcome in the worklog. This file
  is a proposal, not authorization to run administrator commands.
