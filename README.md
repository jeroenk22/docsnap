# DocSnap 📸

> Crawl any documentation site to **Markdown + PDF** — one YAML config per site.

DocSnap logt automatisch in, klapt alle accordions en tabs uit, en slaat de volledige documentatie op als één leesbaar Markdown-bestand én een nette PDF.

---

## Installatie

```bash
pip install -r requirements.txt
playwright install chromium
```

---

## Gebruik

### Alles in één stap (aanbevolen)

```bash
python run_all.py sites/mendrix.yaml
```

### Alleen scrapen

```bash
python scraper.py sites/mendrix.yaml
```

### Alleen PDF genereren

```bash
python convert_to_pdf.py mendrix_docs.md --title "MendriX Docs"
```

### Browser zichtbaar (handig bij debuggen of manual login)

```bash
python run_all.py sites/mendrix.yaml --visible
```

---

## Nieuwe site toevoegen

1. Kopieer `sites/example_public.yaml` of `sites/example_manual_login.yaml`
2. Pas `base_url`, `start_url`, `scope_paths` en `output` aan
3. Kies login-methode: `none` / `form` / `manual`
4. Bij `form`: voeg credentials toe aan `.env` en verwijs ernaar via `username_env` / `password_env`
5. Draai: `python run_all.py sites/jouwsite.yaml`

---

## Login-methodes

| Methode  | Wanneer gebruiken                                                   |
| -------- | ------------------------------------------------------------------- |
| `none`   | Publieke docs, geen login nodig                                     |
| `form`   | Username + password via formulier; credentials uit `.env`           |
| `manual` | SSO / 2FA / complexe login — browser opent, jij logt in, druk Enter |

---

## YAML-opties (volledig overzicht)

```yaml
title: "Naam van de docs" # gebruikt in PDF-header
base_url: "https://docs.example.com" # origin voor scope-check
start_url: "https://docs.example.com/guide" # beginpunt van crawl
output: "output.md" # pad voor Markdown-output
headless: true # false = browser zichtbaar

scope_paths: # alleen URLs die beginnen met deze paden
  - /guide
  - /api

login:
  method: form # none | form | manual
  url: "https://.../login"
  env_file: ".env"
  username_env: SITE_USERNAME
  password_env: SITE_PASSWORD
  selectors: # CSS-selectors voor het loginformulier
    username: "input[type='email']"
    password: "input[type='password']"
    submit: "button[type='submit']"

expand:
  enabled: true
  wait_ms: 300 # wachttijd na uitklappen (ms)
  click_selectors: # elementen om op te klikken
    - "summary"
    - "[aria-expanded='false']"
  custom_js: # optionele JS die na klikken wordt uitgevoerd
    - "document.querySelectorAll('.lazy').forEach(el => el.click())"

content:
  selectors: # volgorde: eerste match wint
    - "main"
    - "article"
    - ".content"
  exclude_selectors: # verwijder uit content vóór conversie
    - "nav"
    - "footer"
    - ".sidebar"

crawl:
  max_pages: 500 # maximaal aantal pagina's

include_images: false # true = afbeelding-URLs in MD opnemen
```
