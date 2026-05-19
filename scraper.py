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
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import html2text
import yaml
from dotenv import dotenv_values
from playwright.async_api import async_playwright, Page


def log(msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


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
    log(f"[login] Navigeer naar {login_url}")
    wait_mode = login_cfg.get("wait_until", "load")  # "networkidle" werkt niet op zware SPAs
    await page.goto(login_url, wait_until=wait_mode, timeout=60_000)

    if method == "manual":
        log("[login] Browser is open — log in via de browser en druk daarna hier op Enter...")
        input()
        log("[login] Wachten tot alle redirects afgerond zijn...")
        try:
            await page.wait_for_load_state("networkidle", timeout=15_000)
        except Exception:
            pass
        log(f"[login] Doorgaan (nu op: {page.url})")
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
        log(f"[login] Geslaagd ✓  (nu op: {page.url})")
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

    # Eventuele custom JS uitvoeren — in hoofdframe én in iframes
    frames_to_run = [page]
    if expand_cfg.get("include_frames", False):
        for frame in page.frames:
            if frame != page.main_frame:
                frames_to_run.append(frame)
                log(f"  [frame] {frame.url}")

    for js in expand_cfg.get("custom_js", []):
        for target in frames_to_run:
            try:
                await target.evaluate(js)
            except Exception as e:
                log(f"  ⚠ custom_js mislukt ({getattr(target, 'url', '?')}): {e}")

    await page.wait_for_timeout(expand_cfg.get("wait_ms", 300))


async def page_to_markdown(page: Page, url: str,
                           content_cfg: dict, h2t: html2text.HTML2Text) -> str:
    """Haal content op en converteer naar Markdown.
    Zoekt ook in child frames als include_frames is ingesteld."""
    selectors = content_cfg.get("selectors", ["main", "article", ".content", "body"])

    content_el = None
    content_target = page
    include_frames = content_cfg.get("include_frames", False)

    # Geef selector-prioriteit voorrang boven frame-prioriteit:
    # eerst per selector zoeken in hoofdframe, daarna in child frames.
    # Zo wint een specifiek iframe-selector van een generieke <main> in de shell.
    for sel in selectors:
        content_el = await page.query_selector(sel)
        if content_el:
            content_target = page
            log(f"         Content gevonden via '{sel}' in hoofdframe")
            break

        if include_frames:
            for frame in page.frames:
                if frame == page.main_frame:
                    continue
                try:
                    content_el = await frame.query_selector(sel)
                    if content_el:
                        content_target = frame
                        log(f"         Content gevonden via '{sel}' in frame: {frame.url}")
                        break
                except Exception:
                    pass
            if content_el:
                break

    html = await content_el.inner_html() if content_el else await page.content()

    # Verwijder ongewenste elementen via JS (nav, footer, enz.)
    exclude = content_cfg.get("exclude_selectors", [])
    if exclude and content_el:
        for sel in exclude:
            await content_target.evaluate(f"""
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
    start_time = time.time()

    log(f"Start: {cfg.get('title', 'Documentatie')}")
    log(f"  Startpagina : {start_url}")
    log(f"  Scope       : {scope_paths}")
    log(f"  Max pagina's: {max_pages}")
    log(f"  Output      : {output_md}")
    print()

    async with async_playwright() as pw:
        profile_dir = login_cfg.get("profile_dir")

        if profile_dir:
            # Persistent context: cookies/sessie worden bewaard tussen runs
            profile_path = Path(profile_dir)
            profile_path.mkdir(parents=True, exist_ok=True)
            log(f"[browser] Persistent profiel: {profile_path}")
            ctx  = await pw.chromium.launch_persistent_context(
                str(profile_path),
                headless=headless,
                viewport={"width": 1440, "height": 900},
            )
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        else:
            browser = await pw.chromium.launch(headless=headless)
            ctx     = await browser.new_context(viewport={"width": 1440, "height": 900})
            page    = await ctx.new_page()

        # Login indien nodig
        if login_cfg.get("method", "none") != "none":
            await do_login(page, login_cfg, username, password)
            print()

        # Crawl
        while to_visit and len(visited) < max_pages:
            url = to_visit.pop(0)
            if url in visited:
                continue
            visited.add(url)
            log(f"[{len(visited):>3}/{max_pages}] Laden: {url}")
            log(f"         Wachtrij: {len(to_visit)} pagina's nog te bezoeken")

            try:
                await page.goto(url, wait_until="networkidle", timeout=30_000)
            except Exception as e:
                if "interrupted by another navigation" in str(e):
                    log(f"         ↻ Redirect gedetecteerd, wachten en opnieuw proberen...")
                    try:
                        await page.wait_for_load_state("networkidle", timeout=10_000)
                    except Exception:
                        pass
                    try:
                        await page.goto(url, wait_until="networkidle", timeout=30_000)
                    except Exception as e2:
                        log(f"         ⚠ Overgeslagen na retry: {e2}")
                        continue
                else:
                    log(f"         ⚠ Overgeslagen: {e}")
                    continue

            # Wacht tot de content-selector in de DOM staat (Vue SPA kan nog renderen na networkidle)
            wait_for = crawl_cfg.get("wait_for_selector")
            if wait_for:
                try:
                    await page.wait_for_selector(wait_for, timeout=10_000)
                    log(f"         Content-selector gevonden")
                except Exception:
                    log(f"         ⚠ wait_for_selector '{wait_for}' niet gevonden, ga toch verder")

            # Wacht op iframes — Connect apps / embedded widgets laden apart
            if crawl_cfg.get("wait_for_frames"):
                frame_sel  = crawl_cfg["wait_for_frames"]
                frame_timeout = crawl_cfg.get("frame_timeout_ms", 20_000)
                log(f"         Wachten op iframe-content ('{frame_sel}') …")
                found = False
                deadline = time.time() + frame_timeout / 1000
                while time.time() < deadline and not found:
                    for frame in page.frames:
                        if frame == page.main_frame:
                            continue
                        try:
                            el = await frame.query_selector(frame_sel)
                            if el:
                                log(f"         iframe geladen: {frame.url}")
                                found = True
                                break
                        except Exception:
                            pass
                    if not found:
                        await page.wait_for_timeout(500)
                if not found:
                    log(f"         ⚠ iframe-selector '{frame_sel}' niet gevonden na {frame_timeout}ms")

            # Accordions/navigatie uitklappen vóór link-discovery
            await expand_all(page, expand_cfg)

            # Nieuwe links ontdekken (ná expand zodat ingeklapte nav-items ook zichtbaar zijn)
            known = len(visited) + len(to_visit)
            new = await collect_links(page, base_url, scope_paths, visited | set(to_visit))
            to_visit.extend(new)
            if new:
                log(f"         +{len(new)} nieuwe pagina's gevonden  →  {[u.split('/')[-1] for u in new[:5]]}{'...' if len(new) > 5 else ''}")

            # Pagina → Markdown
            try:
                md = await page_to_markdown(page, url, content_cfg, h2t)
                pages_md.append(md)
                title = await page.title()
                log(f"         ✓ Opgeslagen: \"{title}\"")
            except Exception as e:
                log(f"         ⚠ Conversie mislukt: {e}")

            elapsed = time.time() - start_time
            log(f"         Voortgang: {len(visited)} gedaan | {len(to_visit)} resterend | {elapsed:.0f}s verstreken")
            print()

        await ctx.close()  # werkt zowel voor persistent context als gewone browser

    elapsed = time.time() - start_time
    output_md.write_text("\n".join(pages_md), encoding="utf-8")
    print()
    log(f"✅  Klaar! {len(visited)} pagina's gescraped in {elapsed:.0f}s → {output_md}")
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
