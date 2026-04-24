# Cash Rocket Anaheim

Marketing website for **cashrocketanaheim.com** — an Anaheim-targeted ghost
site feeding the shared Cash in Flash apply pipeline.

- Legal entity: **Dhan Corporation** (Cash Rocket Anaheim is a marketing dba).
- Source-attribution slug: `cashrocket_anaheim` (stored in sessionStorage
  by apply.cashinflash.com and persisted on the backend as `source_site`).
- Deploy target: **Netlify** (static, no build step).
- Pre-launch embargo: `robots.txt` is `Disallow: /` — counsel must sign off
  before indexing is enabled.

## ⚠ Before you deploy — 2 blockers

### 1. Upload the 10 Poppins woff2 fonts into `/fonts/`
Binary files can't be pushed via the Claude Code GitHub integration — it
round-trips content as JSON strings which corrupts woff2 bytes. The fonts
need to be uploaded manually. Two easy options:

**Option A — GitHub web UI (quickest):**
1. Open the repo's `fonts/` folder on the `main` branch.
2. Click "Add file → Upload files".
3. Drag the 10 woff2 files (same ones cif-website already ships — copy from
   `cashinflash/Cif-website` at `/fonts/`).
4. Commit directly to the branch.

Files needed:
```
poppins-400.woff2       poppins-400-ext.woff2
poppins-500.woff2       poppins-500-ext.woff2
poppins-600.woff2       poppins-600-ext.woff2
poppins-700.woff2       poppins-700-ext.woff2
poppins-800.woff2       poppins-800-ext.woff2
```

**Option B — git clone + commit locally:**
```bash
git clone -b main \
  git@github.com:cashinflash/CashRocketAnaheim.git
cd CashRocketAnaheim
# Copy fonts from a local cif-website checkout (or download from
# https://raw.githubusercontent.com/cashinflash/Cif-website/main/fonts/...)
mkdir -p fonts && cp /path/to/cif-website/fonts/*.woff2 fonts/
git add fonts/ && git commit -m "add Poppins woff2 fonts" && git push
```

Until the fonts are uploaded, the site falls back to `Helvetica Neue, Arial,
sans-serif` — still readable, just not on-brand. The `@font-face` rules and
`<link rel="preload">` tags already point at the right paths, so everything
"just works" the moment the binaries land.

### 2. Fill in the placeholder tokens
See the table below.

## Placeholders (resolve before launch)
| Token | What to fill in |
|---|---|
| `[[LICENSE_NUMBER]]` | CDFPI deferred-deposit license # (usually `10DFPI-NNNNNN`) |
| `[[NMLS_ID]]` | NMLS consumer access ID |
| `[[YEAR_FOUNDED]]` | Copyright year (e.g. `2026`) |
| `[[CONTACT_EMAIL]]` | Customer / legal-notices email |
| `657-366-7776` | Toll-free support number |
| `[[GA4_ID]]` | New Google Analytics 4 property id |

A find-and-replace across the repo will resolve them. Run
`grep -r '\[\[' --exclude-dir=node_modules --exclude-dir=.git` to list remaining tokens.

## Apply CTAs
Every Apply button points at:
```
https://apply.cashinflash.com/?source_site=cashrocket_anaheim&utm_source=cashrocketanaheim.com&utm_medium=referral&utm_campaign=payday_anaheim
```
This works without JavaScript — hrefs are hard-coded.

## Layout
```
/
├── index.html                  # Anaheim payday-loan landing
├── rates-and-fees/index.html   # CA CFL §23035 disclosure
├── terms/ privacy/ security/   # rebranded legal (Dhan preserved)
├── css/style.css               # navy/gold palette
├── js/main.js, js/analytics.js # menu + GA loader (GA ID placeholder)
├── images/logo.svg             # inline SVG wordmark
├── fonts/poppins-*.woff2       # reused from cif-website
├── 404.html, robots.txt, sitemap.xml, site.webmanifest
├── netlify.toml                # security headers + caching
└── SOURCE_SITE                 # literal slug: cashrocket_anaheim
```

## Local preview
```bash
python3 -m http.server 8000
```
Then open http://localhost:8000/.
