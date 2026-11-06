# SLQ Dashboard på Proxmox

Samme opskrift som FamilyLog: Docker i en Debian-LXC med `nesting=1,keyctl=1`,
værtsport **8090**, Nginx Proxy Manager foran.

> `proxmox/create-lxc.sh` og Docker-imaget er ikke kørt endnu. Der er hverken
> Proxmox eller Docker i det miljø, de blev skrevet i.

## 1. Opret containeren

Kopiér `proxmox/create-lxc.sh` til Proxmox-værten, og kør den som root. Vælg et
ledigt nummer og en ledig adresse:

```bash
CTID=109 IP=30.11.0.109 GATEWAY=30.11.0.1 bash create-lxc.sh
```

Scriptet opretter en LXC (2 kerner, 1 GB RAM, 16 GB disk, starter sammen med
værten), installerer Docker, kloner repo'et til `/opt/slq-dashboard` og starter
appen. Første build tager et par minutter.

Hvis repo'et er privat, skal LXC'en bruge en deploy key, ligesom FamilyLog
(`docs/CONTAINER.md` i FamilyLog).

## 2. Første gang

Åbn `http://<ip>:8090`, og opret administratoren. Alt andet sættes op under
**Admin → Opsætning**: hjemme (sted og koordinater, bruges til vejret og til hvad
der er tæt på), adressen til dk-live, Google og nyhedskilder.

## 3. Nginx Proxy Manager

Ny proxy host `dashboard.slq.dk` → `http://<ip>:8090` med Let's Encrypt og Force
SSL. Sæt derefter **Offentlig adresse** i Admin til `https://dashboard.slq.dk`.

Under Advanced, så en Strava-eksport kan importeres:

    client_max_body_size 30m;

Dashboardet har login, men indeholder kalender, tidslinje og økonomi. Skal det
kun bruges hjemme og over WireGuard, så læg en Access List på i NPM.

## 4. Google

Under **Admin → Opsætning → Google Kalender** står trinene og den redirect-adresse,
Google skal have. Husk at sætte OAuth consent screen til *In production*: i
*Testing* udløber forbindelsen efter 7 dage. Hver person forbinder bagefter sin
egen konto under **Kalender**.

## 5. FamilyLog

Kræver FamilyLog 0.5.0. Sæt adressen under **Admin → Opsætning → FamilyLog**. Lav
en læsenøgle pr. person i FamilyLog under **Settings → Accounts → Read key**, og
sæt den ind under **Admin → Brugere → Ret**. Nøglen vises kun én gang.

## 6. Opdatering og backup

```bash
cd /opt/slq-dashboard
bash update.sh            # henter, bygger, tager backup af /data, genstarter og tjekker
bash update.sh status
bash update.sh rollback   # tilbage til seneste backup, kode og data
bash update.sh compose logs -f
```

Alt der er dit, ligger i volumet `/data`: `app.db`, `settings.json`, `secret.key`
og logs. Egne indstillinger hører til i
`deploy/container/docker-compose.override.yml`, som git ignorerer.
