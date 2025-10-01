"""Office 365 API client for calendar operations."""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from O365 import Account, FileSystemTokenBackend

_LOGGER = logging.getLogger(__name__)


class Office365Client:
    """Client for interacting with Office 365 calendar API."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        tenant_id: str = "common",
        calendar_id: str = "primary",
        user_principal_name: str | None = None
    ):
        """Initialize the O365 client."""
        self.client_id = client_id
        self.client_secret = client_secret
        self.tenant_id = tenant_id
        self.calendar_id = calendar_id
        self.user_principal_name = user_principal_name

        # Setup token storage
        token_path = Path(__file__).parent / ".tokens"
        token_path.mkdir(exist_ok=True)
        token_backend = FileSystemTokenBackend(
            token_path=token_path,
            token_filename="o365_token.txt"
        )

        # Create account - using authorization flow (confidential client) for delegated permissions
        # Authorization flow requires client_secret and uses redirect URI
        # User visits URL and gets redirected back with authorization code

        # Use authorization flow with client credentials
        # The Azure app is configured as confidential client requiring client_secret
        credentials = (client_id, client_secret)

        # Define minimal scopes using scope helpers - only calendar access
        self.scopes = ['calendar_all']  # This maps to 'Calendars.ReadWrite'

        self.account = Account(
            credentials,  # Use tuple with client_id and client_secret
            auth_flow_type="authorization",  # Authorization code flow
            tenant_id=tenant_id,
            token_backend=token_backend,
            # Don't pass scopes here - deprecated in 2.1+, only pass to authenticate()
        )

        self.schedule = None
        self.calendar = None

    def authenticate(self, interactive: bool = False) -> bool:
        """
        Authenticate with Office 365 using device code flow.

        Args:
            interactive: Allow interactive authentication (can run in container!)

        Returns:
            True if authentication successful
        """
        try:
            if not self.account.is_authenticated:
                if not interactive:
                    _LOGGER.error("Not authenticated and interactive mode disabled")
                    _LOGGER.error("Run with --interactive flag to authenticate")
                    _LOGGER.error("You can authenticate from inside the container!")
                    return False

                _LOGGER.info("=" * 70)
                _LOGGER.info("AUTHENTICATING WITH DEVICE CODE FLOW")
                _LOGGER.info("=" * 70)
                _LOGGER.info("")
                _LOGGER.info("OAuth authorization flow:")
                _LOGGER.info("1. Click the URL below to authorize the application")
                _LOGGER.info("2. After accepting permissions, you'll see a white screen")
                _LOGGER.info("3. Copy the ENTIRE URL from your browser's address bar")
                _LOGGER.info("4. Paste it back here when prompted")
                _LOGGER.info("")
                _LOGGER.info(f"Requesting permissions: {', '.join(self.scopes)} (calendar access only)")
                _LOGGER.info("")

                # Pass scopes explicitly to authenticate method to override any defaults
                if not self.account.authenticate(requested_scopes=self.scopes):
                    _LOGGER.error("Failed to authenticate with Office 365")
                    return False

                _LOGGER.info("")
                _LOGGER.info("=" * 70)
                _LOGGER.info("AUTHENTICATION SUCCESSFUL!")
                _LOGGER.info("=" * 70)
                _LOGGER.info("Token saved. You can now run without --interactive flag.")
                _LOGGER.info("")

            self.schedule = self.account.schedule()

            # Get the calendar
            if self.calendar_id == "primary":
                self.calendar = self.schedule.get_default_calendar()
            else:
                self.calendar = self.schedule.get_calendar(calendar_id=self.calendar_id)

            if not self.calendar:
                _LOGGER.error(f"Could not access calendar: {self.calendar_id}")
                return False

            _LOGGER.info(f"Successfully authenticated and accessed calendar: {self.calendar.name}")
            return True

        except Exception as e:
            _LOGGER.error(f"Authentication error: {e}", exc_info=True)
            return False

    def get_synced_events(
        self,
        start_date: datetime,
        end_date: datetime,
        prefixes: list[str]
    ) -> dict[str, dict[str, Any]]:
        """
        Get events that were synced from HA (identified by prefixes).

        Args:
            start_date: Start of date range
            end_date: End of date range
            prefixes: List of prefixes to identify synced events

        Returns:
            Dictionary mapping UID to event data
        """
        if not self.calendar:
            raise RuntimeError("Not authenticated. Call authenticate() first.")

        try:
            # Get events in date range using calendarView
            # The calendarView endpoint handles date filtering automatically via start_recurring/end_recurring
            # Don't use additional $filter queries as they conflict with calendarView
            # Use a larger batch size and handle pagination properly
            events = self.calendar.get_events(
                include_recurring=True,
                start_recurring=start_date,  # This handles the date filtering for calendarView
                end_recurring=end_date,      # This handles the date filtering for calendarView
                batch=999,  # Use maximum batch size to reduce pagination
                limit=None  # Remove any limit to get all events
            )

            _LOGGER.debug(f"Requested events from {start_date} to {end_date} with batch size 999, no limit")

            synced_events = {}
            total_events = 0
            prefixed_events = 0

            # Ensure we iterate through ALL events by properly handling pagination
            # Convert to list to force complete iteration through all pages
            all_events = list(events)
            _LOGGER.info(f"Retrieved {len(all_events)} total events from O365 after pagination")

            for event in all_events:
                total_events += 1
                start_str = event.start.strftime('%Y-%m-%d %H:%M') if event.start else 'No start'
                end_str = event.end.strftime('%Y-%m-%d %H:%M') if event.end else 'No end'
                _LOGGER.debug(f"Examining O365 event: '{event.subject}' ({start_str} - {end_str})")

                # Check if event has any of our prefixes
                if event.subject and any(event.subject.startswith(prefix) for prefix in prefixes):
                    prefixed_events += 1
                    # Try to get UID from extended properties
                    # Debug: check what's in the event body before getting UID
                    body_preview = (event.body[:200] + '...') if event.body and len(event.body) > 200 else (event.body or 'No body')
                    _LOGGER.debug(f"Event body for '{event.subject}': {body_preview}")

                    uid = self._get_event_uid(event)
                    _LOGGER.info(f"Found existing synced event: {event.subject} ({start_str} - {end_str}) (UID: {uid}, O365 ID: {event.object_id})")
                    if uid:
                        if uid in synced_events:
                            _LOGGER.warning(f"Duplicate UID found: {uid} for event '{event.subject}' - this indicates duplicate events in O365")
                        synced_events[uid] = self._normalize_event(event)

            _LOGGER.info(f"Retrieved {total_events} total events from O365, {prefixed_events} with prefixes {prefixes}, {len(synced_events)} with valid UIDs")
            return synced_events

        except Exception as e:
            _LOGGER.error(f"Error fetching O365 events: {e}", exc_info=True)
            raise

    def create_event(self, event_data: dict, uid: str) -> Any:
        """
        Create a new event in Office 365.

        Args:
            event_data: Event data dictionary
            uid: Unique ID from Home Assistant

        Returns:
            Created event object
        """
        if not self.calendar:
            raise RuntimeError("Not authenticated. Call authenticate() first.")

        try:
            event = self.calendar.new_event()
            self._populate_event(event, event_data)

            # Store UID in extended properties for tracking
            self._set_event_uid(event, uid)

            event.save()
            _LOGGER.debug(f"Created event: {event.subject}")
            # Verify UID was stored
            stored_uid = self._get_event_uid(event)
            _LOGGER.debug(f"Verified stored UID for '{event.subject}': {stored_uid} (expected: {uid})")
            return event

        except Exception as e:
            _LOGGER.error(f"Error creating event: {e}", exc_info=True)
            raise

    def update_event(self, event_id: str, event_data: dict) -> Any:
        """
        Update an existing event in Office 365.

        Args:
            event_id: O365 event ID
            event_data: Updated event data

        Returns:
            Updated event object
        """
        if not self.calendar:
            raise RuntimeError("Not authenticated. Call authenticate() first.")

        try:
            # Get the event
            event = self.calendar.get_event(event_id)
            if not event:
                _LOGGER.error(f"Event not found: {event_id}")
                return None

            # Update fields
            self._populate_event(event, event_data)

            event.save()
            _LOGGER.debug(f"Updated event: {event.subject}")
            return event

        except Exception as e:
            _LOGGER.error(f"Error updating event {event_id}: {e}", exc_info=True)
            raise

    def delete_event(self, event_id: str) -> bool:
        """
        Delete an event from Office 365.

        Args:
            event_id: O365 event ID

        Returns:
            True if deleted successfully
        """
        if not self.calendar:
            raise RuntimeError("Not authenticated. Call authenticate() first.")

        try:
            event = self.calendar.get_event(event_id)
            if not event:
                _LOGGER.warning(f"Event not found for deletion: {event_id}")
                return False

            event.delete()
            _LOGGER.debug(f"Deleted event: {event.subject}")
            return True

        except Exception as e:
            _LOGGER.error(f"Error deleting event {event_id}: {e}", exc_info=True)
            raise

    def _populate_event(self, event: Any, data: dict) -> None:
        """
        Populate event object with data.

        Args:
            event: O365 event object
            data: Event data dictionary
        """
        event.subject = data.get("summary", "")
        event.body = data.get("description", "")
        event.location = data.get("location", "")

        # Set times
        start = data.get("start")
        end = data.get("end")

        if data.get("all_day"):
            event.is_all_day = True

        if start:
            _LOGGER.debug(f"Setting event start time: {start} (type: {type(start)}, tzinfo: {getattr(start, 'tzinfo', None)})")
            event.start = start
        if end:
            _LOGGER.debug(f"Setting event end time: {end} (type: {type(end)}, tzinfo: {getattr(end, 'tzinfo', None)})")
            event.end = end

    def _normalize_event(self, event: Any) -> dict:
        """
        Normalize O365 event to common format.

        Args:
            event: O365 event object

        Returns:
            Normalized event dictionary
        """
        return {
            "id": event.object_id,
            "uid": self._get_event_uid(event),
            "summary": event.subject or "",
            "description": event.body or "",
            "location": event.location.get("displayName", "") if event.location else "",
            "start": event.start,
            "end": event.end,
            "all_day": event.is_all_day,
        }

    def _set_event_uid(self, event: Any, uid: str) -> None:
        """
        Store UID in event's description.

        Args:
            event: O365 event object
            uid: UID to store
        """
        # Store UID in description as primary method
        try:
            current_description = event.body or ""
            uid_marker = f"[HA_UID:{uid}]"
            if uid_marker not in current_description:
                # Add UID marker at the end of description
                if current_description.strip():
                    event.body = current_description + f"\n\n{uid_marker}"
                else:
                    event.body = uid_marker
                _LOGGER.debug(f"Added UID to description: {uid}")
        except Exception as e:
            _LOGGER.warning(f"Could not add UID to description: {e}")

    def _get_event_uid(self, event: Any) -> str | None:
        """
        Get UID from event's description.

        Args:
            event: O365 event object

        Returns:
            UID if found, None otherwise
        """
        try:
            # Try to extract UID from description first
            if event.body:
                import re
                uid_match = re.search(r'\[HA_UID:([^\]]+)\]', event.body)
                if uid_match:
                    uid = uid_match.group(1)
                    _LOGGER.debug(f"Found HA_UID in description: {uid}")
                    return uid

            # Fallback: use O365 object_id if no UID stored
            # This is for backwards compatibility with events created before UID tracking
            _LOGGER.debug(f"No HA_UID found for '{event.subject}', using fallback: {event.object_id}")
            return event.object_id

        except Exception as e:
            _LOGGER.warning(f"Could not get UID property for '{event.subject}': {e}")
            return event.object_id
