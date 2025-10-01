"""Home Assistant API client for calendar operations."""

import logging
from datetime import datetime
from typing import Any

import requests

_LOGGER = logging.getLogger(__name__)


class HomeAssistantClient:
    """Client for interacting with Home Assistant calendar API."""

    def __init__(self, url: str, token: str, timezone: str = "Europe/London"):
        """Initialize the HA client."""
        self.url = url.rstrip("/")
        self.token = token
        self.timezone = timezone
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def get_events(
        self,
        calendar_id: str,
        start_date: datetime,
        end_date: datetime
    ) -> list[dict[str, Any]]:
        """
        Get events from a Home Assistant calendar.

        Args:
            calendar_id: The entity ID of the calendar (e.g., 'calendar.home')
            start_date: Start of date range
            end_date: End of date range

        Returns:
            List of event dictionaries
        """
        # Use full entity ID for API call - HA expects the full calendar.xxx format
        entity_id = calendar_id if calendar_id.startswith("calendar.") else f"calendar.{calendar_id}"

        # Format dates for HA API (ISO format)
        start_str = start_date.strftime("%Y-%m-%dT%H:%M:%S")
        end_str = end_date.strftime("%Y-%m-%dT%H:%M:%S")

        url = f"{self.url}/api/calendars/{entity_id}"
        params = {
            "start": start_str,
            "end": end_str,
        }

        try:
            _LOGGER.info(f"Fetching events from {url} with params: {params}")
            response = requests.get(
                url,
                headers=self.headers,
                params=params,
                timeout=30
            )
            response.raise_for_status()

            events = response.json()
            _LOGGER.debug(f"Retrieved {len(events)} events from {calendar_id}")

            # Normalize event format
            normalized_events = []
            for event in events:
                normalized_events.append(self._normalize_event(event))

            return normalized_events

        except requests.exceptions.RequestException as e:
            _LOGGER.error(f"Error fetching events from HA: {e}")
            raise

    def _normalize_event(self, event: dict) -> dict:
        """
        Normalize HA event to a common format.

        Args:
            event: Raw event from HA API

        Returns:
            Normalized event dictionary
        """
        # Parse datetime strings
        start = self._parse_datetime(event.get("start"))
        end = self._parse_datetime(event.get("end"))

        return {
            "uid": event.get("uid", ""),
            "summary": event.get("summary", ""),
            "description": event.get("description", ""),
            "location": event.get("location", ""),
            "start": start,
            "end": end,
            "all_day": self._is_all_day_event(event),
        }

    def _parse_datetime(self, dt_value: Any) -> datetime:
        """
        Parse datetime from various formats, preserving timezone information.

        Args:
            dt_value: Datetime value (could be string, dict, or datetime)

        Returns:
            Datetime object with timezone information using ZoneInfo
        """
        from dateutil import parser
        from zoneinfo import ZoneInfo
        from datetime import timezone

        if isinstance(dt_value, datetime):
            # If already a datetime, ensure it has timezone info with ZoneInfo
            if dt_value.tzinfo is None:
                # Assume configured timezone if none specified
                local_tz = ZoneInfo(self.timezone)
                dt_value = dt_value.replace(tzinfo=local_tz)
            elif not isinstance(dt_value.tzinfo, ZoneInfo):
                # Convert to ZoneInfo if it's using a different timezone type
                local_tz = ZoneInfo(self.timezone)
                dt_value = dt_value.astimezone(local_tz)

            _LOGGER.debug(f"Processed existing datetime: {dt_value} (type: {type(dt_value)}, tzinfo type: {type(dt_value.tzinfo)})")
            return dt_value

        if isinstance(dt_value, dict):
            # Handle HA's datetime dict format
            dt_str = dt_value.get("dateTime") or dt_value.get("date")
        else:
            dt_str = dt_value

        if not dt_str:
            return datetime.now(timezone.utc)

        # Try parsing with dateutil which handles timezones better
        try:
            parsed_dt = parser.parse(dt_str)

            # If no timezone info, assume configured timezone
            if parsed_dt.tzinfo is None:
                local_tz = ZoneInfo(self.timezone)
                parsed_dt = parsed_dt.replace(tzinfo=local_tz)
            else:
                # If dateutil created a timezone, convert it to ZoneInfo if needed
                if not isinstance(parsed_dt.tzinfo, ZoneInfo):
                    # Convert to configured timezone to ensure ZoneInfo
                    local_tz = ZoneInfo(self.timezone)
                    parsed_dt = parsed_dt.astimezone(local_tz)

            _LOGGER.debug(f"Parsed datetime: {parsed_dt} (type: {type(parsed_dt)}, tzinfo type: {type(parsed_dt.tzinfo)})")
            return parsed_dt

        except Exception as e:
            _LOGGER.warning(f"Could not parse datetime: {dt_str}, error: {e}")
            return datetime.now(timezone.utc)

    def _is_all_day_event(self, event: dict) -> bool:
        """
        Determine if event is all-day.

        Args:
            event: Event dictionary

        Returns:
            True if all-day event
        """
        start = event.get("start")
        if isinstance(start, dict):
            return "date" in start and "dateTime" not in start
        return False

    def test_connection(self) -> bool:
        """
        Test connection to Home Assistant.

        Returns:
            True if connection successful
        """
        try:
            url = f"{self.url}/api/"
            response = requests.get(
                url,
                headers=self.headers,
                timeout=10
            )
            response.raise_for_status()
            _LOGGER.info("Successfully connected to Home Assistant")
            return True
        except requests.exceptions.RequestException as e:
            _LOGGER.error(f"Failed to connect to Home Assistant: {e}")
            return False
