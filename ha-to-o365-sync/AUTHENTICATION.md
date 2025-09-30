# Authentication Guide

## Device Code Flow

This application uses **Device Code Flow** for Office 365 authentication, which allows authentication from inside Docker containers without requiring a browser on the same machine.

## How It Works

1. You run the script with `--interactive` flag
2. The script displays a URL (e.g., `https://microsoft.com/devicelogin`)
3. The script displays a code (e.g., `ABC-DEF-GHI`)
4. You visit the URL on **any device** (phone, laptop, tablet)
5. You enter the code
6. You sign in with your Microsoft account
7. You approve the requested permissions
8. The token is saved and reused for future runs

## Advantages

- ✅ Works in Docker containers
- ✅ No redirect URI needed
- ✅ No browser required on the same machine
- ✅ Can authenticate from any device
- ✅ More secure than storing passwords
- ✅ Tokens refresh automatically

## Authenticate in Docker

```bash
docker-compose run --rm ha-calendar-sync python sync.py --interactive
```

The container will:
1. Display the device code URL and code
2. Wait for you to complete authentication
3. Save the token to `.tokens/` (persisted via volume)
4. Exit

Then start the sync service:
```bash
docker-compose up -d
```

## Authenticate Locally

If you prefer to authenticate outside Docker:

```bash
pip install -r requirements.txt
python sync.py --interactive
```

The token will be saved to `.tokens/` and will be accessible to Docker via volume mount.

## Permissions Requested

The script requests **only** these permissions:
- `Calendars.ReadWrite` - Read and write calendar events
- `offline_access` - Refresh token for long-term access

**NOT requested**: Mail, Files, Contacts, or any other permissions that the O365 library supports. Only calendar access is requested.

## Azure AD App Setup

For device code flow, your Azure AD app must:

1. **Enable public client flows**
   - Go to Authentication → Advanced settings
   - Set "Allow public client flows" to **YES**

2. **No redirect URI needed**
   - Device code flow doesn't use redirect URIs
   - You can leave this blank

3. **Delegated permissions only**
   - Add `Calendars.ReadWrite`
   - Add `offline_access`
   - Do NOT use Application permissions

4. **Client secret NOT needed**
   - Device flow (public client) doesn't use secrets
   - You can leave this blank or use a placeholder in config.yaml

## Token Storage

Tokens are stored in `.tokens/o365_token.txt`:
- Encrypted by the O365 library
- Contains access token and refresh token
- Automatically refreshed when expired
- Should be kept secure (excluded from git)

## Troubleshooting

### "Authentication failed"
- Ensure "Allow public client flows" is enabled in Azure AD
- Check that you have the correct Client ID and Tenant ID
- Verify you're signing in with the correct Microsoft account

### "Permission denied"
- Check that you added Delegated permissions (not Application)
- Verify `Calendars.ReadWrite` and `offline_access` are added
- Try removing and re-adding permissions in Azure AD

### "Token expired"
- Delete `.tokens/` directory
- Re-run authentication: `python sync.py --interactive`
- Tokens should auto-refresh, but sometimes need manual re-auth

### "Cannot find token"
If running in Docker and token doesn't persist:
- Check that `.tokens/` is mounted as a volume in docker-compose.yml
- Verify permissions on `.tokens/` directory
- Try authenticating directly in Docker: `docker-compose run --rm ha-calendar-sync python sync.py --interactive`

## Security Best Practices

1. **Keep tokens secure**
   - Don't commit `.tokens/` to version control
   - Protect token files with appropriate permissions
   - Rotate tokens regularly

2. **Use least privilege**
   - Only request calendar permissions
   - Don't grant more permissions than needed

3. **Monitor access**
   - Check Azure AD sign-in logs regularly
   - Revoke tokens if suspicious activity detected

4. **Rotate credentials**
   - Rotate client secrets every 6-12 months
   - Re-authenticate if you suspect compromise
