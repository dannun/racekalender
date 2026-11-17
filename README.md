# Racekalender

Een gratis "RaceDay" voor eigen gebruik. Je krijgt alle sessietijden van de grote raceklassen in Nederlandse tijd, met de NL-zender erbij:

- **Agenda-feeds (.ics)** voor de Agenda-app op je iPhone, Mac en Watch, met meldingen.
- **Web-app** die je op je beginscherm zet: overzicht per dag, filter per serie en een aftelklok naar de volgende race.

Elke 6 uur wordt alles automatisch bijgewerkt via GitHub Actions. Dat is gratis, je hebt geen server nodig.

## Installeren (± 5 minuten)

1. Maak op github.com een nieuwe **public** repository aan, bijvoorbeeld `racekalender`.
2. Upload de inhoud van deze map, inclusief de map `.github`.
   Via de terminal: `git init && git add . && git commit -m init && git branch -M main && git remote add origin https://github.com/<jij>/racekalender.git && git push -u origin main`
3. Ga in de repo naar **Settings → Pages → Build and deployment → Source** en kies **GitHub Actions**.
4. Open **Actions → Racekalender bijwerken → Run workflow**. Na ongeveer een minuut staat alles op
   `https://<jij>.github.io/racekalender/`

> Een private repo werkt alleen met GitHub Pages als je een betaald account hebt. De feeds bevatten alleen openbare racetijden.

## Op je iPhone

- **Web-app:** open de URL in Safari en kies **Deel → Zet op beginscherm**.
- **Agenda:** tik in de web-app op **📅 Abonneer** en kies "Alles", "Alleen races" of één serie.
  Meldingen staan al per type sessie in de feed (zie `config.yaml`). In iOS staan meldingen van een geabonneerde agenda soms standaard uit. Zet ze aan via **Agenda → Agenda's → (i) naast de racekalender**.
- Wil je dat iOS vaker verversing ophaalt? Kies dan bij **Instellingen → Apps → Agenda → Accounts → Agenda-abonnementen → Haal op** de optie *elk uur*.

## Aanpassen: `config.yaml`

| Wat | Waar |
|---|---|
| Serie aan of uit | `aan: false` bij die serie |
| Zender wijzigen of aanvullen | blok `zenders:` en per serie `zender:` |
| Meldingen | `meldingen:` (minuten vooraf per race/sprint/kwalificatie/training) |
| Titel in je agenda | `titel_formaat:` |
| Serie toevoegen | nieuw blok onder `series:` met een `mst`- of `ics`-bron |

Zenders met `# ?` zijn niet nagekeken. Pas ze aan als je beter weet. Na elke push bouwt GitHub alles opnieuw.

**Een serie van motorsport-total.com toevoegen:** open op motorsport-total.com de kalenderpagina van de serie. Het pad uit de URL, bijvoorbeeld `porsche-supercup`, gebruik je als `pagina:`. Je kunt ook de link achter "Kalender importieren" overnemen als `ics:`. Het script zet de gevonden link in het log.

## Databronnen

| Bron | Series | Detail |
|---|---|---|
| [sportstimes/f1](https://github.com/sportstimes/f1) (f1calendar.com) | F1, F2, F3, F1 Academy, MotoGP, Formula E, IndyCar | alle sessietijden |
| [motorcal](https://github.com/grahamwetzler/motorcal) | WEC (incl. Le Mans), IMSA, IndyCar | alle sessietijden |
| [motorsport-total.com](https://www.motorsport-total.com/motorsport-termin-kalender) | WorldSBK, NASCAR, DTM, WRC, GTWC, ELMS, 24h Nürburgring + aanvulling volgend seizoen | alleen raceweekenden, zonder tijden |

Per serie en per seizoen wordt de eerste bron gebruikt die data heeft. Komen de officiële tijden later beschikbaar bij een betere bron, dan schakelt het script vanzelf over.

**Beperkingen:** zenders zijn per serie ingesteld, niet per race. Afwijkingen zoals een gratis uitzending op Viaplay TV staan in de notitie van het agenda-item. Bij de series in de onderste rij zie je alleen het weekend, niet de starttijd.

## Op je eigen server in plaats van GitHub

```bash
pip install pyyaml
python build.py --out /var/www/racekalender     # of een IIS-map
# cron: elke 6 uur
17 */6 * * * cd /opt/racekalender && python3 build.py --out /var/www/racekalender
```

Voor de agenda-abonnementen moet de map via **HTTPS** bereikbaar zijn voor je iPhone. Dat kan van buitenaf, of via je VPN als je alleen thuis/op VPN wilt syncen.

## Discord

`discord_post.py` plaatst via een webhook een overzicht in een Discord-kanaal: op maandag de hele week, op de andere dagen de sessies van die dag (alleen als er iets is). Tijden staan als Discord-tijdstempel in het bericht, dus iedereen ziet zijn eigen lokale tijd.

1. Discord: **Serverinstellingen → Integraties → Webhooks → Nieuwe webhook**, kies het kanaal en kopieer de webhook-URL.
2. GitHub-repo: **Settings → Secrets and variables → Actions → New repository secret**, naam `DISCORD_WEBHOOK_URL`, waarde de URL.
3. Testen: **Actions → Racekalender naar Discord → Run workflow** (kies `week`).

Welke series en sessies in Discord komen stel je in onder `discord:` in `config.yaml`. De tijdstippen van plaatsen staan in `.github/workflows/discord.yml` (cron in UTC; in de zomer is dat een uur later NL-tijd).

Zet de webhook-URL nooit in de repo zelf: iedereen met die URL kan in je kanaal posten.

### Discord-evenementen (optioneel)

`discord_events.py` zet races en sprints van de komende 14 dagen in de **Evenementen**-lijst van je server. Leden klikken op "Geïnteresseerd" en krijgen dan van Discord zelf een melding bij de start. Het script draait mee met de gewone update (elke 6 uur), werkt gewijzigde tijden bij en blijft van je eigen handmatige evenementen af.

1. Ga naar discord.com/developers/applications → **New Application** → tabblad **Bot** → **Reset Token** en kopieer het token.
2. Tabblad **OAuth2 → URL Generator**: vink scope `bot` aan en het recht **Manage Events**. Open de gegenereerde link en voeg de bot toe aan je server.
3. Server-ID: zet in Discord **Instellingen → Geavanceerd → Ontwikkelaarsmodus** aan, klik rechts op je server → **Server-ID kopiëren**.
4. Maak in GitHub twee secrets aan: `DISCORD_BOT_TOKEN` en `DISCORD_GUILD_ID`.

Zonder deze secrets slaat het script zichzelf over. Instellingen staan onder `discord: evenementen:` in `config.yaml`. Lokaal bekijken wat er aangemaakt zou worden: `python discord_events.py --dry-run`.

## iRacing Special Events

Serie `iracing` in `config.yaml`. Het script leest de datums automatisch van [iracing.com/specialevents](https://www.iracing.com/specialevents/). Lukt dat niet, bijvoorbeeld omdat de pagina van opzet verandert, dan gebruikt het de lijst in `data/iracing.yaml` (staat in het Actions-log).

iRacing publiceert alleen datums, geen starttijden. Wil je de timeslots in je agenda, zet ze dan per event in `data/iracing.yaml` onder `tijden:` (in GMT/UTC) en verwijder de `url`-bron in `config.yaml`, zodat de handmatige lijst voorrang krijgt.

## Link in Discord

Discord maakt van `webcal://`-links geen klikbare link. Deel daarom de **web-app-URL** (`https://<jij>.github.io/racekalender/`): daar staat de knop 📅 Abonneer. Zet hem in een vastgepinde post, in het kanaalonderwerp of onder `discord: link:` in `config.yaml`. Dan staat hij ook onder elk weekoverzicht.
