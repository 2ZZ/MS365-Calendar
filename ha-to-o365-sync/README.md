# Home Assistant to Office 365 Calendar Sync

A simple Python script to sync Home Assistant calendars to Office 365. This fills the gap by providing one-way synchronization from Home Assistant to Outlook/O365 calendars.

## Features

- One-way sync from Home Assistant to Office 365
- Syncs multiple HA calendars to a single O365 calendar
- Configurable date range (past and future)
- Prefix support to identify synced events
- Optional deletion of events removed from HA
- Can be run on a cron schedule

## Prerequisites

1. **Home Assistant**
   - Running Home Assistant instance with calendar(s)
   - Long-lived access token

2. **Office 365**
   - Microsoft 365 account
   - Azure AD App Registration (for API access)

## Setup

### 1. Install Dependencies

```bash
cd ha-to-o365-sync
pip install -r requirements.txt
```

### 2. Create Azure AD App Registration

1. Go to [Azure Portal](https://portal.azure.com)
2. Navigate to Azure Active Directory → App registrations
3. Click "New registration"
4. Name: `HA Calendar Sync`
5. Supported account types: "Accounts in this organizational directory only"
6. **Redirect URI**: LEAVE BLANK (we use device code flow)
7. Click "Register"

8. **Get Client ID and Tenant ID**
   - Copy the "Application (client) ID"
   - Copy the "Directory (tenant) ID"

9. **Enable Public Client Flow**
   - Go to "Authentication"
   - Scroll down to "Advanced settings"
   - Under "Allow public client flows", set to **YES**
   - Click "Save"

10. **Set API Permissions**
    - Go to "API permissions"
    - Click "Add a permission"
    - Choose "Microsoft Graph"
    - Choose **"Delegated permissions"** (NOT Application permissions)
    - Add only: `Calendars.ReadWrite` and `offline_access`
    - You do NOT need admin consent for delegated permissions
    - **Note**: The script only requests these two permissions

**Note**: Client secret is NOT needed for device code flow. You can leave it blank or use a placeholder value in config.yaml.

### 3. Get Home Assistant Token

1. Log in to Home Assistant
2. Click your profile (bottom left)
3. Scroll to "Long-Lived Access Tokens"
4. Click "Create Token"
5. Name: `Calendar Sync`
6. Copy the token

### 4. Configure the Script

1. Copy the example config:
```bash
cp config.yaml.example config.yaml
```

2. Edit `config.yaml` with your details:

```yaml
home_assistant:
  url: "http://homeassistant.local:8123"
  token: "your_long_lived_access_token"

office365:
  client_id: "your_client_id"
  client_secret: "your_client_secret"
  tenant_id: "your_tenant_id"  # or "common"
  calendar_id: "primary"

sync:
  ha_calendars:
    - "calendar.home_calendar"
    - "calendar.personal"
  days_past: 7
  days_future: 90
  event_prefix: "[HA]"
  delete_removed_events: true
```

### 5. First Time Authentication

**NEW**: Device code flow allows authentication from inside Docker! You can authenticate from any device.

**Option A: Authenticate Locally**
```bash
pip install -r requirements.txt
python sync.py --interactive
```

**Option B: Authenticate in Docker**
```bash
docker-compose run --rm ha-calendar-sync python sync.py --interactive
```

The script will:
1. Display a URL (e.g., `https://microsoft.com/devicelogin`)
2. Display a code (e.g., `ABC-DEF-GHI`)
3. You visit the URL on **any device** (phone, laptop, etc.)
4. Enter the code shown
5. Sign in and approve calendar permissions
6. Token is saved to `.tokens/` for future runs

**Permissions requested**: Only `Calendars.ReadWrite` and `offline_access` (not the full library defaults)

**Other options:**
```bash
# Verbose logging
python sync.py -v

# Custom config file
python sync.py -c /path/to/config.yaml

# Full sync (after authentication)
python sync.py
```

## Running with Docker

### Using Docker Compose (Recommended)

1. Create your `config.yaml` file (see configuration above)

2. **Authenticate using device code flow** (can be done in Docker!):
```bash
docker-compose run --rm ha-calendar-sync python sync.py --interactive
```

Follow the prompts to authenticate via device code on any device.

3. Start the container:
```bash
docker-compose up -d
```

4. View logs:
```bash
docker-compose logs -f
```

5. Stop the container:
```bash
docker-compose down
```

The docker-compose setup:
- **Startup health checks**: Validates configuration and authentication before starting
- Runs the sync every 15 minutes automatically
- Mounts your `config.yaml` as read-only
- Mounts `.tokens/` directory to persist authentication
- Restarts automatically on failure
- Implements intelligent retry logic:
  - On sync failure: retries after 60 seconds
  - After 3 consecutive failures: backs off for 1 hour
  - Prevents aggressive retry loops that could spam logs
- If health checks fail on startup, the container exits with clear error messages

### Using Docker Run

Build the image:
```bash
docker build -t ha-calendar-sync .
```

Run once:
```bash
docker run --rm \
  -v $(pwd)/config.yaml:/app/config.yaml:ro \
  -v ha-sync-tokens:/app/.tokens \
  ha-calendar-sync
```

Run continuously (every 15 minutes):
```bash
docker run -d \
  --name ha-calendar-sync \
  --restart unless-stopped \
  -v $(pwd)/config.yaml:/app/config.yaml:ro \
  -v ha-sync-tokens:/app/.tokens \
  ha-calendar-sync \
  sh -c "while true; do python sync.py && sleep 900; done"
```

## Scheduling with Cron

To run automatically every 15 minutes without Docker:

```bash
# Edit crontab
crontab -e

# Add this line (adjust path as needed)
*/15 * * * * cd /path/to/ha-to-o365-sync && /usr/bin/python3 sync.py >> sync.log 2>&1
```

## How It Works

1. Fetches events from specified Home Assistant calendars
2. Fetches existing synced events from Office 365 (identified by prefix)
3. Compares events and:
   - Creates new events in O365 that exist in HA
   - Updates existing events if they've changed
   - Deletes events from O365 that were removed from HA (if enabled)

Events are tracked using UIDs to maintain the relationship between HA and O365.

## Configuration Options

### `home_assistant`
- `url`: Home Assistant base URL
- `token`: Long-lived access token

### `office365`
- `client_id`: Azure AD app client ID
- `client_secret`: Azure AD app client secret
- `tenant_id`: Azure AD tenant ID (or "common" for multi-tenant)
- `calendar_id`: O365 calendar ID (use "primary" for default calendar)

### `sync`
- `ha_calendars`: List of HA calendar entity IDs to sync
- `days_past`: How many days in the past to sync (default: 7)
- `days_future`: How many days in the future to sync (default: 90)
- `event_prefix`: Prefix added to synced events (default: "[HA]")
- `delete_removed_events`: Delete from O365 when removed from HA (default: true)

## Troubleshooting

### Authentication Errors

**Problem:** "Failed to authenticate with Office 365"

**Solutions:**
- Verify client ID and secret are correct
- Ensure client secret hasn't expired
- Check API permissions are granted
- Try using "common" for tenant_id

### Home Assistant Connection Errors

**Problem:** "Failed to connect to Home Assistant"

**Solutions:**
- Verify Home Assistant URL is correct and accessible
- Check the long-lived access token is valid
- Ensure firewall allows connections

### No Events Syncing

**Problem:** Events aren't appearing in O365

**Solutions:**
- Check HA calendar entity IDs are correct (run `sync.py -v` for details)
- Verify date range includes the events
- Look for errors in verbose logging
- Check O365 calendar permissions

### Token Storage

The script stores O365 authentication tokens in `.tokens/` directory. If you have authentication issues:

```bash
# Remove cached tokens and re-authenticate
rm -rf .tokens/
python sync.py
```

## Limitations

- One-way sync only (HA → O365)
- No conflict resolution (HA is source of truth)
- All synced events go to a single O365 calendar
- Recurring events are treated as individual instances

## Security Notes

- Keep `config.yaml` secure (contains secrets)
- The `.gitignore` excludes sensitive files
- Consider using environment variables for production
- Rotate client secrets regularly

## License

This is a companion tool for the MS365 Calendar integration. Use at your own risk.
