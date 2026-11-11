# Putting Gym Buddy on AWS

From nothing to "the phone shows my reps over the hotspot". About an hour the
first time. Steps marked **You** need your accounts or passwords; nobody else
can do them for you.

Status, 2026-11-10: the server, the scripts and the restart test below are
tested on the laptop. The Docker files have **not** been built yet (the laptop
has no Docker), so step 4 is the first time they run. If the build fails, the
error will be in the output of that command; nothing else depends on Docker
(see "If Docker fights back").

## What you end up with

    Watch --hotspot--> http://<server ip>:8000   (upload, with the token)
    Phone -----------> https://<name>.duckdns.org (dashboard, with the password)

    One small AWS server running two containers:
      app    the FastAPI server. Data on a volume, so it survives restarts.
      caddy  adds HTTPS in front of it, and gets its own certificate.

## 1. Create the server (You, 10 min)

1. Sign in at https://lightsail.aws.amazon.com and choose **Create instance**.
2. Platform **Linux/Unix**, blueprint **OS Only → Ubuntu 24.04 LTS**.
3. Pick the plan with **1 GB** of memory. The smallest plan would probably run
   it, but the build installs numpy and scipy and 1 GB leaves room.
4. Name it `gym-buddy`, create it, and wait for "Running".
5. Open the instance → **Networking**:
   - **Attach static IP** (create one). Without it the address changes when the server restarts. Write the address down: it is `<server ip>` below.
   - Under **IPv4 Firewall**, add two rules: **HTTPS (TCP 443)** and **Custom TCP 8000**. SSH (22) and HTTP (80) are already open.

## 2. Give it a name (You, 5 min)

HTTPS needs a name, not just a number, because certificates are issued to names.

1. Sign in at https://www.duckdns.org.
2. Add a subdomain, e.g. `dan-gymbuddy`. Put `<server ip>` in its "current ip" box and press **update ip**.
3. Your name is now `dan-gymbuddy.duckdns.org`. It is `<name>` below.

## 3. Install Docker on the server (5 min)

On the instance page press **Connect using SSH** (a terminal opens in the
browser). Then:

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu
```

Close the terminal and connect again (the second line only takes effect on a new login). Check:

```bash
docker run --rm hello-world
```

## 4. Get the code and start it (10 min)

```bash
git clone -b server-api https://github.com/drodriguez97/gym-buddy.git
cd gym-buddy
cp .env.example .env
python3 -c "import secrets; print(secrets.token_urlsafe(24))"
nano .env
```

If the repository is private, GitHub asks for a user name and a personal
access token (GitHub → Settings → Developer settings → Fine-grained tokens,
read-only access to this one repository).

In `nano`, fill in the three lines, then Ctrl+O, Enter, Ctrl+X:

    GYM_BUDDY_TOKEN=<the random text the python line printed>
    GYM_BUDDY_PASSWORD=<a password you will type on your phone>
    GYM_BUDDY_DOMAIN=<name>

Start it:

```bash
docker compose --profile https up -d --build
docker compose ps
```

`docker compose ps` should show `app` as **healthy** after about half a minute,
and `caddy` as running. Open `https://<name>` on your phone: the browser asks
for a password (leave the user name empty), then shows "No sets yet".

## 5. Check it from the laptop (2 min)

In PowerShell, from `server\`, with the same token and password as in `.env`:

```powershell
$env:GYM_BUDDY_TOKEN = "<token>"; $env:GYM_BUDDY_PASSWORD = "<password>"
..\.venv\Scripts\python.exe scripts\check_server.py http://<server ip>:8000
```

Every line should say `ok` except "there are sets to show" and "the watch has
reported in", which come next.

## 6. Preload real sets (2 min)

So the demo has data even if the live part fails:

```powershell
..\.venv\Scripts\python.exe scripts\push_sets.py http://<server ip>:8000 --as-workout
```

This sends the laptop's stored sets through the same `POST /sets` the watch
uses. `--as-workout` gives them start times ending ten minutes ago (see the
top of the script for why).

## 7. Point the watch at it (You, 5 min)

Edit `watch/config.py` on the laptop, then save it to the watch with Thonny:

    WIFI_SSID = "<your phone hotspot's name>"
    WIFI_PASSWORD = "<the hotspot password>"
    SERVER = "http://<server ip>:8000"
    TOKEN = "<the token from .env>"

The hotspot must offer 2.4 GHz; the watch cannot see 5 GHz. iPhone: Settings →
Personal Hotspot → **Maximize Compatibility** on. Android: hotspot settings →
band → 2.4 GHz.

Then the real test (this is milestone M4): hotspot on, do 5 curls, hold B, and
the phone shows 5. Run `check_server.py` again: every line `ok`.

## 8. Prove a restart keeps the data (2 min)

```bash
docker compose --profile https down
docker compose --profile https up -d
```

Reload the dashboard: the same sets are there. `down` throws the containers
away; the data was never in them, it is on the volume.

## Everyday commands (on the server, in `gym-buddy/`)

| To | Run |
|---|---|
| See what's running | `docker compose ps` |
| Read the server's log | `docker compose logs app --tail 50` |
| Update after a `git push` | `git pull && docker compose --profile https up -d --build` |
| Recount every set after an analyzer change | `docker compose exec app python scripts/backfill.py` |
| Copy the data out as a backup | `docker run --rm -v gym-buddy_data:/data -v "$PWD":/out busybox tar czf /out/backup.tgz /data` |
| Stop paying | Delete the instance and the static IP in Lightsail |

## What is and isn't protected

- The dashboard on `https://<name>` is encrypted and behind the password.
- The watch uploads over plain HTTP. On a network someone else can listen on,
  the token could be read and used to upload fake sets. It cannot read anything:
  the token only opens the two upload addresses. HTTPS from the watch is the
  fix and is untested on this firmware, so it is left for after the demo.
- Port 8000 also serves the dashboard without encryption. Use the `https://`
  address on the phone, never `http://<server ip>:8000`, or the password
  travels in the clear.
- Change the token: edit `.env`, `docker compose --profile https up -d`, and put the new one in `watch/config.py`.

## If Docker fights back

The container is packaging, not logic. The same server runs without it:

```bash
sudo apt install -y python3-venv
cd gym-buddy/server && python3 -m venv venv && venv/bin/pip install -r requirements-run.txt
GYM_BUDDY_TOKEN=<token> GYM_BUDDY_PASSWORD=<password> venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```

That gives the watch and (over HTTP) the phone everything they need, with data
in `server/data/`. And if AWS itself isn't working by Friday night, the plan's
cut line applies: demo from the laptop with preloaded data.
