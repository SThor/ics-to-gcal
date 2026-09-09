# ICS → Google Calendar Importer

A small Windows tool: drop a `.ics` file onto it (or double-click and pick a
file) and it imports every event into your primary Google Calendar. Re-running
on the same file is safe — events are matched by their iCalendar UID and
existing matching events are updated instead of duplicated.

## 1. One-time Google Cloud setup (free)

1. Go to https://console.cloud.google.com/ and create a new project (any name).
2. In the left menu: **APIs & Services → Library** → search "Google Calendar API" → **Enable**.
3. **APIs & Services → OAuth consent screen**:
   - User type: **External**.
   - Fill app name / support email / developer email, save through the wizard.
   - On the "Test users" step, add your own Google account email.
   - Publishing status can stay "Testing" — that's fine for personal use.
4. **APIs & Services → Credentials → + Create Credentials → OAuth client ID**:
   - Application type: **Desktop app**.
   - Name it anything, click **Create**.
   - Click **Download JSON**.
5. Rename the downloaded file to `client_secret.json` and place it in this
   project folder next to `import_ics.py` — and later, next to the built `.exe`.

## 2. Install dependencies

```powershell
uv sync
```

## 3. Run it directly (no build needed)

```powershell
uv run python import_ics.py path\to\file.ics
```

The first run opens a browser window to sign in and grant calendar access.
A `token.json` is cached under `%LOCALAPPDATA%\ics-to-gcal\` so you won't be
asked again. If the OAuth app remains in **Testing**, Google refresh tokens
expire after seven days; move the app to **In production** for a long-lived
grant (the unverified-app warning may still appear).

## 4. Build a standalone .exe

```powershell
uv add --dev pyinstaller
uv run build
```

The executable is created at `dist\ics-to-gcal\ics-to-gcal.exe`, and the build
script copies `client_secret.json` there automatically. This folder build
starts faster than a single-file executable.

Create a Desktop shortcut to `ics-to-gcal.exe`. You can then:

- **Drag and drop** a `.ics` file onto the Desktop shortcut/exe to import it, or
- **Double-click** the exe and pick a file from the dialog that appears.
- Set the exe as the default application for `.ics` files, so that double-clicking any `.ics` file will automatically import it into Google Calendar.

## Notes / limitations

- Only `VEVENT` entries are imported (no alarms/reminders, todos, or timezone
  overrides beyond basic UTC/local conversion).
- Recurring events (`RRULE`) are carried over, but per-instance exceptions
  (`EXDATE`/modified occurrences) are not specially handled.
- The OAuth consent screen may show an "unverified app" warning since this is
   a personal-use client — click **Advanced → Go to (app name)** to continue.
