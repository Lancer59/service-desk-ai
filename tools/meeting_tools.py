"""
tools/meeting_tools.py — Calendar and meeting creation tools.

Covers: Teams/Outlook calendar events, Google Meet, Zoom meetings.
"""

import os
import uuid
from langchain.tools import tool
from pydantic import BaseModel, Field


class TeamsMeetingInput(BaseModel):
    subject: str = Field(description="Meeting subject/title")
    start_utc: str = Field(description="Start time in ISO 8601 UTC, e.g. 2025-01-15T10:00:00")
    end_utc: str = Field(description="End time in ISO 8601 UTC, e.g. 2025-01-15T11:00:00")
    attendee_emails: list[str] = Field(description="List of attendee email addresses")


class GoogleMeetInput(BaseModel):
    summary: str = Field(description="Meeting title/summary")
    start_utc: str = Field(description="Start time in ISO 8601 UTC")
    end_utc: str = Field(description="End time in ISO 8601 UTC")
    attendee_emails: list[str] = Field(description="List of attendee email addresses")


class ZoomMeetingInput(BaseModel):
    topic: str = Field(description="Zoom meeting topic/title")
    start_utc: str = Field(description="Start time in ISO 8601 UTC, e.g. 2025-01-15T10:00:00Z")
    duration_minutes: int = Field(default=60, description="Duration in minutes")


@tool("calendar_tool", args_schema=TeamsMeetingInput)
def calendar_tool(
    subject: str,
    start_utc: str,
    end_utc: str,
    attendee_emails: list[str],
) -> dict:
    """
    Create an Outlook calendar event with a Teams meeting link.
    Returns the Teams join URL and calendar event link.
    """
    try:
        from clients.graph import create_teams_meeting

        organizer = os.environ.get("GRAPH_ORGANIZER_USER", "")
        if not organizer:
            return {"success": False, "error": "GRAPH_ORGANIZER_USER env var not set."}

        payload = {
            "subject": subject,
            "start": {"dateTime": start_utc, "timeZone": "UTC"},
            "end": {"dateTime": end_utc, "timeZone": "UTC"},
            "attendees": [
                {"emailAddress": {"address": email}, "type": "required"}
                for email in attendee_emails
            ],
            "isOnlineMeeting": True,
            "onlineMeetingProvider": "teamsForBusiness",
        }

        event = create_teams_meeting(organizer, payload)
        return {
            "success": True,
            "event_id": event.get("id", ""),
            "teams_join_url": event.get("onlineMeeting", {}).get("joinUrl", ""),
            "calendar_url": event.get("webLink", ""),
            "subject": subject,
            "start": start_utc,
            "end": end_utc,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool("create_google_meet", args_schema=GoogleMeetInput)
def create_google_meet(
    summary: str,
    start_utc: str,
    end_utc: str,
    attendee_emails: list[str],
) -> dict:
    """
    Create a Google Calendar event with a Google Meet link.
    Returns the Meet join URL.
    """
    try:
        from clients.google_cal import create_event_with_meet

        request_id = str(uuid.uuid4())
        event = create_event_with_meet(summary, start_utc, end_utc, attendee_emails, request_id)
        return {
            "success": True,
            "meet_url": event.get("hangoutLink", ""),
            "event_id": event.get("id", ""),
            "summary": summary,
            "start": start_utc,
            "end": end_utc,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool("create_zoom_meeting", args_schema=ZoomMeetingInput)
def create_zoom_meeting(topic: str, start_utc: str, duration_minutes: int = 60) -> dict:
    """
    Create a Zoom meeting and return the join URL.
    """
    try:
        from clients.zoom import create_meeting

        meeting = create_meeting(topic, start_utc, duration_minutes)
        return {
            "success": True,
            "join_url": meeting.get("join_url", ""),
            "meeting_id": meeting.get("id", ""),
            "topic": topic,
            "start": start_utc,
            "duration_minutes": duration_minutes,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
