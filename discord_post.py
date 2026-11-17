#!/usr/bin/env python3
"""Racekalender → Discord. Plaatst via een webhook een overzicht van de komende
week of van vandaag, op basis van public/races.json (gemaakt door build.py).

Gebruik:  python discord_post.py --mode week|dag [--data public/races.json] [--dry-run]
Webhook:  omgevingsvariabele DISCORD_WEBHOOK_URL
Tijden staan als Discord-tijdstempel in het bericht: iedereen ziet zijn eigen lokale tijd.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parent
DAGEN = ["Maandag", "Dinsdag", "Woensdag", "Donderdag", "Vrijdag", "Zaterdag", "Zondag"]
MAANDEN = ["januari", "februari", "maart", "april", "mei", "juni", "juli", "augustus",
           "september", "oktober", "november", "december"]
MAX_DESC, MAX_MSG, MAX_EMBEDS = 3900, 5500, 10


def dag_naam(d: date) -> str:
    return f"{DAGEN[d.weekday()]} {d.day} {MAANDEN[d.month - 1]}"


def regel(s: dict, series: dict, start: datetime | None) -> str:
    se = series.get(s["serie"], {"naam": s["serie"], "zender": {"kort": "?"}})
    zender = se["zender"]["kort"]
    if s["hele_dag"]:
        eind = date.fromisoformat(s["eind"]) - timedelta(days=1)
        tm = f" t/m {DAGEN[eind.weekday()][:2].lower()} {eind.day} {MAANDEN[eind.month - 1][:3]}" if eind.isoformat() != s["start"] else ""
        wanneer = "🗓️" + (tm or " hele dag") if s["categorie"] == "weekend" else "🕓 tijd volgt"
    else:
        wanneer = f"<t:{int(start.timestamp())}:t>"
    vet = "**" if s["categorie"] in ("race", "sprint") else ""
    kl = f" · 🏎️ {s['klassen']}" if s.get("klassen") else ""
    return f"{wanneer} · **{se['naam']}** {vet}{s['sessie']}{vet} · {s['evenement']}{kl} · 📺 {zender}"


def bouw_berichten(data: dict, cfg: dict, mode: str, nu: datetime) -> list[dict]:
    tz = ZoneInfo(data.get("tijdzone", "Europe/Amsterdam"))
    dc = cfg.get("discord") or {}
    cats = set(dc.get("categorieen") or ["race", "sprint", "kwalificatie", "weekend"])
    alleen = set(dc.get("series") or data["series"].keys())
    vandaag = nu.astimezone(tz).date()
    tot = vandaag + timedelta(days=7 if mode == "week" else 1)

    per_dag: dict[date, list[tuple]] = {}
    for s in data["sessies"]:
        if s["serie"] not in alleen or s["categorie"] not in cats:
            continue
        if s["hele_dag"]:
            d, e, start = date.fromisoformat(s["start"]), date.fromisoformat(s["eind"]), None
            if e <= vandaag or d >= tot:
                continue
            d = max(d, vandaag)             # lopend weekend: toon op vandaag
            sleutel = (0, s["start"])
        else:
            start = datetime.fromisoformat(s["start"].replace("Z", "+00:00"))
            d = start.astimezone(tz).date()
            if not (vandaag <= d < tot) or datetime.fromisoformat(s["eind"].replace("Z", "+00:00")) <= nu:
                continue
            sleutel = (1, s["start"])
        per_dag.setdefault(d, []).append((sleutel, regel(s, data["series"], start)))

    if not per_dag:
        return []

    kleur = int(str(dc.get("kleur", "#ff3b30")).lstrip("#"), 16)
    embeds = []
    for d in sorted(per_dag):
        regels = [r for _, r in sorted(per_dag[d])]
        titel = "Vandaag · " + dag_naam(d) if d == vandaag else dag_naam(d)
        blok, n = [], 0
        for r in regels + [None]:
            if r is None or n + len(r) + 1 > MAX_DESC:
                embeds.append({"title": titel, "description": "\n".join(blok), "color": kleur})
                blok, n, titel = [], 0, dag_naam(d) + " (vervolg)"
            if r is not None:
                blok.append(r)
                n += len(r) + 1

    kop = dc.get("kop_week", "🏁 **Races deze week**") if mode == "week" else dc.get("kop_dag", "🏁 **Races vandaag**")
    if dc.get("link"):
        kop += f"\n{dc['link']}"
    berichten, huidig, grootte = [], [], 0
    for e in embeds:
        g = len(e["title"]) + len(e["description"])
        if huidig and (grootte + g > MAX_MSG or len(huidig) >= MAX_EMBEDS):
            berichten.append(huidig)
            huidig, grootte = [], 0
        huidig.append(e)
        grootte += g
    berichten.append(huidig)
    naam = dc.get("naam", data.get("titel", "Racekalender"))
    return [{"username": naam, "content": kop if i == 0 else "", "embeds": b, "allowed_mentions": {"parse": []}}
            for i, b in enumerate(berichten)]


def verstuur(url: str, payload: dict) -> None:
    req = urllib.request.Request(
        url + ("&" if "?" in url else "?") + "wait=true",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "racekalender (https://github.com, 1.0)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        r.read()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["week", "dag"], default="week")
    ap.add_argument("--data", default=str(ROOT / "public" / "races.json"))
    ap.add_argument("--config", default=str(ROOT / "config.yaml"))
    ap.add_argument("--dry-run", action="store_true", help="toon de berichten, verstuur niets")
    ap.add_argument("--nu", help="test: doe alsof het dit moment is (ISO, bijv. 2026-11-16T08:00:00+01:00)")
    a = ap.parse_args()

    data = json.loads(Path(a.data).read_text("utf-8"))
    cfg = yaml.safe_load(Path(a.config).read_text("utf-8"))
    nu = datetime.fromisoformat(a.nu) if a.nu else datetime.now(timezone.utc)
    berichten = bouw_berichten(data, cfg, a.mode, nu)
    if not berichten:
        print("Niets te melden – geen bericht geplaatst.", file=sys.stderr)
        return 0
    if a.dry_run:
        print(json.dumps(berichten, ensure_ascii=False, indent=1))
        return 0
    url = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if not url:
        print("DISCORD_WEBHOOK_URL ontbreekt.", file=sys.stderr)
        return 1
    for b in berichten:
        verstuur(url, b)
        time.sleep(1)
    print(f"✔ {len(berichten)} bericht(en) geplaatst.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
