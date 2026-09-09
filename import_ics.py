"""Import events from a .ics file into Google Calendar using the Calendar API's
events.import method (dedupes by iCalUID, so re-running is safe)."""
import datetime as dt
import os
import sys

from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from icalendar import Calendar

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]

# Files live in %LOCALAPPDATA%\ics-to-gcal so the packaged .exe can write there
# even when it's run from the Desktop or another read-only-ish location.
APP_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "ics-to-gcal")
TOKEN_PATH = os.path.join(APP_DIR, "token.json")


def app_base_dir():
    """Directory the client_secret.json is expected to live in."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def get_credentials():
    os.makedirs(APP_DIR, exist_ok=True)
    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError:
                creds = None
                os.remove(TOKEN_PATH)
        else:
            creds = None
        if creds is None:
            client_secret_path = os.path.join(app_base_dir(), "client_secret.json")
            if not os.path.exists(client_secret_path):
                raise SystemExit(
                    f"Missing {client_secret_path}\n"
                    "Download your Google Cloud OAuth client secret and place it "
                    "next to this program as 'client_secret.json'."
                )
            flow = InstalledAppFlow.from_client_secrets_file(client_secret_path, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_PATH, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
    return creds


def show_message(title, message, error=False):
    """Show feedback when the app is launched without a console."""
    import tkinter as tk
    from tkinter import messagebox

    root = tk.Tk()
    root.withdraw()
    try:
        if error:
            messagebox.showerror(title, message, parent=root)
        else:
            messagebox.showinfo(title, message, parent=root)
    finally:
        root.destroy()


def pick_ics_file():
    if len(sys.argv) > 1:
        return sys.argv[1]
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    try:
        return filedialog.askopenfilename(
            title="Choose a .ics file to import",
            filetypes=[("iCalendar files", "*.ics"), ("All files", "*.*")],
            parent=root,
        )
    finally:
        root.destroy()


def to_event_datetime(value):
    """Convert an icalendar date/datetime value to a Google Calendar event date field."""
    if isinstance(value, dt.datetime):
        if value.tzinfo is None:
            value = value.astimezone()  # assume local system timezone
        return {"dateTime": value.isoformat()}
    return {"date": value.isoformat()}


def event_time_zone(component, property_name):
    property_value = component.get(property_name)
    if property_value is None:
        return None
    time_zone = property_value.params.get("TZID")
    if time_zone:
        return str(time_zone)
    value = property_value.dt
    if isinstance(value, dt.datetime) and value.tzinfo is not None:
        return getattr(value.tzinfo, "key", None) or "UTC"
    return "UTC"


def build_event_body(component):
    dtstart = component.get("dtstart")
    uid = component.get("uid")
    if dtstart is None:
        raise ValueError("VEVENT is missing DTSTART")
    if uid is None:
        raise ValueError("VEVENT is missing UID")

    start_value = dtstart.dt
    body = {
        "iCalUID": str(uid),
        "summary": str(component.get("summary", "")),
        "start": to_event_datetime(start_value),
    }
    dtend = component.get("dtend")
    if dtend is not None:
        body["end"] = to_event_datetime(dtend.dt)
    else:
        duration = component.get("duration")
        if duration is not None:
            body["end"] = to_event_datetime(start_value + duration.dt)
        elif isinstance(start_value, dt.date) and not isinstance(start_value, dt.datetime):
            body["end"] = to_event_datetime(start_value + dt.timedelta(days=1))
        else:
            body["end"] = body["start"]

    description = component.get("description")
    if description:
        body["description"] = str(description)
    location = component.get("location")
    if location:
        body["location"] = str(location)

    rrule = component.get("rrule")
    if rrule:
        body["recurrence"] = [f"RRULE:{rrule.to_ical().decode()}"]
        if isinstance(start_value, dt.datetime):
            time_zone = event_time_zone(component, "dtstart")
            if time_zone:
                body["start"]["timeZone"] = time_zone
                body["end"]["timeZone"] = event_time_zone(component, "dtend") or time_zone

    return body


def import_or_update_event(service, body):
    calendar_id = "primary"
    matches = service.events().list(
        calendarId=calendar_id,
        iCalUID=body["iCalUID"],
        maxResults=250,
        showDeleted=False,
    ).execute().get("items", [])
    if not matches:
        service.events().import_(calendarId=calendar_id, body=body).execute()
        return 0, 1

    master_matches = [match for match in matches if "recurringEventId" not in match]
    for match in master_matches:
        patch_body = {key: value for key, value in body.items() if key != "iCalUID"}
        for field in ("description", "location", "recurrence"):
            if field not in body:
                patch_body[field] = None
        service.events().patch(
            calendarId=calendar_id,
            eventId=match["id"],
            body=patch_body,
        ).execute()
    if not master_matches:
        service.events().import_(calendarId=calendar_id, body=body).execute()
        return 0, 1
    return len(master_matches), 0


def main():
    try:
        ics_path = pick_ics_file()
        if not ics_path:
            return
        if not os.path.exists(ics_path):
            raise RuntimeError(f"File not found: {ics_path}")

        with open(ics_path, "rb") as f:
            cal = Calendar.from_ical(f.read())

        events = [
            c for c in cal.walk()
            if c.name == "VEVENT" and c.get("recurrence-id") is None
        ]
        if not events:
            show_message("ICS to Google Calendar", "No calendar events were found in this file.")
            return

        creds = get_credentials()
        service = build("calendar", "v3", credentials=creds)

        imported = 0
        updated = 0
        failures = []
        for component in events:
            label = str(component.get("summary", "(untitled event)"))
            try:
                body = build_event_body(component)
                updated_count, imported_count = import_or_update_event(service, body)
                updated += updated_count
                imported += imported_count
            except Exception as exc:  # noqa: BLE001 - report and continue with remaining events
                failures.append(f"{label}: {exc}")

        if failures:
            details = "\n".join(failures[:3])
            if len(failures) > 3:
                details += f"\n...and {len(failures) - 3} more."
            show_message(
                "Import completed with errors",
                f"Imported {imported} event(s) and updated {updated} event(s).\n\n"
                f"{len(failures)} event(s) failed:\n{details}",
                error=True,
            )
        else:
            show_message(
                "Import complete",
                f"Imported {imported} event(s) and updated {updated} event(s) in Google Calendar.",
            )
    except SystemExit as exc:
        show_message("Import failed", str(exc), error=True)
    except Exception as exc:  # noqa: BLE001 - show unexpected errors in the no-console app
        show_message("Import failed", str(exc), error=True)


if __name__ == "__main__":
    main()
