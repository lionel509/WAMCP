# Cloudflare Tunnel Setup (Persistent Token-Based)

This guide is for setting up a **persistent tunnel with a stable hostname** using a Cloudflare token.

**For quick testing without a token, use `make tunnel` instead** (see main [README.md](../../README.md#cloudflare-tunnel-setup)).

---

This directory contains configuration for exposing the local docker-compose stack to the internet via [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/) with a persistent, named hostname.

## Why Persistent Tunnels?

- Your tunnel URL stays the same across restarts
- Ideal for long-lived development environments or staging
- Requires a Cloudflare account and creating a tunnel manually

**If you just want to test webhooks once: use `make tunnel` (quick tunnel).**

## Two Auth Modes

### 1. Token-Based (Recommended for Persistent Tunnels)

**For a tunnel that persists across restarts:**
- Create a tunnel in Cloudflare Zero Trust dashboard
- Copy the tunnel token
- Set `CLOUDFLARED_TUNNEL_TOKEN` in `.env` (in future if you want persistent mode)
- Configure hostname routing in Cloudflare dashboard

**Pros:**
- Hostname persists across restarts
- Can be shared/managed centrally
- No local credentials file needed

**Cons:**
- Requires Cloudflare account + manual setup
- Token is sensitive (like a password)

### 2. Quick Tunnel (Recommended for Local Testing)

**For instant public access without token setup:**
```bash
make tunnel
```

No token needed! Cloudflare generates a random hostname automatically. See [Quick Tunnel](../../README.md#quick-tunnel-recommended-for-local-dev) in the main README.

---

### Step 1: Create a Tunnel in Cloudflare Dashboard

1. Go to **Cloudflare Dashboard** → **Zero Trust** → **Networks** → **Tunnels**
2. Click **Create a tunnel**
3. Choose **Cloudflared**
4. Name it (e.g., `wamcp-dev`)
5. Copy the **token** (looks like `eyJhIjoiXXX...`)

### Step 2: Add Tunnel Details to `.env`

```bash
# Copy from Cloudflare dashboard
CLOUDFLARED_TUNNEL_TOKEN=eyJhIjoiXXX...

# This will be your public hostname (you'll set it in step 3)
CLOUDFLARED_PUBLIC_BASE_URL=https://wamcp-dev.example.com
```

### Step 3: Configure the Public Hostname (Cloudflare Dashboard)

1. Still in the tunnel config, click **Public Hostnames**
2. **Add a public hostname**:
   - **Subdomain**: `wamcp-dev` (or your choice)
   - **Domain**: `example.com` (your Cloudflare domain)
   - **Type**: `HTTPS`
   - **URL**: `http://api:8000` (internal docker service)
3. Save

### Step 4: Start the Stack with Tunnel

```bash
make dev-tunnel
```

This runs:
```bash
docker-compose up --build
```

And includes the `cloudflared` service, which tunnels `api:8000` to your public hostname.

### Step 5: Verify It Works

```bash
# From your local machine (outside docker):
curl https://wamcp-dev.example.com/

# Should reach your API
```

## Connecting Meta Webhooks

Once your tunnel is live:

1. Go to **Meta App Dashboard** → **WhatsApp** → **Configuration**
2. Set **Callback URL**:
   ```
   https://wamcp-dev.example.com/webhooks/whatsapp
   ```
3. Set **Verify Token** to your `WHATSAPP_VERIFY_TOKEN` from `.env`
4. Click **Verify and Save**

Meta will now POST webhooks to your public tunnel URL, which routes to your local API.

## Useful Commands

```bash
# Start dev stack WITH tunnel
make dev-tunnel

# View API logs
make logs-api

# View cloudflared tunnel logs
make logs-cloudflared

# Stop everything
make down
```

## Security Notes

- **Never commit** `CLOUDFLARED_TUNNEL_TOKEN` to git (it's in `.env`, which is in `.gitignore`)
- The tunnel token acts like a password; treat it as sensitive
- Only the API endpoint is exposed; Postgres, Redis, MinIO remain internal
- All traffic is encrypted end-to-end via Cloudflare's network

## Troubleshooting

### Tunnel not connecting

```bash
docker-compose logs cloudflared
```

Check the token is valid and not expired.

### Webhook URL verification fails

- Ensure `WHATSAPP_VERIFY_TOKEN` matches what you set in Meta dashboard
- Confirm the API is responding: `curl https://your-tunnel-url/health`

### "502 Bad Gateway"

Usually means the API service is not healthy or not listening on `0.0.0.0:8000`. Check:

```bash
docker-compose logs api
```
