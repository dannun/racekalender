#!/usr/bin/env python3
"""Racekalender → Discord-evenementen. Houdt de Evenementen-lijst van je server
gelijk met public/races.json: maakt nieuwe sessies aan, werkt gewijzigde tijden
bij en verwijdert vervallen sessies. Raakt alleen evenementen aan die dit script
zelf heeft gemaakt (herkenbaar aan 'rk:<id>' onderaan de beschrijving).

Gebruik:  python discord_events.py [--data public/races.json] [--dry-run]
Vereist:  omgevingsvariabelen DISCORD_BOT_TOKEN en DISCORD_GUILD_ID
          Bot-recht: Evenementen beheren (Manage Events)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
API = "https://discord.com/api/v10"
MARK = re.compile(r"rk:([0-9a-f]{16})\s*$")


def api(method: str, path: str, token: str, body: dict | None = None):
    for _ in range(6):
        req = urllib.request.Request(
            API + path, method=method,
            data=json.dumps(body).encode("utf-8") if body is not None else None,
            headers={"Authorization": f"Bot {token}", "Content-Type": "application/json",
                     "User-Agent": "DiscordBot (https://github.com, 1.0) racekalender"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            if e.code == 429:                      # rate limit: wachten en opnieuw
                try:
                    wacht = float(json.loads(e.read()).get("retry_after", 5))
                except Exception:  # noqa: BLE001
                    wacht = 5.0
                time.sleep(min(wacht, 60) + 0.5)
                continue
            raise RuntimeError(f"Discord {method} {path}: HTTP {e.code} {e.read().decode('utf-8', 'replace')[:300]}") from None
    raise RuntimeError(f"Discord {method} {path}: te vaak rate limited")


def uid(s: dict) -> str:
    return hashlib.sha1(f"{s['serie']}|{s['evenement']}|{s['sessie']}|{s['start'][:10]}".encode()).hexdigest()[:16]


def dt(v: str) -> datetime:
    return datetime.fromisoformat(v.replace("Z", "+00:00"))


def gewenst(data: dict, cfg: dict, nu: datetime) -> dict[str, dict]:
    ev = ((cfg.get("discord") or {}).get("evenementen")) or {}
    cats = set(ev.get("categorieen") or ["race", "sprint"])
    alleen = set(ev.get("series") or data["series"].keys()) - set(ev.get("uitsluiten") or [])
    tot = nu + timedelta(days=int(ev.get("dagen_vooruit", 14)))
    fmt = ev.get("titel_formaat", "{serie} · {sessie} · {evenement}")
    out: dict[str, dict] = {}
    for s in data["sessies"]:
        if s["hele_dag"] or s.get("tbc") or s["serie"] not in alleen or s["categorie"] not in cats:
            continue
        start, eind = dt(s["start"]), dt(s["eind"])
        if not (nu + timedelta(minutes=10) < start <= tot):
            continue
        se = dict(data["series"][s["serie"]])
        if str((cfg.get("discord") or {}).get("land", "nl")).lower() == "be" and se.get("zender_be"):
            se["zender"] = se["zender_be"]
        desc = f"📺 {se['zender']['info']}"
        if s.get("klassen"):
            desc += f"\n🏎️ {s['klassen']}"
        if s.get("locatie"):
            desc += f"\n📍 {s['locatie']}"
        if s.get("notitie"):
            desc += f"\nℹ️ {s['notitie']}"
        u = uid(s)
        out[u] = {
            "name": fmt.format(serie=se["naam"], sessie=s["sessie"], evenement=s["evenement"])[:100],
            "scheduled_start_time": start.isoformat(),
            "scheduled_end_time": max(eind, start + timedelta(minutes=5)).isoformat(),
            "description": f"{desc[:950]}\n\nrk:{u}",
            "entity_type": 3,                       # extern (geen spraakkanaal)
            "privacy_level": 2,
            "entity_metadata": {"location": f"📺 {se['zender']['kort']}"[:100]},
        }
    maxn = int(ev.get("max", 60))
    return dict(sorted(out.items(), key=lambda kv: kv[1]["scheduled_start_time"])[:maxn])


def verschilt(best: dict, nieuw: dict) -> bool:
    return (best.get("name") != nieuw["name"]
            or dt(best["scheduled_start_time"]) != dt(nieuw["scheduled_start_time"])
            or not best.get("scheduled_end_time")
            or dt(best["scheduled_end_time"]) != dt(nieuw["scheduled_end_time"])
            or (best.get("description") or "") != nieuw["description"]
            or ((best.get("entity_metadata") or {}).get("location")) != nieuw["entity_metadata"]["location"])


def sync(data: dict, cfg: dict, nu: datetime, call, dry: bool = False) -> dict:
    """call(method, path, body) voert een API-aanroep uit."""
    wil = gewenst(data, cfg, nu)
    bestaand = {}
    for e in call("GET", "/scheduled-events", None) or []:
        m = MARK.search(e.get("description") or "")
        if m:
            bestaand[m.group(1)] = e
    tel = {"nieuw": 0, "bijgewerkt": 0, "verwijderd": 0, "ongewijzigd": 0}
    for u, e in bestaand.items():
        # alleen nog niet gestarte evenementen opruimen; lopende/afgelopen laat Discord zelf verdwijnen
        if u not in wil and e.get("status") == 1 and dt(e["scheduled_start_time"]) > nu + timedelta(minutes=15):
            print(f"- verwijderd: {e['name']}", file=sys.stderr)
            if not dry:
                call("DELETE", f"/scheduled-events/{e['id']}", None)
            tel["verwijderd"] += 1
    for u, n in wil.items():
        e = bestaand.get(u)
        if e is None:
            print(f"+ nieuw: {n['name']} ({n['scheduled_start_time']})", file=sys.stderr)
            if not dry:
                call("POST", "/scheduled-events", n)
            tel["nieuw"] += 1
        elif e.get("status") == 1 and verschilt(e, n):
            print(f"~ bijgewerkt: {n['name']} ({n['scheduled_start_time']})", file=sys.stderr)
            if not dry:
                call("PATCH", f"/scheduled-events/{e['id']}", n)
            tel["bijgewerkt"] += 1
        else:
            tel["ongewijzigd"] += 1
    return tel


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(ROOT / "public" / "races.json"))
    ap.add_argument("--config", default=str(ROOT / "config.yaml"))
    ap.add_argument("--dry-run", action="store_true", help="toon wat er zou gebeuren, wijzig niets")
    a = ap.parse_args()

    data = json.loads(Path(a.data).read_text("utf-8"))
    cfg = yaml.safe_load(Path(a.config).read_text("utf-8"))
    nu = datetime.now(timezone.utc)
    token = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    guild = os.environ.get("DISCORD_GUILD_ID", "").strip()
    if not token or not guild:
        if a.dry_run:
            for n in gewenst(data, cfg, nu).values():
                print(f"{n['scheduled_start_time']}  {n['name']}  [{n['entity_metadata']['location']}]")
            return 0
        print("DISCORD_BOT_TOKEN / DISCORD_GUILD_ID niet ingesteld – evenementen overgeslagen.", file=sys.stderr)
        return 0
    call = lambda m, p, b: api(m, f"/guilds/{guild}{p}", token, b)  # noqa: E731
    tel = sync(data, cfg, nu, call, a.dry_run)
    print("✔ Discord-evenementen: " + ", ".join(f"{v} {k}" for k, v in tel.items()), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
