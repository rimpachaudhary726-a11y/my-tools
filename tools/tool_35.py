#!/usr/bin/env python3
"""
dashboard.py - Aggregate Bitcoin price, London weather, and top‑5 news into a
single HTML dashboard with timestamps, icons, and optional e‑mail notification.

Only Python standard library is used.
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.error
import datetime
import xml.etree.ElementTree as ET
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# --------------------------------------------------------------------------- #
# Configuration (public APIs)
BITCOIN_URL = "https://api.coindesk.com/v1/bpi/currentprice/USD.json"
WEATHER_URL = "https://wttr.in/London?format=j1"
NEWS_RSS_URL = "https://feeds.bbci.co.uk/news/rss.xml"

# --------------------------------------------------------------------------- #
# Helper functions ----------------------------------------------------------- #

def safe_fetch(url, timeout=10):
    """Fetch data from a URL and return raw bytes. Raises RuntimeError on failure."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            if resp.status != 200:
                raise RuntimeError(f"HTTP {resp.status} from {url}")
            return resp.read()
    except urllib.error.URLError as e:
        raise RuntimeError(f"Network error while contacting {url}: {e}") from e
    except Exception as e:
        raise RuntimeError(f"Unexpected error while fetching {url}: {e}") from e


def get_bitcoin_price():
    """Return (price_str, timestamp) or (error_msg, timestamp)."""
    ts = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    try:
        data = safe_fetch(BITCOIN_URL)
        payload = json.loads(data.decode())
        price = payload["bpi"]["USD"]["rate"]
        return f"${price}", ts
    except Exception as e:
        return f"Error: {e}", ts


def get_london_weather():
    """Return (description, temperature°C, timestamp) or (error_msg, None, timestamp)."""
    ts = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    try:
        data = safe_fetch(WEATHER_URL)
        payload = json.loads(data.decode())
        cur = payload["current_condition"][0]
        temp_c = cur["temp_C"]
        desc = cur["weatherDesc"][0]["value"]
        return f"{desc}", f"{temp_c}°C", ts
    except Exception as e:
        return f"Error: {e}", None, ts


def get_top_news(limit=5):
    """Return list of (title, link) or list with a single error tuple."""
    try:
        data = safe_fetch(NEWS_RSS_URL)
        root = ET.fromstring(data)
        items = []
        for item in root.iter('item')[:limit]:
            title = item.findtext('title') or "No title"
            link = item.findtext('link') or "#"
            items.append((title, link))
        if not items:
            return [("No news items found", "#")]
        return items
    except Exception as e:
        return [("Error fetching news: " + str(e), "#")]


def verify_email_env():
    """Check required e‑mail environment variables. Return dict or abort."""
    required = ["EMAIL_SMTP_SERVER", "EMAIL_SMTP_PORT",
                "EMAIL_USER", "EMAIL_PASS", "EMAIL_TO"]
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        sys.stderr.write(
            f"Missing required email environment variables: {', '.join(missing)}\n")
        sys.exit(1)

    cfg = {
        "smtp_server": os.getenv("EMAIL_SMTP_SERVER"),
        "smtp_port": int(os.getenv("EMAIL_SMTP_PORT")),
        "user": os.getenv("EMAIL_USER"),
        "password": os.getenv("EMAIL_PASS"),
        "to": os.getenv("EMAIL_TO"),
    }
    return cfg


def send_email(subject, html_body, cfg):
    """Send an HTML e‑mail using the supplied config."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = cfg["user"]
    msg["To"] = cfg["to"]
    part = MIMEText(html_body, "html")
    msg.attach(part)

    try:
        with smtplib.SMTP_SSL(cfg["smtp_server"], cfg["smtp_port"], timeout=15) as server:
            server.login(cfg["user"], cfg["password"])
            server.send_message(msg)
    except Exception as e:
        sys.stderr.write(f"Failed to send e‑mail: {e}\n")
        # Continue without aborting


def build_html(bitcoin, weather, news):
    """Create a self‑contained HTML string."""
    now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Live Dashboard – {now}</title>
<style>
body {{font-family: Arial, sans-serif; background:#f4f4f4; margin:0; padding:1rem;}}
section {{background:#fff; padding:1rem; margin-bottom:1rem; border-radius:5px; box-shadow:0 2px 4px rgba(0,0,0,0.1);}}
h2 {{margin-top:0;}}
footer {{font-size:0.8rem; color:#666; text-align:center;}}
ul {{list-style:none; padding:0;}}
li {{margin:0.5rem 0;}}
a {{color:#0066cc; text-decoration:none;}}
a:hover {{text-decoration:underline;}}
</style>
</head>
<body>
<h1>📊 Live Dashboard</h1>
<p>Generated at <strong>{now}</strong></p>

<section>
<h2>💰 Bitcoin Price (USD)</h2>
<p>{bitcoin[0]}</p>
<p><small>Fetched at {bitcoin[1]}</small></p>
</section>

<section>
<h2>🌤️ London Weather</h2>
<p>{weather[0]}</p>
"""
    if weather[1] is not None:
        html += f"<p>Temperature: {weather[1]}</p>\n"
    html += f"<p><small>Fetched at {weather[2]}</small></p>\n</section>\n"

    html += """<section>
<h2>🗞️ Top 5 News</h2>
<ul>
"""
    for title, link in news:
        safe_title = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        html += f'<li><a href="{link}" target="_blank">{safe_title}</a></li>\n'
    html += """</ul>
</section>
<footer>Dashboard generated by dashboard.py – © 2026</footer>
</body>
</html>"""
    return html


# --------------------------------------------------------------------------- #
# Main ---------------------------------------------------------------------- #

def main():
    parser = argparse.ArgumentParser(
        description="Aggregate Bitcoin price, London weather, and top‑5 news into an HTML dashboard.")
    parser.add_argument("-o", "--output", default="dashboard.html",
                        help="Path to the generated HTML file (default: dashboard.html)")
    parser.add_argument("--email", action="store_true",
                        help="Send the generated dashboard via e‑mail (requires env vars)")
    args = parser.parse_args()

    # Fetch data (network errors are handled inside each function)
    bitcoin = get_bitcoin_price()
    weather = get_london_weather()
    news = get_top_news()

    # Build HTML
    html = build_html(bitcoin, weather, news)

    # Write to file
    try:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"Dashboard written to {args.output}")
    except Exception as e:
        sys.stderr.write(f"Failed to write dashboard file: {e}\n")
        sys.exit(1)

    # Optional e‑mail
    if args.email:
        cfg = verify_email_env()
        subject = f"Live Dashboard – {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
        send_email(subject, html, cfg)
        print("Dashboard e‑mail sent (if configuration is correct).")


if __name__ == "__main__":
    main()