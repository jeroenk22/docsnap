"""
find_spec.py
Zoekt de OpenAPI spec via de Confluence REST API (attachments).
Gebruikt de opgeslagen browsersessie (.profiles/atlassian) voor authenticatie.

Gebruik:
    python find_spec.py
    python find_spec.py 1866694660   # andere pagina-ID
"""

import asyncio
import json
import sys
from pathlib import Path

from playwright.async_api import async_playwright


PROFILE_DIR  = ".profiles/atlassian"
BASE_URL     = "https://mendrix.atlassian.net"


def looks_like_openapi(data) -> bool:
    return isinstance(data, dict) and (
        "paths" in data or "openapi" in data or "swagger" in data
    )


async def find_spec(page_id: str) -> None:
    async with async_playwright() as pw:
        profile_path = Path(PROFILE_DIR)
        profile_path.mkdir(parents=True, exist_ok=True)

        ctx  = await pw.chromium.launch_persistent_context(
            str(profile_path), headless=True,
            viewport={"width": 1440, "height": 900},
        )
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()

        # ── Stap 1: pagina storage-formaat ophalen (macro-config) ────────────
        storage_url = f"{BASE_URL}/wiki/rest/api/content/{page_id}?expand=body.storage"
        print(f"[1] Pagina storage ophalen: {storage_url}")
        resp = await page.goto(storage_url, wait_until="load", timeout=30_000)
        body = await resp.body()

        try:
            data = json.loads(body)
        except Exception:
            print("⚠ Geen JSON teruggekregen — ben je ingelogd?")
            print("  Draai eerst: python find_spec.py --login")
            await ctx.close()
            return

        storage = data.get("body", {}).get("storage", {}).get("value", "")
        print(f"   Storage-inhoud ({len(storage)} tekens):")
        print()
        print(storage[:3000])  # toon eerste 3000 tekens
        print()

        # ── Stap 2: JSON extraheren uit CDATA van swagger-integration macro ──
        import re
        matches = re.findall(r'<!\[CDATA\[(.*?)\]\]>', storage, re.DOTALL)
        saved = 0
        for i, cdata in enumerate(matches):
            cdata = cdata.strip()
            try:
                spec = json.loads(cdata)
                if looks_like_openapi(spec):
                    out = Path("openapi_spec.json")
                    out.write_text(json.dumps(spec, indent=2, ensure_ascii=False), encoding="utf-8")
                    print(f"✅  OpenAPI spec opgeslagen als {out}")
                    print(f"   Titel  : {spec.get('info', {}).get('title', '?')}")
                    print(f"   Versie : {spec.get('info', {}).get('version', '?')}")
                    print(f"   Paden  : {len(spec.get('paths', {}))}")
                    saved += 1
            except Exception:
                pass

        if not saved:
            print("⚠ Geen OpenAPI spec gevonden in CDATA-blokken.")
            Path("page_storage.xml").write_text(storage, encoding="utf-8")
            print("   Ruwe storage opgeslagen als page_storage.xml voor inspectie.")

        await ctx.close()


if __name__ == "__main__":
    if "--login" in sys.argv:
        # Handmatig inloggen en sessie opslaan
        async def login():
            async with async_playwright() as pw:
                ctx  = await pw.chromium.launch_persistent_context(
                    str(Path(PROFILE_DIR)), headless=False,
                    viewport={"width": 1440, "height": 900},
                )
                page = ctx.pages[0] if ctx.pages else await ctx.new_page()
                await page.goto(f"{BASE_URL}/wiki/spaces/MAD/pages/1866694660/2025.3",
                                wait_until="load", timeout=60_000)
                print("Log in en druk dan hier op Enter...")
                input()
                await ctx.close()
        asyncio.run(login())
    else:
        pid = sys.argv[1] if len(sys.argv) > 1 else "1866694660"
        asyncio.run(find_spec(pid))
