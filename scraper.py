"""
docs-scraper/scraper.py
Generieke Playwright-based documentatie scraper.
Configureerbaar via een YAML-bestand per site.

Gebruik:
    python scraper.py sites/mendrix.yaml
    python scraper.py sites/example.yaml --visible   # browser zichtbaar
"""

import argparse
import asyncio
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

import html2text
import yaml
from dotenv import dotenv_values
from playwright.async_api import async_playwright, Page


# ── Helpers ───────────────────────────────────────────────────────────────────

def clean_url(url: str) -> str:
    p = urlparse(url)
    return p._replace(fragment="").geturl().rstrip("/")


def is_in_scope(url: str, base: str, scope_paths: list[str]) -> bool:
    """Valt de URL binnen de geconfigureerde paden?"""
    pu, pb = urlparse(url), urlparse(base)
    if pu.netloc != pb.netloc:
        return False
    return any(pu.path.startswith(p) for p in scope_paths)


def resolve_credentials(cfg: dict) -> tuple[str, str]:
    """Haal username/password op uit cfg of uit het .env bestand."""
    env = {}
    if cfg.get("env_file"):
        env = dotenv_values(cfg["env_file"])

    username = env.get(cfg.get("username_env", ""), "") or cfg.get("username", "")
    password = env.get(cfg.get("password_env", ""), "") or cfg.get("password", "")
    return username, password


# ── Browser acties ────────────────────────────────────────────────────────────

async def do_login(page: Page, login_cfg: dict, username: str, password: str) -> None:
    method = login_cfg.get("method", "form")

    if method == "none":
        return

    login_url = login_cfg["url"]
    print(f"  [login] Navigeer naar {login_url}")
    await page.goto(login_url, wait_until="networkidle")

    if method == "manual":
        print("  [login] Wacht op handmatige login — druk Enter als je bent ingelogd...")
        input()
        return

    if method == "form":
        sel = login_cfg.get("selectors", {})
        await page.fill(sel.get("username", "input[type='email']"), username)
        await page.fill(sel.get("password", "input[type='password']"), password)
        await page.click(sel.get("submit", "button[type='submit']"))
        await page.wait_for_load_state("networkidle", timeout=20_000)

        # Eenvoudige check: zijn we nog op de login-pagina?
        if any(kw in page.url.lower() for kw in ("login", "signin", "auth")):
            raise RuntimeError(
                f"Login lijkt mislukt — nog op: {page.url}\n"
                "Controleer je credentials in .env of de YAML-config."
            )
        print(f"  [login] Geslaagd ✓  (nu op: {page.url})")
        return

    raise ValueError(f"Onbekende login method: {method!r}  (kies: none, form, manual)")


async def expand_all(page: Page, expand_cfg: dict) -> None:
    """Klapt alle accordions, details en tabs uit op basis van config."""
    if not expand_cfg.get("enabled", True):
        return

    # <details> open zetten
    await page.evaluate("document.querySelectorAll('details').forEach(d => d.open = true)")

    # Klikken op accordion-triggers die nog dicht zijn
    extra_triggers = expand_cfg.get("click_selectors", [
        "summary",
        ".accordion-button",
        "[data-bs-toggle='collapse']",
        "[aria-expanded='false']",
        ".accordion-header button",
    ])
    for sel in extra_triggers:
        try:
            triggers = await page.query_selector_all(sel)
            for t in triggers:
                try:
                    expanded = await t.get_attribute("aria-expanded")
                    if expanded == "false":
                        await t.click(timeout=1_000)
                        await page.wait_for_timeout(150)
                except Exception:
                    pass
        except Exception:
            pass

    # Tab-panels forceren
    await page.evaluate("""
        document.querySelectorAll('[role="tabpanel"], .tab-pane').forEach(el => {
            el.style.display  = 'block';
            el.style.overflow = 'visible';
            el.classList.add('active', 'show');
        });
        document.querySelectorAll('[role="tab"]').forEach(t =>
            t.setAttribute('aria-selected', 'true')
        );
    """)

    # Eventuele custom JS uit de config
    for js in expand_cfg.get("custom_js", []):
        try:
            await page.evaluate(js)
        except Exception as e:
            print(f"    ⚠ custom_js mislukt: {e}")

    await page.wait_for_timeout(expand_cfg.get("wait_ms", 300))


async def page_to_markdown(page: Page, url: str,
                           content_cfg: dict, h2t: html2text.HTML2Text) -> str:
    """Haal content op en converteer naar Markdown."""
    content_el = None
    for sel in content_cfg.get("selectors", ["main", "article", ".content", "body"]):
        content_el = await page.query_selector(sel)
        if content_el:
            break

    html = await content_el.inner_html() if content_el else await page.content()

    # Verwijder ongewenste elementen via JS (nav, footer, enz.)
    exclude = content_cfg.get("exclude_selectors", [])
    if exclude and content_el:
        for sel in exclude:
            await page.evaluate(f"""
                el => el.querySelectorAll({sel!r}).forEach(n => n.remove())
            """, content_el)
        html = await content_el.inner_html()

    md    = h2t.handle(html).strip()
    title = await page.title()
    return f"\n\n---\n\n# {title}\n\n> Bron: {url}\n\n{md}"


async def collect_links(page: Page, base: str,
                        scope_paths: list[str], visited: set) -> list[str]:
    anchors = await page.query_selector_all("a[href]")
    links   = []
    for a in anchors:
        href = await a.get_attribute("href")
        if not href or href.startswith(("mailto:", "javascript:", "#")):
            continue
        full = clean_url(urljoin(base, href))
        if full not in visited and is_in_scope(full, base, scope_paths):
            links.append(full)
    return list(dict.fromkeys(links))


# ── Hoofd ─────────────────────────────────────────────────────────────────────

async def scrape(config_path: Path, force_visible: bool = False) -> Path:
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    base_url    = cfg["base_url"].rstrip("/")
    start_url   = cfg.get("start_url", base_url)
    scope_paths = cfg.get("scope_paths", [urlparse(start_url).path])
    output_md   = Path(cfg.get("output", "output.md"))
    headless    = not force_visible and cfg.get("headless", True)

    login_cfg   = cfg.get("login",   {"method": "none"})
    expand_cfg  = cfg.get("expand",  {})
    content_cfg = cfg.get("content", {})
    crawl_cfg   = cfg.get("crawl",   {})

    max_pages   = crawl_cfg.get("max_pages", 500)

    # Credentials
    username, password = "", ""
    if login_cfg.get("method") == "form":
        username, password = resolve_credentials(login_cfg)
        if not username or not password:
            sys.exit("❌  Geen credentials gevonden. Vul .env of stel username/password in de YAML in.")

    # html2text instellen
    h2t = html2text.HTML2Text()
    h2t.ignore_links  = False
    h2t.ignore_images = cfg.get("include_images", False)
    h2t.body_width    = 0
    h2t.protect_links = True
    h2t.wrap_links    = False

    visited:  set[str]  = set()
    to_visit: list[str] = [clean_url(start_url)]
    pages_md: list[str] = [f"# {cfg.get('title', 'Documentatie')}\n\n*Automatisch gegenereerd*\n"]

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless)
        ctx     = await browser.new_context(viewport={"width": 1440, "height": 900})
        page    = await ctx.new_page()

        # Login indien nodig
        if login_cfg.get("method", "none") != "none":
            await do_login(page, login_cfg, username, password)

        # Crawl
        while to_visit and len(visited) < max_pages:
            url = to_visit.pop(0)
            if url in visited:
                continue
            visited.add(url)
            print(f"  [{len(visited):>3}] {url}")

            try:
                await page.goto(url, wait_until="networkidle", timeout=30_000)
            except Exception as e:
                print(f"       ⚠ Overgeslagen: {e}")
                continue

            # Nieuwe links ontdekken
            new = await collect_links(page, base_url, scope_paths, visited | set(to_visit))
            to_visit.extend(new)

            # Accordions uitklappen
            await expand_all(page, expand_cfg)

            # Pagina → Markdown
            try:
                md = await page_to_markdown(page, url, content_cfg, h2t)
                pages_md.append(md)
            except Exception as e:
                print(f"       ⚠ Conversie mislukt: {e}")

        await browser.close()

    output_md.write_text("\n".join(pages_md), encoding="utf-8")
    print(f"\n✅  {len(visited)} pagina's → {output_md}")
    return output_md


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generieke docs scraper")
    parser.add_argument("config", help="Pad naar YAML-config (bijv. sites/mendrix.yaml)")
    parser.add_argument("--visible", action="store_true", help="Browser zichtbaar tonen")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        sys.exit(f"❌  Config niet gevonden: {config_path}")

    asyncio.run(scrape(config_path, force_visible=args.visible))
