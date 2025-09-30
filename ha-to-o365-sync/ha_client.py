"""Home Assistant API client for calendar operations."""

import logging
from datetime import datetime
from typing import Any

import requests

_LOGGER = logging.getLogger(__name__)


class HomeAssistantClient:
    """Client for interacting with Home Assistant calendar API."""

    def __init__(self, url: str, token: str):
        """Initialize the HA client."""
        self.url = url.rstrip("/")
        self.token = token
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
        Parse datetime from various formats.

        Args:
            dt_value: Datetime value (could be string, dict, or datetime)

        Returns:
            Datetime object
        """
        if isinstance(dt_value, datetime):
            return dt_value

        if isinstance(dt_value, dict):
            # Handle HA's datetime dict format
            dt_str = dt_value.get("dateTime") or dt_value.get("date")
        else:
            dt_str = dt_value

        if not dt_str:
            return datetime.utcnow()

        # Try parsing ISO format
        try:
            # Remove timezone info for simplicity (we'll use UTC)
            if "+" in dt_str:
                dt_str = dt_str.split("+")[0]
            if "Z" in dt_str:
                dt_str = dt_str.replace("Z", "")

            # Try with microseconds
            try:
                return datetime.strptime(dt_str, "%Y-%m-%dT%H:%M:%S.%f")
            except ValueError:
                # Try without microseconds
                return datetime.strptime(dt_str, "%Y-%m-%dT%H:%M:%S")

        except ValueError:
            # Try date-only format
            try:
                return datetime.strptime(dt_str, "%Y-%m-%d")
            except ValueError:
                _LOGGER.warning(f"Could not parse datetime: {dt_str}")
                return datetime.utcnow()

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
