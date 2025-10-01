#!/usr/bin/env python3
"""Sync Home Assistant calendars to Office 365."""

from o365_client import Office365Client
from ha_client import HomeAssistantClient
import argparse
import logging
import os
import sys
import warnings
from datetime import datetime, timedelta
from pathlib import Path

import yaml

# Suppress PytzUsageWarning from O365 library
warnings.filterwarnings("ignore", category=DeprecationWarning, module="O365")
warnings.filterwarnings("ignore", message=".*pytz.*", category=UserWarning)


logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
_LOGGER = logging.getLogger(__name__)


class CalendarSync:
    """Manages syncing between Home Assistant and Office 365 calendars."""

    def __init__(self, config: dict, interactive: bool = False):
        """Initialize the sync manager."""
        self.config = config
        self.interactive = interactive
        self.ha_client = HomeAssistantClient(
            config["home_assistant"]["url"],
            config["home_assistant"]["token"],
            config["sync"].get("timezone", "Europe/London")
        )
        self.o365_client = Office365Client(
            config["office365"]["client_id"],
            config["office365"]["client_secret"],
            config["office365"]["tenant_id"],
            config["office365"].get("calendar_id", "primary"),
            config["office365"].get("user_principal_name")
        )

        self.delete_removed = config["sync"].get("delete_removed_events", True)

        # Calculate date range
        days_past = config["sync"].get("days_past", 7)
        days_future = config["sync"].get("days_future", 90)
        now = datetime.utcnow()
        self.start_date = now - timedelta(days=days_past)
        self.end_date = now + timedelta(days=days_future)

    def sync(self):
        """Perform the sync operation."""
        _LOGGER.info("Starting calendar sync...")

        try:
            # Test Home Assistant connection first (skip in interactive mode for initial auth)
            if not self.interactive:
                _LOGGER.info("Testing Home Assistant connection...")
                if not self.ha_client.test_connection():
                    _LOGGER.error("Cannot connect to Home Assistant. Aborting sync.")
                    return False

            # Authenticate with O365
            _LOGGER.info("Authenticating with Office 365...")
            if not self.o365_client.authenticate(interactive=self.interactive):
                _LOGGER.error("Cannot authenticate with Office 365. Aborting sync.")
                return False

            # If in interactive mode, authentication is all we need
            if self.interactive:
                _LOGGER.info("="*70)
                _LOGGER.info("✓ Authentication successful!")
                _LOGGER.info("Token saved to .tokens/ directory")
                _LOGGER.info("You can now run the sync in Docker")
                _LOGGER.info("="*70)
                return True

            # Get all HA events
            ha_events = {}
            calendar_prefixes = set()  # Track all possible prefixes for O365 filtering

            for calendar_id in self.config["sync"]["ha_calendars"]:
                _LOGGER.info(f"Fetching events from HA calendar: {calendar_id}")

                # Extract calendar name and create prefix (e.g., "calendar.ian" -> "[Ian]")
                calendar_name = calendar_id.split(".")[-1] if "." in calendar_id else calendar_id
                calendar_prefix = f"[{calendar_name.capitalize()}]"
                calendar_prefixes.add(calendar_prefix)

                events = self.ha_client.get_events(
                    calendar_id,
                    self.start_date,
                    self.end_date
                )
                for event in events:
                    # Store event with its calendar prefix
                    event["calendar_prefix"] = calendar_prefix
                    ha_events[event["uid"]] = event
                    start_str = event["start"].strftime('%Y-%m-%d %H:%M') if event.get("start") else 'No start'
                    end_str = event["end"].strftime('%Y-%m-%d %H:%M') if event.get("end") else 'No end'
                    _LOGGER.info(f"  HA event: {event['summary']} ({start_str} - {end_str}) UID: {event['uid']} -> {calendar_prefix}")
                _LOGGER.info(f"  Found {len(events)} events")

            _LOGGER.info(f"Total HA events to sync: {len(ha_events)}")

            # Get existing synced events from O365
            _LOGGER.info("Fetching existing synced events from Office 365...")
            _LOGGER.info(f"Looking for events with prefixes: {list(calendar_prefixes)}")
            o365_events = self.o365_client.get_synced_events(
                self.start_date,
                self.end_date,
                list(calendar_prefixes)  # Pass all possible prefixes
            )
            _LOGGER.info(f"Found {len(o365_events)} existing synced events in O365")

            # Track operations
            created = 0
            updated = 0
            deleted = 0

            # Sync events from HA to O365
            for uid, ha_event in ha_events.items():
                # Use the calendar-specific prefix for this event
                calendar_prefix = ha_event["calendar_prefix"]
                prefixed_summary = f"{calendar_prefix} {ha_event['summary']}"
                ha_event["summary"] = prefixed_summary

                _LOGGER.debug(f"Processing HA event UID: {uid}, Summary: {prefixed_summary}")
                _LOGGER.debug(f"Available O365 event UIDs: {list(o365_events.keys())}")

                if uid in o365_events:
                    # Event exists, check if it needs updating
                    o365_event = o365_events[uid]
                    if self._event_needs_update(ha_event, o365_event):
                        _LOGGER.info(f"Updating event: {ha_event['summary']}")
                        self.o365_client.update_event(o365_event["id"], ha_event)
                        updated += 1
                else:
                    # Create new event
                    start_str = ha_event["start"].strftime('%Y-%m-%d %H:%M') if ha_event.get("start") else 'No start'
                    end_str = ha_event["end"].strftime('%Y-%m-%d %H:%M') if ha_event.get("end") else 'No end'
                    _LOGGER.info(f"Creating event: {ha_event['summary']} ({start_str} - {end_str}) UID: {uid}")
                    self.o365_client.create_event(ha_event, uid)
                    created += 1

            # Delete events from O365 that no longer exist in HA
            if self.delete_removed:
                for uid, o365_event in o365_events.items():
                    if uid not in ha_events:
                        _LOGGER.info(f"Deleting removed event: {o365_event['summary']}")
                        self.o365_client.delete_event(o365_event["id"])
                        deleted += 1

            _LOGGER.info("Sync completed successfully!")
            _LOGGER.info(f"Summary: {created} created, {updated} updated, {deleted} deleted")
            return True

        except Exception as e:
            _LOGGER.error(f"Sync failed: {e}", exc_info=True)
            return False

    def _event_needs_update(self, ha_event: dict, o365_event: dict) -> bool:
        """Check if an event needs to be updated."""
        # Temporarily disable updates to stop the constant updating
        _LOGGER.debug(f"Skipping update check - events are considered identical")
        return False

    def delete_all_synced_events(self) -> bool:
        """Delete all synced events from O365 for testing/reset purposes."""
        _LOGGER.info("=" * 70)
        _LOGGER.info("DELETING ALL SYNCED EVENTS FROM O365")
        _LOGGER.info("=" * 70)

        try:
            # Authenticate with O365
            _LOGGER.info("Authenticating with Office 365...")
            if not self.o365_client.authenticate(interactive=self.interactive):
                _LOGGER.error("Cannot authenticate with Office 365. Aborting delete.")
                return False

            # Get all possible calendar prefixes
            calendar_prefixes = set()
            for calendar_id in self.config["sync"]["ha_calendars"]:
                calendar_name = calendar_id.split(".")[-1] if "." in calendar_id else calendar_id
                calendar_prefix = f"[{calendar_name.capitalize()}]"
                calendar_prefixes.add(calendar_prefix)

            _LOGGER.info(f"Looking for events with prefixes: {list(calendar_prefixes)}")

            # Get all synced events from O365
            _LOGGER.info("Fetching all synced events from Office 365...")
            o365_events = self.o365_client.get_synced_events(
                self.start_date,
                self.end_date,
                list(calendar_prefixes)
            )

            if not o365_events:
                _LOGGER.info("No synced events found to delete.")
                return True

            _LOGGER.info(f"Found {len(o365_events)} synced events to delete")

            # Confirm deletion
            if self.interactive:
                confirm = input(f"\nAre you sure you want to delete {len(o365_events)} synced events? (yes/no): ")
                if confirm.lower() not in ['yes', 'y']:
                    _LOGGER.info("Deletion cancelled by user.")
                    return True

            # Delete all synced events
            deleted = 0
            for uid, event in o365_events.items():
                try:
                    _LOGGER.info(f"Deleting event: {event['summary']} (UID: {uid})")
                    self.o365_client.delete_event(event["id"])
                    deleted += 1
                except Exception as e:
                    _LOGGER.error(f"Failed to delete event {uid}: {e}")

            _LOGGER.info("=" * 70)
            _LOGGER.info(f"DELETION COMPLETE: {deleted} events deleted")
            _LOGGER.info("=" * 70)
            return True

        except Exception as e:
            _LOGGER.error(f"Delete operation failed: {e}", exc_info=True)
            return False

    def run_continuous(self, sync_interval: int) -> bool:
        """Run continuous sync with configurable sleep interval."""
        import time
        import signal
        import sys

        _LOGGER.info("=" * 70)
        _LOGGER.info("STARTING CONTINUOUS SYNC MODE")
        _LOGGER.info(f"Sync interval: {sync_interval} seconds ({sync_interval//60} minutes)")
        _LOGGER.info("Press Ctrl+C to stop")
        _LOGGER.info("=" * 70)

        # Handle graceful shutdown
        def signal_handler(sig, frame):
            _LOGGER.info("\nReceived interrupt signal. Stopping continuous sync...")
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        sync_count = 0
        while True:
            try:
                sync_count += 1
                _LOGGER.info(f"\n{'='*50}")
                _LOGGER.info(f"SYNC #{sync_count} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                _LOGGER.info(f"{'='*50}")

                # Perform sync
                result = self.sync()

                if result:
                    _LOGGER.info(f"Sync #{sync_count} completed successfully")
                else:
                    _LOGGER.error(f"Sync #{sync_count} failed")

                # Sleep until next sync
                _LOGGER.info(f"Sleeping for {sync_interval} seconds until next sync...")
                time.sleep(sync_interval)

            except Exception as e:
                _LOGGER.error(f"Error in continuous sync loop: {e}", exc_info=True)
                _LOGGER.info(f"Waiting {sync_interval} seconds before retrying...")
                time.sleep(sync_interval)


def load_config(config_path: Path) -> dict:
    """Load configuration from YAML file."""
    if not config_path.exists():
        _LOGGER.error(f"Config file not found: {config_path}")
        _LOGGER.error("Please create config.yaml based on config.yaml.example")
        sys.exit(1)

    with open(config_path) as f:
        config = yaml.safe_load(f)

    # Validate required fields
    required_fields = [
        ("home_assistant", "url"),
        ("home_assistant", "token"),
        ("office365", "client_id"),
        ("office365", "client_secret"),
        ("sync", "ha_calendars"),
    ]

    for section, field in required_fields:
        if section not in config or field not in config[section]:
            _LOGGER.error(f"Missing required config: {section}.{field}")
            sys.exit(1)

    return config


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Sync Home Assistant calendars to Office 365"
    )
    parser.add_argument(
        "-c", "--config",
        type=Path,
        default=Path(__file__).parent / "config.yaml",
        help="Path to config file (default: config.yaml)"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    parser.add_argument(
        "-i", "--interactive",
        action="store_true",
        help="Interactive mode for initial authentication (requires browser access)"
    )
    parser.add_argument(
        "-d", "--delete",
        action="store_true",
        help="Delete all synced events from O365 (for resetting/testing)"
    )
    parser.add_argument(
        "--continuous",
        action="store_true",
        help="Run in continuous mode, syncing at configured intervals"
    )
    parser.add_argument(
        "--interval",
        type=int,
        help="Override sync interval in seconds (only with --continuous)"
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    config = load_config(args.config)
    syncer = CalendarSync(config, interactive=args.interactive)

    if args.delete:
        result = syncer.delete_all_synced_events()
        sys.exit(0 if result else 1)
    elif args.continuous:
        # Get sync interval from command line or config
        sync_interval = args.interval or config["sync"].get("sync_interval", 900)
        result = syncer.run_continuous(sync_interval)
        sys.exit(0 if result else 1)
    else:
        result = syncer.sync()
        sys.exit(0 if result else 1)


if __name__ == "__main__":
    main()
