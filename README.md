# SLQ Dashboard

Min private startside: ét overblik med dato, tid, kalender, elpriser, trafik,
nyheder og resten, og en side til hver sektion. Kører som en Docker-container i
sin egen LXC på Proxmox. Lavet til pc'en; på telefonen virker det bare.

| Sektion | Hvad | Kilde |
|---|---|---|
| **Overblik** | Dato og tid, Dagsbåndet (kalender, elpris og vejr på én tidsakse) og noget fra hver sektion | Alle |
| **Kalender** | Din Google-kalender, kun læsning | Google Calendar API, én konto pr. person |
| **DK live** | Elpriser, trafik og opdateringer, plus link til kortet | Din dk-live-container |
| **Nyheder** | Overskrifter og korte tekster uden reklamer | RSS, hentet af serveren (DR og TV 2 som standard) |
| **LogMyLife** | Din egen tidslinje, der husker alt | Dine indlæg, Google, senere andre sektioner |
| **Aktier** | Nordnet | Ikke forbundet endnu, se `docs/PLAN.md` |
| **FamilyLog** | Dine data fra FamilyLog, kun læsning | Ikke forbundet endnu, se `docs/PLAN.md` |
| **Formel 1** | Sæsonens sessioner, ikke noget live | Jolpica |
| **SLQ DL** | Late night-historie, dato for dato | Egen database med kilder |
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
cd backend && APP_DATA_DIR=./data APP_DKLIVE_URL=http://127.0.0.1:9100 \
  APP_JOLPICA_URL=http://127.0.0.1:9100/jolpica python -m uvicorn app.main:app --port 8080
cd frontend && npm run dev                             # proxier /api til :8080
```
