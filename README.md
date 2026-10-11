# DawaiDaam

Compares what a prescription medicine really costs across **online pharmacies** (price + delivery + fees)
and **nearby physical stores** (price + your own travel cost, or store delivery when offered).

## Run it

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                   # optional
uvicorn backend.main:app --reload
# open http://localhost:8000
```
Or `docker build -t dawaidaam . && docker run -p 8000:8000 dawaidaam`.
Tests: `pytest`.

## Deploy the complete app on Render (recommended instead of Netlify)

One Python **Web Service** serves the website and `/api/...` together. No separate
frontend deploy, CORS changes or Netlify API proxy is needed.

### Deploy from this repository

1. Put this project in its own GitHub/GitLab/Bitbucket repository, with `backend`,
   `frontend`, `data`, `requirements.txt`, `render.yaml` and `.python-version` at the root.
   Do not upload `.env`, `rx.db`, database backups or credentials. The included
   `.gitignore` excludes local secrets and databases, but does not untrack files
   already committed. Inspect the files before pushing. Upload the **whole source
   project**, not only the frontend folder.
2. Sign in at [Render](https://dashboard.render.com/), choose **New > Blueprint**,
   connect that repository, and use the root `render.yaml`.
3. Review the resources and charges before deploying. The Blueprint selects a paid
   **Starter** Python service and a **1 GB persistent disk**. Render's free service
   cannot attach a persistent disk; using it would lose SQLite data on redeploy or
   restart. Check Render's current pricing before confirming.
4. Deploy and wait for the build and health check to pass. Open the service's assigned
   HTTPS URL (shown in Render), **not the old Netlify URL**. This is the new full-app URL.

`render.yaml` uses JSON syntax, which is valid YAML, so its configuration can also be
checked with Python's standard JSON parser without adding a YAML dependency.
`.python-version` selects the latest available Python 3.12 patch, matching the Docker
runtime's minor version. The native Python runtime is selected explicitly, not Docker.

### Equivalent manual Web Service settings

If you prefer **New > Web Service** instead of a Blueprint, configure all of these:

| Setting | Value |
| --- | --- |
| Language/runtime | Python 3 |
| Root directory | Blank when the project is at the repository root |
| Build command | `pip install -r requirements.txt` |
| Start command | `uvicorn backend.main:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips='*'` |
| Health check path | `/api/health` |
| Instance plan | Paid plan supporting disks (Blueprint uses Starter) |
| Instances | 1; keep a single Uvicorn worker for this SQLite deployment |
| Persistent disk | Mount at `/var/data`, size 1 GB |
| Environment variable | `DB_PATH=/var/data/rx.db` |
| Demo setting | `ENABLE_DEMO=true` (synthetic prices, not verified retail quotes) |
| Nearby pharmacy lookup | `ENABLE_OSM=true` (requires external network access) |

Render supplies `PORT`; do not paste `$PORT` into a Windows PowerShell command.
The disk must be attached **before** startup. Only files under `/var/data` persist;
the app creates `rx.db` there on first startup, not during the build. The default
local database is not migrated automatically. Disk-backed services cannot scale to
multiple instances and have a brief interruption during deploys. Arrange regular,
SQLite-consistent backups separately before using real customer data.

The proxy flags let Uvicorn recognize HTTPS terminated by Render, preserving Secure
session cookies and the existing same-origin protection. Trusting all forwarded
headers is intended **only behind Render's managed ingress**, where clients cannot
bypass the proxy; do not reuse that wildcard on a directly exposed server. For other
hosts, restrict trusted proxies to their documented addresses. Do not disable origin
checks to work around failed login. Never commit `PHARMACY_API_KEY`; if needed, set it
as a secret in Render's environment settings.

### Verify after deployment

- Open `/api/health` on the new domain: expect HTTP 200, `application/json`, and
  `"ok": true`. An HTML page means you are on the wrong host or have incorrect routing.
- Open `/`, search for a medicine, and try **Browse all** and **Liquids only**.
- Register a test account, log out/in, save a basket item and an address, then compare.
  Inspect the session cookie: HttpOnly, Secure and SameSite=Strict should be present.
- Confirm comparison requests to `/api/prices/stream` return `text/event-stream`,
  with result events and a final done event. External provider failures may still
  occur independently of deployment.
- Redeploy/restart, log in again, and confirm the basket and address remain saved.
- Update bookmarks to the Render URL. The old Netlify site remains static and will
  still show the API error unless a separate backend/proxy integration is added.

Local tests validate startup and persistence, but do not create a Render service or
verify its public routing. Prices remain demo/indicative and medicine information
requires clinical review before production use.

## Netlify deployment: fixing "Page not found"

The HTML entry point is `frontend/index.html`, **not** an `index.html` at the project root.
The root `netlify.toml` configures Netlify to publish `frontend` with no build command.

### Deploying from Git

1. Push the project, including `netlify.toml`, to the repository connected to Netlify.
2. In Netlify's build settings, leave the **base directory** blank (repository root),
   leave the **build command** blank, and set the **publish directory** to `frontend`.
   This assumes the project files are at the repository root. If they are in an `rxcompare`
   subfolder, set that as the base directory and keep the publish directory as `frontend`.
3. Trigger a new production deploy. Open the site's root URL, e.g. `https://your-site.netlify.app/`.
4. Confirm the published deploy contains `index.html`, `styles.css` and `app.js` at its root.

### Manual drag-and-drop deployment

Drop the **frontend folder**, not the entire project folder, into Netlify's deploy area.
If uploading a ZIP, put `index.html`, `styles.css` and `app.js` directly at the ZIP root,
not inside an enclosing `rxcompare/` or `frontend/` folder. A manual deploy does not use
the repository build settings to move files into place.

Navigation uses hash URLs such as `/#login`, `/#basket` and `/#addresses`; `/login` is not
a page in this app. No catch-all rewrite is required, and `/api/*` must not return HTML.

**Important:** This fixes static publishing only. Netlify static hosting does not run this
project's FastAPI/uvicorn server or persistent SQLite database. Without a separately hosted
backend and an API proxy, the page can load but medicine search, accounts, basket, saved
addresses and price comparison will not work. For the simplest full deployment, host this
existing app on a Python/container web service with persistent storage for `DB_PATH`; it
already serves both the frontend and API from the same origin. Do not upload `rx.db`, `.env`
or other private backend files as public static assets. A split Netlify/API deployment also
requires deliberate cookie, origin-protection and SSE proxy configuration; merely changing
the publish directory does not provide that integration.

## Accounts, medicine information and basket

### "Unexpected token '<' ... is not valid JSON" on Netlify

This means an `/api/...` request returned an HTML document (often a 404 or a catch-all
rewrite to `index.html`) rather than a JSON API response. Publishing `frontend` only fixes
the home page; it does not deploy the Python backend. The frontend now checks response
types and displays an explicit deployment message instead of a JSON parsing error.

Open `/api/health` on the deployed site's domain: a correctly connected backend returns
JSON containing `"ok": true`. An HTML page or a 404 means the API is not connected.
Remove any `/* -> /index.html` rewrite that captures API requests. Run the complete app
on a Python web service (build: `pip install -r requirements.txt`; start:
`uvicorn backend.main:app --host 0.0.0.0 --port $PORT`, where the host supplies `PORT`).
Use persistent storage and set `DB_PATH` to a writable path on that storage to preserve
accounts, baskets and addresses. This app serves the frontend from that same service,
so Netlify is optional. If retaining Netlify, connect it to the actual hosted backend
with an API proxy and verify origin protection, session cookies and SSE end-to-end.
Do not disable origin checks or return fake JSON to hide the missing backend.

- Use **Log in** in the navigation to register (passwords require at least 10 characters), then sign in.
  Passwords use salted PBKDF2-SHA256 hashes. Sessions use random tokens, stored hashed in SQLite,
  with HttpOnly/SameSite=Strict cookies, seven-day expiry and logout revocation. HTTPS enables Secure cookies.
- **History** keeps the latest 100 comparisons initiated while signed in, with medicine, quantity and time.
  It does not save location or pincode. Each account sees only its own history and can clear it.
- **Basket** saves medicine quantities per account. Update or remove an item, or return to comparison
  to get fresh costs. This is a saved list, **not checkout**; it does not dispense medicine or place orders.
- Selecting a medicine shows educational usage, possible side effects, warnings and a patient-information
  reference. Summaries cover the eight sample catalogue medicines, are not exhaustive, and need clinical
  review before production. They do not provide individualized dosing instructions.
- Pharmacy search links are available without a live feed. They **do not verify availability** or identify
  an exact product. Real enabled HTTP connectors display direct listing links when returned by the source;
  demo quote links remain labelled as provider websites, not real product offers.

New account API: `POST /api/auth/register`, `POST /api/auth/login`, `POST /api/auth/logout`,
`GET /api/auth/me`; `GET/POST/DELETE /api/history`; `GET/PUT /api/basket` and
`DELETE /api/basket/{drug_id}`. History and basket require a session cookie.

### Medicine catalogue and liquids

The starter catalogue contains 27 medicine/strength/form entries, including six syrups or oral
liquids. Browse all entries or only liquids from the search controls. It is **not** a complete list
of medicines used in India, a usage-frequency ranking, an official essential-medicines list,
or a stock guarantee. Brand aliases aid discovery; verify composition against the actual pack.
New reference prices are synthetic demo inputs, not verified retail prices; new entries have no
invented brand-price comparisons. A clinician/pharmacist should review entries before production use.

Liquid shopping quantities mean **bottles**, not millilitres or doses. Concentration and sample
bottle volume are explicit; real HTTP listings must match both and the liquid form. Children need
age/weight-appropriate professional advice. Medicine details include drug safety, prescription,
antibiotic and liquid warnings; no dose is inferred from shopping quantity. The catalogue does not
include controlled/narcotic medicines and does not claim that unflagged entries are universally OTC.

### Saved address details

Use **Addresses** in the navigation to add, edit or delete multiple home addresses for your account.
Each address includes a label, recipient, street, optional landmark, city, state, six-digit Indian
pincode and optional coordinates. Use **current location** while at that home or enter
coordinates manually; leave both latitude and longitude blank to save without coordinates.
Typed street addresses are not automatically geocoded. Addresses persist in SQLite and are private
to the signed-in account. Unlike comparison history, this address book stores precise locations when supplied.

In the basket's **Delivery address** selector, choose a saved address or a one-time location.
One-time locations offer current location or manual coordinates. There is no map-selection or
address-search/geocoding feature. If a saved address has no coordinates, you can still select it;
coordinates are optional in basket checkout too. Its saved pincode is used for online delivery.
Without coordinates, only coordinate-independent online providers are checked; nearby stores and
location-dependent providers are explicitly skipped. You can optionally supply coordinates to include them.
Changing the selection clears old offers and rechecks the basket using that address's coordinates
and pincode. Directions also use the selected location. Selecting an address does **not** place an
order or transfer address details to an external pharmacy; enter the delivery address on its website.

API: authenticated `GET/POST /api/addresses`, `PUT/DELETE /api/addresses/{address_id}`.
`GET /api/basket/compare?address_id=...` resolves only an address owned by the current user and
uses its stored location/pincode instead of any supplied location parameters. For addresses without
coordinates, the API uses the supplied latitude/longitude and still uses the saved pincode. Missing or deleted
addresses return 404; existing latitude/longitude comparisons remain supported. The address table
is created automatically at startup without changing existing accounts, baskets or history.

### Comparing the whole basket

On the Basket page, enter your location (or use geolocation) and optional delivery
pincode. The app checks the whole basket automatically after items or quantities change when a valid
location is available; **Check whole basket** also refreshes it manually. Location is not saved to history.

`GET /api/basket/compare?lat=17&lng=78&pincode=...`
requires login and compares only the current user's saved items. Results group items by source and
physical branch/fulfilment, showing per-item price and availability, store address/phone/hours,
directions, medicine subtotal, delivery fee, platform fee, total and estimated delivery time.
The basket UI uses a 5 km store search and excludes personal travel costs (the API still accepts optional
radius and travel-cost overrides). Delivery/platform fees are charged once per basket,
and free-delivery thresholds and minimum orders use the combined medicine subtotal.
Quantities are still rounded to whole packs by each price connector.

Missing, out-of-stock, stale or unknown-stock/price items prevent a complete-basket total.
Failed sources are reported separately; "no listing" is not proof that a retailer has no stock.
Demo offers remain clearly marked synthetic. Reported in-stock flags do not guarantee sufficient
inventory for the requested quantity: verify with the pharmacy before buying.

**Online delivery fees and ETAs currently come from configured provider rules, not a live cart/checkout
API.** No real online feeds are enabled out of the box. To show the exact charge a platform is asking,
a permitted partner checkout-quote integration is needed, including its pincode, pack, stock, fee and
ETA data. Do not represent configured estimates or demo rows as verified checkout prices.

Online offers include a **Continue on provider** hyperlink when a product URL is supplied, plus
**Copy medicine list** for manual entry on the pharmacy's website. Demo links are labelled as demo
websites. These are not populated cart or checkout links, and no items are added to an external account.
Automatic cart transfer requires the selected pharmacy's documented cart deep link or authorized
cart-creation API, exact product IDs and pack quantities, and any required customer authorization.
No configured provider currently supplies that integration. Browser security prevents this app from
directly manipulating another website's logged-in cart.

The legacy internal session-cookie name is retained so existing users are not logged out by the
DawaiDaam rebrand; account and basket data remain unchanged.

Pages use client-side navigation (`/#login`, `/#history`, `/#basket`, `/#compare`).
Existing SQLite databases are extended automatically at startup; no manual migration is needed.

For deployment, use HTTPS, review proxy/origin handling, restrict registration abuse, and add email
verification, password recovery, account deletion and appropriate privacy/retention policies.
Failed logins are limited to ten attempts per email/IP in 15 minutes; this is not a complete abuse-prevention system.

## What is real and what is demo

| Piece | Status out of the box |
|---|---|
| Nearby pharmacy locations, hours, phone | **Real**, from OpenStreetMap (Overpass API) |
| Store prices | Real when loaded via portal API, CSV import or crowd reports; otherwise the store is listed as "Price unconfirmed" with the reference price as an upper bound |
| Online prices | **Demo** (synthetic) until you enable a real connector in `data/providers.json` |
| Delivery fees, free-delivery thresholds, ETA | Real logic, driven by per-provider rules (`delivery` block) |
| Stores that deliver | Pickup and delivery are shown as separate options |

Set `ENABLE_DEMO=false` once you have real sources, so synthetic rows disappear.

## How the total is computed

`total = medicine price + delivery fee + platform fee + your travel cost - discount`

- Online: delivery rule per provider (`base_fee`, `free_above`, `per_km`, `max_km`, `min_order`, `platform_fee`, `eta_*`).
- Store pickup: `road_km x 2 x your cost per km` (road_km = straight line x `ROAD_FACTOR`).
- Quantity is converted to whole packs (30 tablets of a 10-pack = 3 packs).

## Getting real-time prices

Data flows: connector -> per-source timeout and cache -> ranking -> streamed to the browser over SSE
(`GET /api/prices/stream`), so the fastest source shows up first and a failing source never blocks the rest.

1. **Pharmacy portal / feeds (best).** `POST /api/pharmacy/prices` with header `X-API-Key`, or bulk-load with
   `python -m backend.import_csv prices.csv`.
2. **Partner or official APIs.** Add an entry with `"type": "http"`, `"response": "json"` to `data/providers.json`
   (see `example-json-api`: URL template, `items_path`, field mappings, delivery rule), then set `"enabled": true`.
3. **HTML pages.** Same file, `"response": "html"` with CSS selectors (see `example-html`).
4. **Crowd reports.** `POST /api/reports` stores them as `pending`; moderate before they influence prices.

The two `example-*` providers use placeholder `.test` domains. I did not hard-code real retailers' endpoints:
they change often, mostly have no public API, and many forbid automated access.

### Read this before scraping anything
- Check each site's Terms of Service and `robots.txt`. The HTTP connector enforces robots.txt (fail-closed)
  and rate-limits per source, but that does not make scraping permitted. Get written permission or a partner API where you can.
- Selling or comparing prescription-only medicines is regulated (in India, for example, online pharmacy rules and
  Schedule H/H1/X restrictions). This app only compares prices and never sells or advises. Get legal review before launch.
- Health-related location and search data is sensitive. Don't log precise locations, and review your privacy law
  obligations (DPDP Act, GDPR, HIPAA, depending on market).

## API

| Endpoint | Purpose |
|---|---|
| `GET /api/drugs/search?q=` | Autocomplete, tolerant of brand names and typos |
| `GET /api/drugs/{id}` | Drug detail plus cheaper same-ingredient brands |
| `GET /api/prices?drug_id&qty&lat&lng&radius_km&travel_cost_per_km&pincode&sort=total\|fastest\|nearest` | Ranked list, waits for all sources |
| `GET /api/prices/stream?...` | Same, streamed via SSE |
| `POST /api/reports` | Crowd price report (pending review) |
| `POST /api/pharmacy/prices` | Authenticated pharmacy price upload |

## Layout

```
backend/  main.py (API) aggregator.py (fan-out, cache, timeouts) delivery.py ranking.py normalize.py
          db.py (SQLite) connectors/{demo,osm,http_connector,robots,base}.py
data/     drugs.json (sample catalogue, illustrative prices)  providers.json (sources + delivery rules)
frontend/ index.html styles.css app.js (Leaflet map, live results)
tests/    test_core.py
```

## Moving to production

SQLite -> PostgreSQL + PostGIS, in-memory cache -> Redis, scheduled ingestion workers (Prefect/Airflow) instead of
on-demand fetches for slow sources, full drug coding (RxNorm / local formulary) instead of `drugs.json`,
auth for the pharmacy portal, moderation UI for crowd reports, and observability on per-source freshness and failure rate.
