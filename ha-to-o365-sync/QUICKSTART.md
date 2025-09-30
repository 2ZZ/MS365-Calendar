# Quick Start Guide

## Prerequisites

1. Home Assistant with calendar(s)
2. Microsoft 365 account
3. Azure AD app registration (see full README for setup)

## Setup Steps

### 1. Configure Azure AD App

- Create app registration in [Azure Portal](https://portal.azure.com)
- **NO redirect URI needed** (using device code flow)
- Enable "Allow public client flows" in Authentication → Advanced settings
- Add **Delegated permissions** (NOT Application):
  - `Calendars.ReadWrite`
  - `offline_access`
- Note your Client ID and Tenant ID (Client Secret NOT needed)

### 2. Configure the Script

```bash
cd ha-to-o365-sync
cp config.yaml.example config.yaml
# Edit config.yaml with your credentials
```

### 3. Authenticate with Device Code Flow

**Can be done in Docker!** Device code flow works without browser on the same machine:

```bash
docker-compose run --rm ha-calendar-sync python sync.py --interactive
```

Or authenticate locally:
```bash
pip install -r requirements.txt
python sync.py --interactive
```

The script will show:
- A URL to visit (e.g., `https://microsoft.com/devicelogin`)
- A code to enter (e.g., `ABC-DEF-GHI`)

Visit the URL on **any device** (phone, laptop), enter the code, and approve permissions.
Token is saved to `.tokens/` for future runs.

### 4. Run with Docker

```bash
docker-compose up -d
docker-compose logs -f
```

## Health Checks

The container runs startup health checks that verify:
- ✓ Config file exists and is valid
- ✓ Office 365 token exists (authentication completed)
- ✓ Home Assistant is accessible
- ✓ Office 365 authentication works
- ✓ Calendar configuration is valid

If any check fails, the container exits with a clear error message.

## Retry Logic

- **Success**: Waits 15 minutes, then syncs again
- **Failure**: Retries after 60 seconds
- **3 consecutive failures**: Backs off for 1 hour
- Prevents aggressive retry loops

## Troubleshooting

### "No authentication token found"
Run authentication with device code flow:
```bash
docker-compose run --rm ha-calendar-sync python sync.py --interactive
```

### "Failed to connect to Home Assistant"
- Check URL in `config.yaml`
- Verify token is valid
- Ensure Home Assistant is accessible from Docker

### "Cannot authenticate with Office 365"
- Ensure you used **Delegated** permissions (not Application)
- Delete `.tokens/` and re-authenticate
- Check client secret hasn't expired

### Container keeps restarting
```bash
docker-compose logs
```
Check the logs for specific error messages from health checks.

## Files Created

- `config.yaml` - Your configuration (not in git)
- `.tokens/` - OAuth tokens (not in git)
- Both are excluded by `.gitignore`

## Environment Variables

You can customize the retry behavior in `docker-compose.yml`:

```yaml
environment:
  - SYNC_INTERVAL=900    # Seconds between successful syncs (15 min)
  - MAX_RETRIES=3        # Retries before backing off
  - BACKOFF_TIME=3600    # Backoff duration in seconds (1 hour)
```
