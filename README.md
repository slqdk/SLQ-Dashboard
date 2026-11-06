# SLQ Dashboard

Min private startside: ét overblik med dato, tid, kalender, elpriser, trafik,
nyheder og resten, og en side til hver sektion. Kører som en Docker-container i
sin egen LXC på Proxmox. Lavet til pc'en; på telefonen virker det bare.

| Sektion | Hvad | Kilde |
|---|---|---|
| **Overblik** | Dato og tid, Dagsbåndet (kalender, elpris og vejr på én tidsakse), dk-lives kort over de seneste 6 timer, og noget fra hver sektion | Alle |
| **Kalender** | Din Google-kalender, kun læsning | Google Calendar API, én konto pr. person |
| **DK live** | Elpriser, trafik og opdateringer, plus link til kortet | Din dk-live-container |
| **Nyheder** | Overskrifter og korte tekster uden reklamer | RSS, hentet af serveren (DR og TV 2 som standard) |
| **LogMyLife** | Din egen tidslinje, der husker alt | Dine indlæg, Google, Dagbog, FamilyMap, Strava-eksport |
| **Aktier** | Din beholdning, ugens udvikling, snitkurs, udbytte og resultat pr. år | CSV-udtræk fra Nordnet, som du selv importerer, og kurser fra Yahoo Finance |
| **FamilyLog** | Månedens forbrug og søgning, kun læsning | FamilyLog 0.5.0 med læsenøgle pr. person |
| **Formel 1** | Sæsonens sessioner, ikke noget live | Jolpica |
| **SLQ DL** | Late night-historie, dato for dato, og de nyeste monologer | Egen database med kilder, YouTube |
| **Printere** | Status på printerne: fremskridt, tid tilbage, temperaturer. Kun læsning | Bambu Lab-printere direkte på netværket |
| **Kameraer** | Billeder og live-video bag login. Familien får det kun, hvis du vælger det | Tapo C200 gennem go2rtc |
| **Links** | Dine links i mapper | Egen database |
| **Admin** | Familiens brugere og al opsætning | |

Øverst til højre står ping-indikatoren: **Her** er svartiden fra din browser til
serveren, **Server** er svartiden fra serveren og ud. Klik for detaljer og
belastning.

- Installation på Proxmox: [docs/PROXMOX.md](docs/PROXMOX.md)
- Beslutninger, status og næste skridt: [docs/PLAN.md](docs/PLAN.md)

## Udvikling

```bash
cd backend && pip install -r requirements-dev.txt && python -m pytest -q
cd frontend && npm ci && npm test && npm run build
python3 tools/mock_upstreams.py 9100 &                 # falske data
python3 tools/mock_printer.py 9101 &                   # en falsk printer, kræver cryptography
cd backend && APP_DATA_DIR=./data APP_DKLIVE_URL=http://127.0.0.1:9100 \
  APP_JOLPICA_URL=http://127.0.0.1:9100/jolpica python -m uvicorn app.main:app --port 8080
cd frontend && npm run dev                             # proxier /api til :8080
```
