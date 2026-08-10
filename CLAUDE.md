# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A single-purpose script that checks prices for tracked items on rodentpro.com and sends an
email/SMS notification when a price drops to or below a target. It runs on demand locally, and
automatically once a day via a scheduled GitHub Actions workflow (the source of truth for the
daily schedule — see "Cloud schedule" below).

Repo: https://github.com/Autumn-Chrysanthemum/rodentpro-price-tracker

## Commands

Run a price check manually:
```
python3 price_tracker.py
```

View the run history from a local run:
```
cat logs/price_tracker.log
```

View recent cloud runs and their logs:
```
gh run list --workflow=price_check.yml
gh run view <run-id> --log
```

Trigger a cloud run on demand (outside the daily schedule):
```
gh workflow run price_check.yml
```

No test suite, linter, or build step — this is a single script with no dependencies outside
the Python standard library.

## Cloud schedule

`.github/workflows/price_check.yml` runs `price_tracker.py` daily via `schedule: cron: "0 3 * * *"`
(03:00 UTC = 8:00 PM Pacific Daylight Time; drifts to 7:00 PM during Pacific Standard Time /
winter months, since GitHub Actions cron doesn't account for DST). Credentials are injected as
repo secrets (`GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`, `NOTIFY_EMAIL`, `SMS_GATEWAY`) rather than a
committed `secrets.json` — `load_secrets()` falls back to these environment variables when
`secrets.json` isn't present on disk (see Architecture below).

A local macOS `launchd` agent (`com.nataliavolkova.rodentpro.pricecheck.plist`) was set up
first and later unloaded once the cloud schedule was confirmed working, to avoid duplicate
alerts — the plist file is kept in the repo for reference but is not currently loaded. To change
the tracked items or their target prices, edit `items.json` and push; the cloud run always uses
whatever is on `main`.

## Architecture

- **`price_tracker.py`** — the entire application. Reads `items.json`, fetches each product
  page over HTTP, extracts price data, compares to the target, and notifies on a hit.
- **`items.json`** — the list of tracked items (`name`, `url`, `target_price`). Add/remove
  entries here to change what's tracked; no code changes needed.
- **`secrets.json`** (gitignored, not committed) — Gmail sender credentials (`gmail_address`,
  `gmail_app_password`, `notify_email`, optional `sms_gateway`) used to send the alert email/SMS.
  `gmail_app_password` is a Google-generated App Password, not the account's real password.
  `secrets.example.json` is the committed template. If neither `secrets.json` nor the
  `GMAIL_ADDRESS`/`GMAIL_APP_PASSWORD` environment variables are present, `load_secrets()` returns
  `None` and the script logs a warning and skips email/SMS but still completes the price check.
- **`com.nataliavolkova.rodentpro.pricecheck.plist`** — the launchd job definition (source of
  truth for the copy installed at `~/Library/LaunchAgents/`). Edit this file and re-run
  `launchctl unload` + `launchctl load` to change the schedule.

### Price extraction

rodentpro.com product pages embed a schema.org `Product` block as `<script
type="application/ld+json">` JSON, including `offers.price`. `price_tracker.py` parses that
block directly (regex to isolate the script tag, `html.unescape`, then `json.loads`) rather than
scraping visible HTML/CSS — the JSON-LD is far more stable across site redesigns than markup or
class names. If rodentpro.com ever drops this structured data, `fetch_price()` is the only
function that needs to change.

### Notification paths

- **Email** (working): sent via Gmail SMTP (`smtplib.SMTP_SSL`) using the credentials in
  `secrets.json`, to `notify_email`.
- **SMS** (working): reuses the same Gmail SMTP send, addressed to `secrets["sms_gateway"]`
  instead of `notify_email` — a carrier email-to-SMS gateway address (e.g.
  `<number>@tmomail.net` for T-Mobile). Sends a short version of the alert body with the same
  subject as the email. Skipped if `sms_gateway` isn't set in `secrets.json`.
There was an earlier attempt at a macOS desktop notification via `osascript -e 'display
notification ...'`, later dropped: Terminal.app never registers with Notification Center on this
machine, so the call silently did nothing, and a compiled-`.app` workaround via `osacompile` was
also abandoned (command-line argv didn't reach `on run argv` reliably when launched that way).

### Failure handling

A per-item fetch/parse failure is logged (`logger.error`) but does not stop the other items from
being checked, and does not block the email/SMS for any items that did succeed.
