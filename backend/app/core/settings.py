"""Global settings: one JSON file in the data directory, admin only.

Everything set up in Admin → Opsætning lives here. Shape and rules from
FamilyLog's settings.py:

* defaults below, then settings.json, then environment overrides
  (ENV_OVERRIDES) - a deployment pins a value from the compose override file
  and it wins over what was saved in the UI. The UI shows such a value as
  locked and names the variable.
* a save merges: only the keys it carries change.
* every value is validated; an unknown key is an error, not a silent drop.
* secrets never go back to the browser: `public()` says whether one is set
  and shows the last characters.
"""
from __future__ import annotations

import json
import os
import re
import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from . import db

DEFAULT_FEEDS = [
    {"name": "DR", "url": "https://www.dr.dk/nyheder/service/feeds/senestenyt"},
    {"name": "TV 2", "url": "https://feeds.services.tv2.dk/api/feeds/nyheder/rss"},
]

DEFAULTS: dict = {
    # ---- general ----
    "publicUrl": "",            # https://dashboard.slq.dk; empty = from the request
    "timezone": "Europe/Copenhagen",
    "homeName": "",             # set in Admin; the middle of Denmark until then
    "homeLat": 56.0,
    "homeLon": 10.0,
    # ---- Google (read only) ----
    "googleClientId": "",
    "googleClientSecret": "",   # never sent back to the browser
    # ---- other apps ----
    "dkliveUrl": "",            # the server reads it: http://<lxc-ip>:4200
    "dkliveLink": "",           # the browser opens it; empty = dkliveUrl
    "familylogUrl": "",         # http://30.11.0.108:8081
    # ---- Nyheder ----
    "newsFeeds": DEFAULT_FEEDS,
    # ---- SLQ DL ----
    "youtubeApiKey": "",        # optional; never sent back to the browser
    # ---- Kameraer ----
    "go2rtcUrl": "",            # the compose file sets this
    # ---- Aktier ----
    "nordnetMode": "off",       # off | api | csv
    "nordnetApiKey": "",        # never sent back to the browser
}

ENV_OVERRIDES = {
    "publicUrl": "APP_PUBLIC_URL",
    "timezone": "APP_TIMEZONE",
    "googleClientId": "APP_GOOGLE_CLIENT_ID",
    "googleClientSecret": "APP_GOOGLE_CLIENT_SECRET",
    "dkliveUrl": "APP_DKLIVE_URL",
    "dkliveLink": "APP_DKLIVE_LINK",
    "familylogUrl": "APP_FAMILYLOG_URL",
    "go2rtcUrl": "APP_GO2RTC_URL",
}

SECRET_KEYS = {"googleClientSecret", "nordnetApiKey", "youtubeApiKey"}
URL_KEYS = {"publicUrl", "dkliveUrl", "dkliveLink", "familylogUrl", "go2rtcUrl"}
TEXT_KEYS = {"googleClientId", "homeName"}
NORDNET_MODES = ("off", "api", "csv")
MAX_FEEDS = 8


class Invalid(ValueError):
    """A value the setup page sent that cannot be stored."""


def path():
    return db.data_dir() / "settings.json"


def _env_pins() -> dict[str, str]:
    """{key: variable} for every key an environment variable pins now."""
    return {k: v for k, v in ENV_OVERRIDES.items() if (os.environ.get(v) or "").strip()}


def _saved() -> dict:
    p = path()
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8-sig"))
            if isinstance(data, dict):
                return {k: v for k, v in data.items() if k in DEFAULTS}
        except (OSError, json.JSONDecodeError):
            pass
    return {}


def load() -> dict:
    out = {**DEFAULTS, **_saved()}
    for key, var in _env_pins().items():
        out[key] = os.environ[var].strip()
    return out


def public() -> dict:
    """What the setup page gets: no secrets, plus which keys are pinned."""
    s = load()
    out = {k: v for k, v in s.items() if k not in SECRET_KEYS}
    for key in SECRET_KEYS:
        value = s.get(key) or ""
        out[f"{key}Set"] = bool(value)
        out[f"{key}Hint"] = f"…{value[-4:]}" if len(value) >= 8 else ""
    out["envPinned"] = _env_pins()
    return out


def _clean_url(key: str, value) -> str:
    value = str(value or "").strip().rstrip("/")
    if value and not re.match(r"^https?://[^\s/]+", value):
        raise Invalid(f"{key}: adressen skal starte med http:// eller https://.")
    return value


def _clean_feeds(value) -> list[dict]:
    if not isinstance(value, list):
        raise Invalid("newsFeeds skal være en liste.")
    out: list[dict] = []
    for item in value:
        if not isinstance(item, dict):
            raise Invalid("Hver nyhedskilde skal have navn og adresse.")
        name = " ".join(str(item.get("name") or "").split())[:40]
        url = _clean_url("newsFeeds", item.get("url"))
        if not url:
            continue
        out.append({"name": name or url, "url": url})
    if len(out) > MAX_FEEDS:
        raise Invalid(f"Højst {MAX_FEEDS} nyhedskilder.")
    return out


def _clean(key: str, value):
    if key in URL_KEYS:
        return _clean_url(key, value)
    if key in TEXT_KEYS or key in SECRET_KEYS:
        return str(value or "").strip()
    if key in ("homeLat", "homeLon"):
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise Invalid(f"{key} skal være et tal.") from None
        limit = 90 if key == "homeLat" else 180
        if abs(number) > limit:
            raise Invalid(f"{key} er uden for kortet.")
        return number
    if key == "newsFeeds":
        return _clean_feeds(value)
    if key == "nordnetMode":
        if value not in NORDNET_MODES:
            raise Invalid("nordnetMode skal være off, api eller csv.")
        return value
    if key == "timezone":
        try:
            ZoneInfo(str(value))
        except (ZoneInfoNotFoundError, ValueError):
            raise Invalid(f"Ukendt tidszone: {value!r}.") from None
        return str(value)
    raise Invalid(f"Ukendt indstilling: {key}.")      # pragma: no cover


def save(patch: dict) -> dict:
    """Merge `patch` into the saved settings and return the public view.

    A secret: absent = unchanged, null = cleared, text = set. A key an
    environment variable pins is refused - saving it would change nothing."""
    unknown = [k for k in patch if k not in DEFAULTS]
    if unknown:
        raise Invalid(f"Ukendt indstilling: {', '.join(sorted(unknown))}.")
    pinned = [k for k in patch if k in _env_pins()]
    if pinned:
        raise Invalid(", ".join(f"{k} er sat af {ENV_OVERRIDES[k]}" for k in pinned)
                      + " i containerens miljø - ret det dér.")
    saved = _saved()
    for key, value in patch.items():
        if key in SECRET_KEYS and value is None:
            saved.pop(key, None)
            continue
        saved[key] = _clean(key, value)
    p = path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(saved, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    tmp.replace(p)
    if "timezone" in patch:
        apply_timezone()
    return public()


def tz() -> ZoneInfo:
    try:
        return ZoneInfo(load().get("timezone") or DEFAULTS["timezone"])
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(DEFAULTS["timezone"])


def apply_timezone() -> None:
    """Make the process's local time the configured zone."""
    name = load().get("timezone") or DEFAULTS["timezone"]
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return
    os.environ["TZ"] = name
    if hasattr(time, "tzset"):
        time.tzset()
