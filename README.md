# Racekalender

Een gratis alternatief voor apps als RaceDay. Alle grote raceklassen staan erin, met sessietijden in Nederlandse tijd en de tv-zender voor **Nederland of België**. Er zijn drie manieren om hem te gebruiken:

- **Web-app:** **https://dannun.github.io/racekalender/**. Je kunt hem als app op je beginscherm zetten.
- **Agenda-abonnement:** werkt in iPhone/Mac, Android/Google en Outlook, met meldingen. Via *Mijn agenda* kies je zelf welke series erin staan.
- **Discord:** een weekoverzicht en de races van de dag in een kanaal, en optioneel ook Discord-evenementen.

Alles wordt elke 6 uur automatisch bijgewerkt via GitHub Actions, en direct na elke wijziging in de repo. Dat kost niets en er is geen eigen server nodig.

---

## Gebruiken

### Web-app
- Open **dannun.github.io/racekalender** in Safari of Chrome en kies **Delen → Zet op beginscherm**.
- **Seriefilters:** tik bovenin op een serie om hem te verbergen of te tonen.
- **Alles / Kwali + races / Races:** hiermee kies je welke sessies je ziet.
- **NL / BE:** wisselt tussen Nederlandse en Belgische zenders. Een Belgisch toestel krijgt automatisch BE.
- Tik op een sessie voor meer info: zender, klassen en notities.

### Abonneren in je agenda
Tik op **ABONNEER**:
1. Kies je toestel: **iPhone / Mac**, **Android** of **Outlook**.
2. Kies de **series** en de **sessies** (Alles, Kwali + races of Races).
3. Tik op **ABONNEER · x SERIES**. Met *Link kopiëren* kopieer je de link om hem ergens anders te plakken.

Onder *Losse agenda's* staan ook kant-en-klare agenda's per serie.

**Wat gebeurt er bij wijzigingen?** Een abonnement is een live koppeling. Verschuift een tijd, dan schuift het item mee. Vervalt een sessie, dan verdwijnt hij, en nieuwe sessies verschijnen vanzelf. Hoe snel je dat ziet, hangt af van je agenda:

| Agenda | Ververst |
|---|---|
| iPhone / Mac | instelbaar: Instellingen → Apps → Agenda → Accounts → **Haal op** → bijvoorbeeld *Elk uur* |
| Google / Android | Google bepaalt het zelf, meestal binnen 8 tot 24 uur |
| Outlook | een paar keer per dag |

Items uit een abonnement kun je niet in je agenda aanpassen. Wijzigingen doe je in deze repo.

---

## Wat staat erin

| Serie | Sessietijden | Zender NL | Zender BE | Bron |
|---|---|---|---|---|
| F1 | ✔ | Viaplay / F1 TV | Play Sports / Tipik / F1 TV | sportstimes |
| F2, F3 | ✔ | Viaplay / F1 TV | Play Sports / F1 TV | sportstimes |
| MotoGP | ✔ | Ziggo Sport | Play Sports / Tipik | sportstimes |
| WEC (incl. Le Mans) | ✔ | Eurosport / FIA WEC+ | Eurosport / FIA WEC+ | motorcal |
| IMSA | ✔ | Ziggo Sport | IMSA.tv | motorcal |
| IndyCar | ✔ | Ziggo Sport | IndyCar Live | sportstimes / motorcal |
| Formula E | ✔ | Ziggo Sport | Play Sports / Eurosport | sportstimes |
| WorldSBK | weekend | Viaplay / SBK VideoPass | RTBF Auvio / SBK VideoPass | motorsport-total |
| NASCAR | weekend | Ziggo Sport | ABXplore | motorsport-total |
| DTM | weekend | Ziggo Sport | DTM-stream | motorsport-total |
| WRC | weekend | Rally.TV | RTBF Auvio / Rally.TV | motorsport-total |
| GT World Challenge | weekend | YouTube | YouTube | motorsport-total |
| ELMS | weekend | YouTube | YouTube | motorsport-total |
| 24h Nürburgring | weekend | Viaplay | 24h-stream | motorsport-total |
| iRacing Special Events | datums + tijden | iRacing | iRacing | iracing.com + `data/iracing.yaml` |

F1 Academy, Moto2 en Moto3 staan standaard uit (`aan: false` in `config.yaml`).

**Weekend** betekent dat de bron alleen het raceweekend kent en geen starttijden. Komt er later een betere bron met tijden, dan schakelt het script vanzelf over. Volgend seizoen verschijnt ook vanzelf zodra de bronnen het publiceren.

De zenders zijn per serie ingesteld, niet per race. Een gratis uitzending van één race staat er dus niet apart bij.

---

## Aanpassen

Bijna alles regel je in **`config.yaml`**. Na een commit bouwt GitHub de kalender binnen ongeveer 2 minuten opnieuw.

| Wat | Waar |
|---|---|
| Serie aan of uit | `aan: false` bij de serie |
| Zender Nederland | `zender:` bij de serie, verwijst naar het blok `zenders:` |
| Zender België | `zender_be:` bij de serie, zie het blok `# ── België ──` |
| Meldingen in de agenda | `meldingen:` (minuten vooraf per race, sprint, kwalificatie of training) |
| Titel van agenda-items | `titel_formaat:` |
| Discord | blok `discord:`, met `land: nl` of `be` |
| Serie toevoegen | nieuw blok onder `series:` met een `mst`- of `ics`-bron (zie het commentaar in het bestand) |

### iRacing Special Events
De datums worden automatisch gelezen van [iracing.com/specialevents](https://www.iracing.com/specialevents/). Klassen, circuit en tijden komen uit **`data/iracing.yaml`**. Officiële tijden staan in het *This Week*-artikel van iRacing en in de event-thread op het forum, meestal pas in de week van het event. Per event kun je invullen:

```yaml
- naam: Chili Bowl
  van: 2026-12-15
  tot: 2026-12-20
  circuit: Tulsa Expo
  klassen: Dirt Midget
  slots: [2026-12-19T22:00Z, ...]          # timeslots in UTC/GMT
  sessies:                                   # of losse sessies per klasse
    - { naam: "Super Session", tijd: 2026-12-20T02:00Z, klassen: "Dirt Midget" }
  notitie: "tekst voor in de agenda"
```

Vul de 2027-kalender aan zodra iRacing die publiceert.

---

## Mijn agenda (Cloudflare Worker)

GitHub Pages kan alleen vaste bestanden serveren. Daarom maakt een klein gratis script bij Cloudflare de persoonlijke agenda's:

- Worker: **https://racekalender.dannun.workers.dev/**
- Voorbeeld: `…workers.dev/mijn.ics?series=f1,motogp&soort=races&land=be`
- Code: `cloudflare/worker.js`. Wijzig je die, plak hem dan opnieuw in Cloudflare (Workers & Pages → racekalender → Edit code → Deploy).
- In `web/index.html` staat het adres bij `const WORKER`. Laat je dat leeg, dan verdwijnt *Mijn agenda* uit de app.
- De worker bewaart de agenda 30 minuten in de cache. Na een update kan het dus even duren voordat Mijn agenda bij is.
- De gratis limiet is 100.000 aanvragen per dag.

---

## Discord (optioneel)

| Wat | Nodig | Bestand |
|---|---|---|
| **Link** vastpinnen in een kanaal | niets | – |
| **Berichten:** maandag het weekoverzicht, andere dagen de races van vandaag | webhook | `discord_post.py` + `.github/workflows/discord.yml` |
| **Evenementen** bovenaan de server (races en sprints, 14 dagen vooruit) | bot | `discord_events.py`, draait mee in `build.yml` |

**Webhook:** Discord → Serverinstellingen → Integraties → Webhooks → Nieuwe webhook → URL kopiëren. Zet die in GitHub onder **Settings → Secrets and variables → Actions** als `DISCORD_WEBHOOK_URL`.

**Bot:** maak een bot op discord.com/developers/applications met de scope `bot` en het recht **Manage Events**, en voeg hem toe aan je server. Zet daarna de secrets `DISCORD_BOT_TOKEN` en `DISCORD_GUILD_ID` (Server-ID, via de Ontwikkelaarsmodus).

Zonder secrets slaan de scripts zichzelf over. Instellingen staan onder `discord:` in `config.yaml`. iRacing staat standaard niet bij de evenementen, omdat je anders vijf slots per event krijgt.

---

## Bestanden

```
.github/workflows/build.yml     bouwen + publiceren (elke 6 uur en na elke commit)
.github/workflows/discord.yml   Discord-berichten (optioneel)
build.py                        haalt de bronnen op en maakt de agenda's + races.json
config.yaml                     series, zenders (NL/BE), meldingen, Discord
data/iracing.yaml               iRacing-details: klassen, tijden, notities
web/                            de web-app (index.html, iconen, manifest)
cloudflare/worker.js            persoonlijke agenda (Mijn agenda)
discord_post.py                 Discord-berichten via webhook
discord_events.py               Discord-evenementen via bot
```

Wat de site publiceert: `index.html`, `races.json`, `alles.ics` / `races.ics` (NL), `alles-be.ics` / `races-be.ics` (BE), `ics/<serie>.ics` en `ics/be/<serie>.ics`.

Lokaal testen:

```bash
pip install pyyaml
python build.py --out public
python discord_post.py --mode week --data public/races.json --dry-run
```

## Databronnen

- [sportstimes/f1](https://github.com/sportstimes/f1) (f1calendar.com en zustersites): F1, F2, F3, F1 Academy, MotoGP, Formula E, IndyCar
- [motorcal](https://github.com/grahamwetzler/motorcal): WEC, IMSA, IndyCar
- [motorsport-total.com](https://www.motorsport-total.com/motorsport-termin-kalender): raceweekenden van overige series (Duitse namen worden vertaald)
- [iracing.com/specialevents](https://www.iracing.com/specialevents/): iRacing Special Events

Racekalender is een eigen project en niet verbonden aan de genoemde series, zenders of bronnen.
