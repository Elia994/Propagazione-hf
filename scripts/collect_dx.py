#!/usr/bin/env python3
"""Read documented public HTTPS DX feeds and keep only verifiably recent spots."""
import datetime as dt
import json
import math
import re
import urllib.request
from pathlib import Path

OUTPUT = Path("data/dx-spots.json")
UTC = dt.timezone.utc
MAX_AGE = dt.timedelta(hours=2)
SOURCES = (
    ("HamQTH", "https://www.hamqth.com/api/v2/spots?limit=200"),
    ("SQ3SWG", "https://skeds.sq3swg.com/api/v1/public/spots?band=hf&limit=200"),
)
MODES = ("FT8", "FT4", "RTTY", "PSK31", "CW", "SSB", "USB", "LSB", "AM")


def parse_time(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        t = dt.datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        return t.replace(tzinfo=UTC) if t.tzinfo is None else t.astimezone(UTC)
    except ValueError:
        return None


def infer_mode(value, comment):
    raw = str(value or "").strip().upper()
    msg = str(comment or "").upper()
    for mode in MODES:
        if re.search(r"\b" + mode + r"\b", msg):
            return "SSB" if mode in ("USB", "LSB") else mode
    if raw in MODES:
        return "SSB" if raw in ("USB", "LSB") else raw
    if raw == "DIGI":
        return "DIGI"
    return "Non indicato"


def normalize(row, source, now):
    try:
        if source == "HamQTH":
            frequency = row.get("freq")
            dx = row.get("dxcall")
            when = row.get("time")
            mode = row.get("mode")
        else:
            frequency = row.get("freqKHz")
            dx = row.get("dx")
            when = row.get("time")
            mode = None
        t = parse_time(when)
        mhz = float(frequency) / 1000
        if not t or not math.isfinite(mhz) or not 1.8 <= mhz <= 30:
            return None
        if not dt.timedelta(minutes=-5) <= now - t <= MAX_AGE:
            return None
        if not isinstance(dx, str) or not (2 <= len(dx) <= 28):
            return None
        spotter = str(row.get("spotter") or "").strip()[:28]
        comment = str(row.get("comment") or "").strip()[:110]
        return {
            "frequency_mhz": round(mhz, 4),
            "mode": infer_mode(mode, comment),
            "dx": dx.strip()[:28],
            "spotter": spotter,
            "utc": t.strftime("%H%M"),
            "comment": comment,
            "source": source,
            "timestamp": t.isoformat(timespec="seconds").replace("+00:00", "Z"),
        }
    except (AttributeError, TypeError, ValueError, OverflowError):
        return None


def parse_response(payload, source, now):
    if not isinstance(payload, dict) or not isinstance(payload.get("spots"), list):
        raise ValueError("Formato JSON non riconosciuto")
    return [spot for row in payload["spots"] if isinstance(row, dict)
            if (spot := normalize(row, source, now)) is not None]


def fetch_json(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "PropagationHF-DXCollector/1.0",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=15) as res:
        return json.load(res)


def main():
    now = dt.datetime.now(UTC)
    incoming, errors, successful_sources = [], [], []
    for name, url in SOURCES:
        try:
            spots = parse_response(fetch_json(url), name, now)
            incoming.extend(spots)
            successful_sources.append(name)
        except (OSError, ValueError) as exc:
            errors.append(f"{name}: {str(exc)[:120]}")
    previous = []
    if OUTPUT.is_file():
        try:
            previous = json.loads(OUTPUT.read_text(encoding="utf-8")).get("spots", [])
        except (OSError, ValueError, TypeError, AttributeError):
            pass
    unique = {}
    for spot in incoming + previous:
        if not isinstance(spot, dict):
            continue
        t = parse_time(spot.get("timestamp"))
        if not t or not dt.timedelta(minutes=-5) <= now - t <= MAX_AGE:
            continue
        try:
            key = (spot["dx"], float(spot["frequency_mhz"]),
                   spot["timestamp"], spot.get("spotter", ""))
        except (KeyError, ValueError, TypeError):
            continue
        unique[key] = spot
    data = {
        "checked_at": now.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "status": "ok" if incoming else ("no_recent" if successful_sources else "unavailable"),
        "new_spots": len(incoming),
        "sources_ok": successful_sources,
        "errors": errors,
        "spots": sorted(unique.values(), key=lambda item: item["timestamp"], reverse=True)[:250],
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("DX check:", len(incoming), "new spots;", len(data["spots"]),
          "total; sources:", successful_sources, "errors:", errors)


if __name__ == "__main__":
    main()
