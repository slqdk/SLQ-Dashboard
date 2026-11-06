# SLQ Dashboard på Proxmox

Samme opskrift som FamilyLog: Docker i en Debian-LXC med `nesting=1,keyctl=1`,
værtsport **8090**, Nginx Proxy Manager foran.

> `proxmox/create-lxc.sh`, Docker-imaget og go2rtc-imaget er ikke kørt endnu. Der
> er hverken Proxmox eller Docker i det miljø, de blev skrevet i.

## 1. Opret containeren

Kopiér `proxmox/create-lxc.sh` til Proxmox-værten, og kør den som root. Vælg et
ledigt nummer og en ledig adresse:

```bash
CTID=109 IP=30.11.0.109 GATEWAY=30.11.0.1 bash create-lxc.sh
```

Scriptet opretter en LXC (2 kerner, 1 GB RAM, 16 GB disk, starter sammen med
værten), installerer Docker, kloner repo'et til `/opt/slq-dashboard` og starter
appen. Første build tager et par minutter.

### Hvis containeren allerede findes

På Proxmox-værten (noden → Shell), med containerens nummer:

```bash
pct set 109 --features nesting=1,keyctl=1 --onboot 1
pct reboot 109
pct enter 109
```

`pct enter` giver en root-shell i containeren uden kode, og `exit` fører tilbage
til værten. Inde i containeren:

```bash
apt-get update
apt-get install -y curl git python3 ca-certificates
curl -fsSL https://get.docker.com | sh
git clone https://github.com/slqdk/SLQ-Dashboard.git /opt/slq-dashboard
cd /opt/slq-dashboard
bash update.sh compose up -d --build
hostname -I
```

## 2. Første gang

Åbn `http://<ip>:8090`, og opret administratoren. Alt andet sættes op under
**Admin → Opsætning**: hjemme (sted og koordinater, bruges til vejret og til hvad
der er tæt på), kortets lag og nøgler, Google og nyhedskilder.

## 3. Nginx Proxy Manager

Ny proxy host `dashboard.slq.dk` → `http://<ip>:8090` med Let's Encrypt og Force
SSL. Sæt derefter **Offentlig adresse** i Admin til `https://dashboard.slq.dk`.

Under Advanced, så en Strava-eksport kan importeres:

    client_max_body_size 30m;

Dashboardet har login, men indeholder kalender, tidslinje og økonomi. Skal det
kun bruges hjemme og over WireGuard, så læg en Access List på i NPM.

## 4. Google

Under **Admin → Opsætning → Google Kalender** står trinene og den redirect-adresse,
Google skal have. Google kræver https og et domæne, så sæt adressen fra afsnit 3 op
først. Appen skal publiceres (*Publish app*): i *Testing* udløber forbindelsen efter
7 dage. Det kræver, at Branding har forside, privatlivspolitik og vilkår udfyldt.
Brug `https://dashboard.slq.dk/privacy.html` til de to sidste; siden følger med
dashboardet og kræver ikke login. Lad logoet stå tomt, for et logo kræver, at Google
godkender appen. Hver person forbinder bagefter sin egen konto under **Kalender**.

## 5. FamilyLog

Kræver FamilyLog 0.5.0. Sæt adressen under **Admin → Opsætning → FamilyLog**. Lav
en læsenøgle pr. person i FamilyLog under **Settings → Accounts → Read key**, og
sæt den ind under **Admin → Brugere → Ret**. Nøglen vises kun én gang.

## 6. Printere

Bambu Lab-printere sættes op under **Admin → Opsætning → Printere**: navn,
IP-adresse, serienummer og LAN Access Code. De tre sidste finder du i printerens
indstillinger. Giv printeren en fast adresse i routeren. Dashboardet læser kun, og
forbindelsen går direkte til printeren uden om Bambus sky.

Afviser printeren forbindelsen, så prøv med LAN-tilstand eller Developer Mode på
printeren. Det er ikke afprøvet på en rigtig printer endnu.

## 7. Kameraer

Opret først en **Camera Account** i Tapo-appen: kameraet → Device Settings →
Advanced Settings → Camera Account. Giv kameraet en fast adresse i routeren.

Tilføj det under **Admin → Opsætning → Kameraer** med navn, IP-adresse, brugernavn
og adgangskode. Vælg så under **Admin → Brugere**, hvem der må se kameraerne.
Sektionen er slået fra for familien som standard.

Billederne går gennem containeren `go2rtc`, som compose starter ved siden af appen.
Den har ingen åben port, så alt går gennem dashboardets login. Den gemmer ikke
kameraernes login på disken: dashboardet sender det igen, hvis den genstarter.
Det er afprøvet med go2rtc og en testkilde, men ikke på et rigtigt C200 endnu.

## 8. Aktier

Vælg **Importeret udtræk** under **Admin → Opsætning → Nordnet**. Hent så CSV-filen
fra Transaktioner og notaer på Nordnet med hele perioden valgt, og importér den på
siden **Aktier**. Hver person ser kun sit eget, og sektionen er slået fra for
familien som standard. Importér igen, når der er nyt: kun det nye kommer til.

Kurserne hentes hver halve time fra Yahoo Finance. Det er gratis og uden nøgle, men
ikke et officielt API, så det kan holde op med at virke. De seneste kurser bliver
liggende, og kun ISIN-numrene sendes dertil.

## 9. Opdatering og backup

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
