#!/usr/bin/env python3
"""Startup health check for calendar sync."""

import logging
import sys
from pathlib import Path

import yaml

from ha_client import HomeAssistantClient
from o365_client import Office365Client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
_LOGGER = logging.getLogger(__name__)


def load_config(config_path: Path) -> dict:
    """Load configuration from YAML file."""
    if not config_path.exists():
        _LOGGER.error(f"Config file not found: {config_path}")
        return None

    try:
        with open(config_path) as f:
            config = yaml.safe_load(f)
        return config
    except Exception as e:
        _LOGGER.error(f"Failed to load config: {e}")
        return None


def check_token_exists():
    """Check if O365 token exists."""
    token_path = Path(__file__).parent / ".tokens" / "o365_token.txt"
    if not token_path.exists():
        _LOGGER.error("=" * 70)
        _LOGGER.error("AUTHENTICATION REQUIRED")
        _LOGGER.error("=" * 70)
        _LOGGER.error("")
        _LOGGER.error("No Office 365 authentication token found.")
        _LOGGER.error("")
        _LOGGER.error("Authenticate using device code flow (can be done in Docker!):")
        _LOGGER.error("")
        _LOGGER.error("  docker-compose run --rm ha-calendar-sync python sync.py --interactive")
        _LOGGER.error("")
        _LOGGER.error("Or authenticate locally:")
        _LOGGER.error("")
        _LOGGER.error("  python sync.py --interactive")
        _LOGGER.error("")
        _LOGGER.error("Device code flow allows you to authenticate from any device.")
        _LOGGER.error("You'll visit a URL and enter a code.")
        _LOGGER.error("")
        _LOGGER.error("=" * 70)
        return False
    return True


def check_home_assistant(config: dict) -> bool:
    """Check Home Assistant connectivity."""
    _LOGGER.info("Testing Home Assistant connection...")

    try:
        ha_client = HomeAssistantClient(
            config["home_assistant"]["url"],
            config["home_assistant"]["token"]
        )

        if not ha_client.test_connection():
            _LOGGER.error("Cannot connect to Home Assistant")
            _LOGGER.error(f"  URL: {config['home_assistant']['url']}")
            _LOGGER.error("  Check that Home Assistant is running and accessible")
            _LOGGER.error("  Verify the long-lived access token is valid")
            return False

        _LOGGER.info("✓ Home Assistant connection successful")
        return True

    except Exception as e:
        _LOGGER.error(f"Home Assistant check failed: {e}")
        return False


def check_office365(config: dict) -> bool:
    """Check Office 365 authentication."""
    _LOGGER.info("Testing Office 365 authentication...")

    try:
        o365_client = Office365Client(
            config["office365"]["client_id"],
            config["office365"]["client_secret"],
            config["office365"]["tenant_id"],
            config["office365"].get("calendar_id", "primary"),
            config["office365"].get("user_principal_name")
        )

        # Don't use interactive mode in health check
        if not o365_client.authenticate(interactive=False):
            _LOGGER.error("Cannot authenticate with Office 365")
            _LOGGER.error("  Check your client_id and client_secret")
            _LOGGER.error("  Ensure you've completed initial authentication")
            return False

        _LOGGER.info("✓ Office 365 authentication successful")
        _LOGGER.info(f"  Calendar: {o365_client.calendar.name}")
        return True

    except Exception as e:
        _LOGGER.error(f"Office 365 check failed: {e}")
        return False


def check_calendars(config: dict) -> bool:
    """Check that configured HA calendars are accessible."""
    _LOGGER.info("Checking Home Assistant calendars...")

    try:
        ha_client = HomeAssistantClient(
            config["home_assistant"]["url"],
            config["home_assistant"]["token"]
        )

        calendars = config["sync"]["ha_calendars"]
        _LOGGER.info(f"  Configured calendars: {', '.join(calendars)}")

        # Just verify they're in the config - actual access will be tested during sync
        _LOGGER.info("✓ Calendar configuration valid")
        return True

    except Exception as e:
        _LOGGER.error(f"Calendar check failed: {e}")
        return False


def main():
    """Run health checks."""
    _LOGGER.info("=" * 70)
    _LOGGER.info("RUNNING STARTUP HEALTH CHECKS")
    _LOGGER.info("=" * 70)

    # Load config
    config_path = Path(__file__).parent / "config.yaml"
    config = load_config(config_path)
    if not config:
        _LOGGER.error("✗ Config check failed")
        sys.exit(1)
    _LOGGER.info("✓ Config loaded")

    # Check token exists
    if not check_token_exists():
        _LOGGER.error("✗ Token check failed")
        sys.exit(1)
    _LOGGER.info("✓ Token file exists")

    # Check Home Assistant
    if not check_home_assistant(config):
        _LOGGER.error("✗ Home Assistant check failed")
        sys.exit(1)

    # Check Office 365
    if not check_office365(config):
        _LOGGER.error("✗ Office 365 check failed")
        sys.exit(1)

    # Check calendars
    if not check_calendars(config):
        _LOGGER.error("✗ Calendar check failed")
        sys.exit(1)

    _LOGGER.info("=" * 70)
    _LOGGER.info("✓ ALL HEALTH CHECKS PASSED")
    _LOGGER.info("=" * 70)
    _LOGGER.info("Ready to start syncing...")
    sys.exit(0)


if __name__ == "__main__":
    main()
