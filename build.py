#!/usr/bin/env python3
"""Racekalender – haalt racekalenders op, voegt ze samen en schrijft
agenda-feeds (.ics), races.json en de web-app naar de map public/.

Gebruik:  python build.py [--config config.yaml] [--out public] [--offline map]
Vereist:  Python 3.11+, PyYAML
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import urllib.request
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parent
UA = "Mozilla/5.0 (racekalender; +https://github.com)"
SPORTSTIMES = "https://raw.githubusercontent.com/sportstimes/f1/main/_db"
MOTORCAL = "https://raw.githubusercontent.com/grahamwetzler/motorcal/main/data"
MST = "https://www.motorsport-total.com"

# ── Sessienamen (NL) en categorieën ─────────────────────────────────────────
ST_NAMES = {
    "fp1": "VT1", "fp2": "VT2", "fp3": "VT3", "practice": "Training",
    "practice1": "VT1", "practice2": "VT2", "practice3": "VT3",
    "qualifying": "Kwalificatie", "qualifying1": "Q1", "qualifying2": "Q2",
    "sprintQualifying": "Sprint-kwalificatie", "sprint": "Sprint",
    "gp": "Race", "race": "Race", "feature": "Hoofdrace",
    "race1": "Race 1", "race2": "Race 2", "race3": "Race 3",
    "warmup": "Warm-up", "other": "Overig",
}
MC_NAMES = {
    "practice": "Training", "qualifying": "Kwalificatie", "hyperpole": "Hyperpole",
    "sprint_qualifying": "Sprint-kwalificatie", "sprint": "Sprint", "race": "Race",
    "warmup": "Warm-up", "testing": "Test",
}
LABEL_NL = [
    (r"Free Practice\s*", "VT"), (r"Practice", "Training"), (r"Qualifying", "Kwalificatie"),
    (r"Warm[- ]?up", "Warm-up"), (r"Test(ing)?", "Test"),
]


def category(key: str) -> str:
    k = key.lower()
    if "sprint" in k and "qual" in k:
        return "kwalificatie"
    if "sprint" in k:
        return "sprint"
    if k in ("gp", "feature") or k.startswith("race"):
        return "race"
    if "qual" in k or "hyperpole" in k:
        return "kwalificatie"
    if k == "weekend":
        return "weekend"
    return "training"


@dataclass
class Session:
    serie: str          # sleutel uit config
    evenement: str      # bijv. "Thailand" / "6 Hours of Spa"
    sessie: str         # NL-naam, bijv. "Kwalificatie"
    categorie: str      # race|sprint|kwalificatie|training|weekend
    start: str          # ISO UTC (getimed) of YYYY-MM-DD (hele dag)
    eind: str           # idem; bij hele dag: exclusieve einddatum
    hele_dag: bool
    locatie: str = ""
    ronde: int | None = None
    tbc: bool = False   # tijd nog niet bekend
    bron: str = ""
    klassen: str = ""   # bijv. "GT3 · GT4" (iRacing)
    notitie: str = ""

    @property
    def jaar(self) -> int:
        return int(self.start[:4])

    @property
    def uid(self) -> str:
        h = hashlib.sha1(f"{self.serie}|{self.evenement}|{self.sessie}|{self.start[:10]}".encode()).hexdigest()[:16]
        return f"{h}@racekalender"


# ── Ophalen ────────────────────────────────────────────────────────────────
class Fetcher:
    def __init__(self, offline: Path | None):
        self.offline = offline
        self.cache: dict[str, str | None] = {}

    def get(self, url: str) -> str | None:
        if url in self.cache:
            return self.cache[url]
        text = None
        if self.offline:
            p = self.offline / re.sub(r"[^A-Za-z0-9._-]", "_", url)
            text = p.read_text("utf-8") if p.exists() else None
        else:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=30) as r:
                    text = r.read().decode("utf-8", "replace")
            except Exception as e:  # noqa: BLE001
                log(f"  ! ophalen mislukt: {url} ({e})")
        self.cache[url] = text
        return text


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


def iso_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_dur(v, default_min: int) -> int:
    if v is None:
        return default_min
    if isinstance(v, (int, float)):
        return int(v)
    m = re.fullmatch(r"\s*(?:(\d+)\s*h)?\s*(?:(\d+)\s*m)?\s*", str(v))
    if not m or not any(m.groups()):
        return default_min
    return int(m.group(1) or 0) * 60 + int(m.group(2) or 0)


# ── Bron: sportstimes (f1calendar.com e.a.) ────────────────────────────────
def src_sportstimes(f: Fetcher, serie: str, src: dict, years: list[int]) -> list[Session]:
    key = src["sleutel"]
    cfg_txt = f.get(f"{SPORTSTIMES}/{key}/config.json")
    if not cfg_txt:
        return []
    cfg = json.loads(cfg_txt)
    lengths = cfg.get("sessionLengths", {})
    out: list[Session] = []
    for y in years:
        if y not in cfg.get("availableYears", []):
            continue
        txt = f.get(f"{SPORTSTIMES}/{key}/{y}.json")
        if not txt:
            continue
        for race in json.loads(txt).get("races", []):
            if race.get("canceled") or race.get("cancelled"):
                continue
            name = race.get("name", "")
            if key == "f1" and not name.lower().endswith(("grand prix", " gp")):
                name = f"{name} GP"
            for sk, st in (race.get("sessions") or {}).items():
                if not st:
                    continue
                start = datetime.fromisoformat(st.replace("Z", "+00:00"))
                dur = int(lengths.get(sk, 60))
                tbc = bool(race.get("tbc"))
                out.append(Session(
                    serie=serie, evenement=name, sessie=ST_NAMES.get(sk, sk),
                    categorie=category(sk), start=iso_utc(start),
                    eind=iso_utc(start + timedelta(minutes=dur)), hele_dag=False,
                    locatie=race.get("location", ""),
                    ronde=race.get("round"), tbc=tbc, bron="sportstimes"))
    return out


# ── Bron: motorcal (YAML) ──────────────────────────────────────────────────
def nl_label(label: str) -> str:
    for pat, rep in LABEL_NL:
        label = re.sub(pat, rep, label)
    return label


def src_motorcal(f: Fetcher, serie: str, src: dict, years: list[int]) -> list[Session]:
    key = src["sleutel"]
    txt = f.get(f"{MOTORCAL}/{key}.yaml")
    dtxt = f.get(f"{MOTORCAL}/defaults.yaml")
    if not txt:
        return []
    data = yaml.safe_load(txt) or {}
    defaults = ((yaml.safe_load(dtxt) or {}).get("defaults", {}) if dtxt else {}).get("durations", {})
    durs = {**defaults, **(data.get("durations") or {})}
    out: list[Session] = []
    for ev in data.get("events") or []:
        for s in ev.get("sessions") or []:
            if str(s.get("status", "")).upper() == "CANCELLED":
                continue
            typ = s.get("type", "race")
            naam = nl_label(s["label"]) if s.get("label") else MC_NAMES.get(typ, typ)
            if s.get("start"):
                start = datetime.fromisoformat(str(s["start"]).replace("Z", "+00:00"))
                if start.year not in years:
                    continue
                dur = parse_dur(s.get("duration") or durs.get(typ), 60)
                out.append(Session(serie, ev.get("name", ""), naam, category(typ), iso_utc(start),
                                   iso_utc(start + timedelta(minutes=dur)), False,
                                   ev.get("location", ""), ev.get("round"), bool(s.get("tbc")), "motorcal"))
            elif s.get("date"):
                d = date.fromisoformat(str(s["date"]))
                if d.year not in years:
                    continue
                out.append(Session(serie, ev.get("name", ""), naam, category(typ), d.isoformat(),
                                   (d + timedelta(days=1)).isoformat(), True,
                                   ev.get("location", ""), ev.get("round"), True, "motorcal"))
    return out


# ── Bron: ICS (algemeen) en motorsport-total ───────────────────────────────
def unfold(text: str) -> list[str]:
    lines: list[str] = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    return lines


def ics_unescape(v: str) -> str:
    return v.replace("\\n", " ").replace("\\N", " ").replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\").strip()


def parse_ics_dt(prop: str, value: str) -> tuple[datetime | date, bool]:
    params = dict(p.split("=", 1) for p in prop.split(";")[1:] if "=" in p)
    if params.get("VALUE") == "DATE" or re.fullmatch(r"\d{8}", value):
        return datetime.strptime(value, "%Y%m%d").date(), True
    if value.endswith("Z"):
        return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc), False
    tz = ZoneInfo(params.get("TZID", "Europe/Berlin"))
    return datetime.strptime(value, "%Y%m%dT%H%M%S").replace(tzinfo=tz), False


def parse_ics(text: str) -> list[dict]:
    events, cur = [], None
    for line in unfold(text):
        if line == "BEGIN:VEVENT":
            cur = {}
        elif line == "END:VEVENT" and cur is not None:
            events.append(cur)
            cur = None
        elif cur is not None and ":" in line:
            prop, val = line.split(":", 1)
            name = prop.split(";")[0].upper()
            if name in ("DTSTART", "DTEND"):
                cur[name] = parse_ics_dt(prop, val)
            elif name in ("SUMMARY", "LOCATION", "STATUS"):
                cur[name] = ics_unescape(val)
    return events


def mst_discover(f: Fetcher, pagina: str) -> str | None:
    """Zoekt via de kalenderpagina van een serie de .ics-link op motorsport-total.com."""
    html = f.get(f"{MST}/{pagina}/termin-kalender")
    if not html:
        return None
    m = re.search(r"termine_[\w.-]+\.ics", html)
    if m:
        return f"{MST}/motorsport-termine/{m.group(0)}"
    m = (re.search(r"motorsport-termin-kalender-abonnieren\?calendar=\d+", html)
         or re.search(r"motorsport-termin-kalender-abonnieren\?channel=\d+", html))
    if not m:
        return None
    sub = f.get(f"{MST}/{m.group(0)}")
    m2 = re.search(r"termine_[\w.-]+\.ics", sub or "")
    if not m2:
        return None
    url = f"{MST}/motorsport-termine/{m2.group(0)}"
    log(f"  · motorsport-total '{pagina}' -> {url}  (tip: zet als 'ics:' in config.yaml)")
    return url


def src_ics(f: Fetcher, serie: str, src: dict, years: list[int], tz: ZoneInfo) -> list[Session]:
    url = src.get("ics") or src.get("url")
    if not url and src.get("pagina"):
        url = mst_discover(f, src["pagina"])
        if not url:
            log(f"  ! geen agenda gevonden voor motorsport-total pagina '{src['pagina']}'")
            return []
    text = f.get(url) if url else None
    if not text:
        return []
    prefix = src.get("prefix")
    out: list[Session] = []
    for ev in parse_ics(text):
        summ = ev.get("SUMMARY", "")
        if "CANCEL" in ev.get("STATUS", "").upper() or "abgesagt" in summ.lower():
            continue
        if prefix:
            if not summ.lower().startswith(prefix.lower()):
                continue
        if "DTSTART" not in ev:
            continue
        # "Formel 2: Bahrain / Sakhir"  ->  "Bahrain / Sakhir"
        name = summ.split(":", 1)[1].strip() if ":" in summ else summ
        s, allday = ev["DTSTART"]
        e = ev.get("DTEND", (None, allday))[0]
        if isinstance(s, datetime):
            sl = s.astimezone(tz)
            el = e.astimezone(tz) if isinstance(e, datetime) else sl
            # Hele weekenden (00:00 – 23:59) als hele-dag-items behandelen
            if (sl.hour, sl.minute) == (0, 0) and ((el.hour, el.minute) in ((0, 0), (23, 59)) or el - sl >= timedelta(hours=20)):
                sd = sl.date()
                ed = el.date() + timedelta(days=1) if (el.hour, el.minute) == (23, 59) else el.date()
                allday, s, e = True, sd, max(ed, sd + timedelta(days=1))
        if allday:
            sd = s if isinstance(s, date) else s.date()
            ed = e if isinstance(e, date) and not isinstance(e, datetime) else sd + timedelta(days=1)
            if sd.year not in years:
                continue
            out.append(Session(serie, name, "Raceweekend", "weekend", sd.isoformat(), ed.isoformat(),
                               True, ev.get("LOCATION", ""), None, True, "motorsport-total"))
        else:
            if s.year not in years:
                continue
            e = e if isinstance(e, datetime) else s + timedelta(hours=1)
            out.append(Session(serie, name, "Sessie", "training", iso_utc(s), iso_utc(e), False,
                               ev.get("LOCATION", ""), None, False, "ics"))
    return out


# ── Bron: iRacing Special Events ───────────────────────────────────────────
MAANDEN_EN = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
DATUM_RE = re.compile(
    r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2})"
    r"(?:\s*[-–—]\s*(?:(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+)?(\d{1,2}))?,\s*(\d{4})$")


def iracing_web(html: str) -> list[dict]:
    """Leest 'Naam' + 'Maand d-d, jjjj' paren uit de Special Events-pagina."""
    import html as htmlmod
    txt = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    txt = re.sub(r"(?i)<br\s*/?>|</(p|div|h\d|li|span|a|strong|b|td|tr)>", "\n", txt)
    txt = htmlmod.unescape(re.sub(r"<[^>]+>", " ", txt))
    lines = [re.sub(r"\s+", " ", x).strip() for x in txt.split("\n")]
    lines = [x for x in lines if x]
    out, seen = [], set()
    for i, line in enumerate(lines):
        m = DATUM_RE.match(line)
        if not m or i == 0:
            continue
        naam = lines[i - 1]
        if DATUM_RE.match(naam) or len(naam) > 60 or naam.lower().endswith("events"):
            continue
        m1, d1, m2, d2, y = m.groups()
        y = int(y)
        van = date(y, MAANDEN_EN[m1[:3].lower()], int(d1))
        tot = date(y, MAANDEN_EN[(m2 or m1)[:3].lower()], int(d2 or d1))
        if tot < van:                       # bijv. Dec 30 – Jan 2
            tot = date(y + 1, tot.month, tot.day)
        if (naam, van) not in seen:
            seen.add((naam, van))
            out.append({"naam": naam, "van": van.isoformat(), "tot": tot.isoformat()})
    return out


def _norm(x: str) -> str:
    return re.sub(r"[^a-z0-9]", "", x.lower().replace("scca", "").replace("iracing", ""))


def _ts(v) -> datetime:
    d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def src_iracing(f: Fetcher, serie: str, src: dict, years: list[int]) -> list[Session]:
    p = ROOT / src.get("bestand", "data/iracing.yaml")
    lokaal = (yaml.safe_load(p.read_text("utf-8")) or {}).get("events", []) if p.exists() else []
    lokaal = [e for e in lokaal if isinstance(e, dict) and e.get("van") and e.get("tot")]
    web: list[dict] = []
    if src.get("url"):
        html = f.get(src["url"])
        web = iracing_web(html) if html else []
        if html and not web:
            log("  ! iracing.com gelezen maar geen events herkend – pagina gewijzigd? Alleen data/iracing.yaml gebruikt")
    # Web levert naam + datums, de YAML vult aan (en kan datums overschrijven)
    events, gebruikt = [], set()
    for w in web:
        match = next((i for i, l in enumerate(lokaal) if i not in gebruikt and (
            str(l["van"]) == w["van"] or (_norm(l["naam"]) and (_norm(l["naam"]) in _norm(w["naam"]) or _norm(w["naam"]) in _norm(l["naam"]))))), None)
        if match is not None:
            gebruikt.add(match)
            events.append({**w, **lokaal[match]})
        else:
            events.append(w)
    events += [l for i, l in enumerate(lokaal) if i not in gebruikt]

    out: list[Session] = []
    for e in events:
        try:
            van, tot = date.fromisoformat(str(e["van"])), date.fromisoformat(str(e["tot"]))
        except (KeyError, ValueError):
            continue
        if van.year not in years:
            continue
        extra = dict(locatie=str(e.get("circuit", "")), klassen=str(e.get("klassen", "")),
                     notitie=str(e.get("notitie", "")), bron="iracing")
        slots = e.get("slots") or e.get("tijden") or []
        dur = parse_dur(e.get("duur"), 120)
        for i, t in enumerate(slots, 1):
            st = _ts(t)
            out.append(Session(serie, e["naam"], f"Race · slot {i}" if len(slots) > 1 else "Race", "race",
                               iso_utc(st), iso_utc(st + timedelta(minutes=dur)), False, **extra))
        if not slots and not e.get("sessies"):
            out.append(Session(serie, e["naam"], "Special Event", "weekend", van.isoformat(),
                               (tot + timedelta(days=1)).isoformat(), True, tbc=True, **extra))
        for x in e.get("sessies") or []:
            st = _ts(x["tijd"])
            out.append(Session(serie, e["naam"], str(x.get("naam", "Race")), "race", iso_utc(st),
                               iso_utc(st + timedelta(minutes=parse_dur(x.get("duur") or e.get("duur"), 60))), False,
                               **{**extra, "klassen": str(x.get("klassen", extra["klassen"]))}))
        if e.get("periode") and not slots:
            out.append(Session(serie, e["naam"], str(e["periode"]), "weekend", van.isoformat(),
                               (tot + timedelta(days=1)).isoformat(), True, tbc=True, **extra))
        if e.get("super_session"):
            st = _ts(e["super_session"])
            out.append(Session(serie, e["naam"], "Super Session", "race", iso_utc(st),
                               iso_utc(st + timedelta(minutes=parse_dur(e.get("duur_super"), 180))), False, **extra))
    return out


# ── Samenvoegen ────────────────────────────────────────────────────────────
def collect(cfg: dict, f: Fetcher, years: list[int]) -> tuple[list[Session], dict]:
    tz = ZoneInfo(cfg.get("tijdzone", "Europe/Amsterdam"))
    all_sessions: list[Session] = []
    report = {}
    for key, s in cfg["series"].items():
        if s.get("aan", True) is False:
            continue
        per_year: dict[int, list[Session]] = {}
        for src in s.get("bronnen", []):
            t = src["type"]
            if t == "sportstimes":
                items = src_sportstimes(f, key, src, years)
            elif t == "motorcal":
                items = src_motorcal(f, key, src, years)
            elif t == "iracing":
                items = src_iracing(f, key, src, years)
            elif t in ("mst", "ics"):
                items = src_ics(f, key, src, years, tz)
            else:
                log(f"  ! onbekend brontype {t}")
                continue
            for y in years:
                got = [x for x in items if x.jaar == y]
                if got and y not in per_year:
                    per_year[y] = got
        sessions = [x for y in years for x in per_year.get(y, [])]
        report[key] = {str(y): (len(per_year[y]), per_year[y][0].bron) if y in per_year else (0, "-") for y in years}
        log(f"{s['naam']:<10} " + "  ".join(f"{y}: {n:>3} ({b})" for y, (n, b) in report[key].items()))
        all_sessions += sessions
    all_sessions.sort(key=lambda x: (x.start[:10], x.hele_dag is False, x.start))
    return all_sessions, report


# ── Uitvoer: ICS ───────────────────────────────────────────────────────────
def ics_escape(v: str) -> str:
    return v.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def fold(line: str) -> str:
    b = line.encode("utf-8")
    if len(b) <= 75:
        return line
    parts, cur = [], b""
    for ch in line:
        cb = ch.encode("utf-8")
        if len(cur) + len(cb) > (75 if not parts else 74):
            parts.append(cur.decode("utf-8"))
            cur = b""
        cur += cb
    parts.append(cur.decode("utf-8"))
    return "\r\n ".join(parts)


def write_ics(path: Path, name: str, sessions: list[Session], cfg: dict, stamp: str) -> None:
    fmt = cfg.get("titel_formaat", "{serie} · {sessie} · {evenement} [{zender}]")
    alarms = cfg.get("meldingen", {})
    L = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//racekalender//NL", "CALSCALE:GREGORIAN",
         "METHOD:PUBLISH", f"X-WR-CALNAME:{ics_escape(name)}", f"X-WR-TIMEZONE:{cfg.get('tijdzone', 'Europe/Amsterdam')}",
         "REFRESH-INTERVAL;VALUE=DURATION:PT6H", "X-PUBLISHED-TTL:PT6H"]
    for s in sessions:
        serie = cfg["series"][s.serie]
        zender = cfg["zenders"].get(serie.get("zender", "onbekend"), cfg["zenders"]["onbekend"])
        sessie = s.sessie + (" (tijd volgt)" if s.tbc and not s.hele_dag else "")
        title = fmt.format(serie=serie["naam"], sessie=sessie, evenement=s.evenement, zender=zender["kort"])
        desc = f"📺 {zender['info']}"
        if s.klassen:
            desc += f"\n🏎️ {s.klassen}"
        if s.notitie:
            desc += f"\nℹ️ {s.notitie}"
        if s.ronde:
            desc += f"\nRonde {s.ronde}"
        if s.hele_dag and not s.notitie:
            desc += "\nExacte sessietijden nog niet bekend."
        L += ["BEGIN:VEVENT", f"UID:{s.uid}", f"DTSTAMP:{stamp}"]
        if s.hele_dag:
            L += [f"DTSTART;VALUE=DATE:{s.start.replace('-', '')}", f"DTEND;VALUE=DATE:{s.eind.replace('-', '')}",
                  "TRANSP:TRANSPARENT"]
        else:
            L += [f"DTSTART:{s.start.replace('-', '').replace(':', '')}", f"DTEND:{s.eind.replace('-', '').replace(':', '')}"]
        L += [f"SUMMARY:{ics_escape(title)}", f"DESCRIPTION:{ics_escape(desc)}"]
        if s.locatie:
            L.append(f"LOCATION:{ics_escape(s.locatie)}")
        L.append(f"CATEGORIES:{ics_escape(serie['naam'])}")
        if not s.hele_dag and not s.tbc:
            for m in alarms.get(s.categorie, []) or []:
                L += ["BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{ics_escape(title)}",
                      f"TRIGGER:-PT{int(m)}M", "END:VALARM"]
        L.append("END:VEVENT")
    L.append("END:VCALENDAR")
    path.write_text("\r\n".join(fold(x) for x in L) + "\r\n", encoding="utf-8")


# ── Hoofdprogramma ─────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(ROOT / "config.yaml"))
    ap.add_argument("--out", default=str(ROOT / "public"))
    ap.add_argument("--offline", help="map met opgeslagen bronbestanden (voor testen)")
    args = ap.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text("utf-8"))
    now = datetime.now(timezone.utc)
    years = [now.year, now.year + 1]
    f = Fetcher(Path(args.offline) if args.offline else None)
    sessions, report = collect(cfg, f, years)

    cutoff = now - timedelta(days=int(cfg.get("historie_dagen", 30)))
    sessions = [s for s in sessions if s.eind >= cutoff.strftime("%Y-%m-%d")]
    if not sessions:
        log("Geen sessies gevonden – uitvoer niet overschreven.")
        return 1

    out = Path(args.out)
    (out / "ics").mkdir(parents=True, exist_ok=True)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    title = cfg.get("titel", "Racekalender")
    active = [k for k, s in cfg["series"].items() if s.get("aan", True) is not False]

    write_ics(out / "alles.ics", title, sessions, cfg, stamp)
    write_ics(out / "races.ics", f"{title} – races", [s for s in sessions if s.categorie in ("race", "sprint", "weekend")], cfg, stamp)
    for k in active:
        sub = [s for s in sessions if s.serie == k]
        if sub:
            write_ics(out / "ics" / f"{k}.ics", f"{cfg['series'][k]['naam']} ({title})", sub, cfg, stamp)

    data = {
        "titel": title,
        "bijgewerkt": now.isoformat(timespec="seconds"),
        "tijdzone": cfg.get("tijdzone", "Europe/Amsterdam"),
        "series": {k: {"naam": cfg["series"][k]["naam"], "kleur": cfg["series"][k].get("kleur", "#888"),
                       "zender": cfg["zenders"].get(cfg["series"][k].get("zender", "onbekend"), cfg["zenders"]["onbekend"]),
                       "ics": f"ics/{k}.ics" if any(s.serie == k for s in sessions) else None}
                   for k in active},
        "sessies": [{k: v for k, v in asdict(s).items() if v not in (None, "", False) or k in ("hele_dag",)}
                    for s in sessions],
        "bronnen": report,
    }
    js = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    (out / "races.json").write_text(js, "utf-8")
    (out / "races.js").write_text(f"window.__RACEDATA__={js};", "utf-8")   # voor de OBS-overlay
    for name in ("index.html", "manifest.webmanifest", "icon.svg", "icon-180.png", "icon-512.png"):
        p = ROOT / "web" / name
        if p.exists():
            shutil.copy(p, out / name)
    log(f"\n✔ {len(sessions)} sessies geschreven naar {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
