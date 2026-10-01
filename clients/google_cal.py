"""
clients/google_cal.py — Google Calendar API client for creating Meet links.

Credentials/config:
  GOOGLE_SERVICE_ACCOUNT_JSON   path to service account JSON key file
  GOOGLE_CALENDAR_DELEGATE      email of the user to impersonate (domain-wide delegation)
"""

import os
import requests

TIMEOUT = 15
_SCOPES = ["https://www.googleapis.com/auth/calendar"]


def _get_token() -> str:
    """Obtain a Google OAuth2 access token via service account + domain-wide delegation."""
    try:
        from google.oauth2 import service_account
        import google.auth.transport.requests as google_requests

        sa_file = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
        delegate = os.environ["GOOGLE_CALENDAR_DELEGATE"]

        creds = service_account.Credentials.from_service_account_file(sa_file, scopes=_SCOPES)
        creds = creds.with_subject(delegate)
        creds.refresh(google_requests.Request())
        return creds.token
    except ImportError:
        # TODO: pip install google-auth google-auth-httplib2
        raise RuntimeError(
            "google-auth not installed. Run: pip install google-auth google-auth-httplib2"
        )


def create_event_with_meet(
    summary: str,
    start_utc: str,
    end_utc: str,
    attendee_emails: list[str],
    request_id: str,
) -> dict:
    """
    Create a Google Calendar event with a Meet link.
    start_utc / end_utc: ISO 8601 format, e.g. '2025-01-15T10:00:00Z'
    """
    token = _get_token()
    r = requests.post(
        "https://www.googleapis.com/calendar/v3/calendars/primary/events",
        params={"conferenceDataVersion": 1},
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={
            "summary": summary,
            "start": {"dateTime": start_utc, "timeZone": "UTC"},
            "end": {"dateTime": end_utc, "timeZone": "UTC"},
            "attendees": [{"email": e} for e in attendee_emails],
            "conferenceData": {
                "createRequest": {"requestId": request_id, "conferenceSolutionKey": {"type": "hangoutsMeet"}}
            },
        },
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return r.json()
