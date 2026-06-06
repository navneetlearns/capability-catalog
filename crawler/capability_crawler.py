#!/usr/bin/env python3
"""
Capability Catalog Crawler

Crawls a platform UI (Journey Builder, Campaigns, Segments, Messaging)
and extracts UI elements into structured capability records.

Usage:
    1. Set PLATFORM_URL below to your platform URL
    2. Run:  python capability_crawler.py
    3. Browser opens -> complete login/OTP in the browser window
    4. Script saves session, then crawls modules automatically
    5. Output: ../screenshots/*.png, ../pages/*.json, ../capabilities/capabilities.json
"""

import json
import os
import time
import pathlib
from datetime import datetime

from playwright.sync_api import sync_playwright

# -- paths -----------------------------------------------------------------
BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
SCREENSHOTS_DIR = BASE_DIR / "screenshots"
PAGES_DIR = BASE_DIR / "pages"
CAPABILITIES_DIR = BASE_DIR / "capabilities"

for d in [SCREENSHOTS_DIR, PAGES_DIR, CAPABILITIES_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# -- config ----------------------------------------------------------------
PLATFORM_URL = "https://zono.digital"  # CHANGE THIS to your platform URL
SESSION_FILE = BASE_DIR / ".crawler_session.json"

MODULES = [
    {"name": "journey_builder", "label": "Journey Builder", "url_path": None},
    {"name": "campaigns",       "label": "Campaigns",       "url_path": None},
    {"name": "segments",        "label": "Segments",        "url_path": None},
    {"name": "messaging",       "label": "Messaging",       "url_path": None},
]


def extract_ui_elements(page) -> dict:
    """Extract all visible UI elements from the current page via JS injection."""
    return page.evaluate("""() => {
        const data = {
            url: window.location.href,
            title: document.title,
            timestamp: new Date().toISOString(),
            headings: [], buttons: [], links: [], menu_items: [],
            form_labels: [], dropdown_options: [], tabs: [], cards: [],
            table_headers: [], badges: [], toggles: [], accordions: [],
            all_text: []
        };
        // headings
        document.querySelectorAll('h1,h2,h3,h4,h5,h6,[class*="heading"],[class*="title"]').forEach(el => {
            const t = (el.textContent||'').trim();
            if(t&&t.length<200) data.headings.push({level:(el.tagName||'heading').toLowerCase(),text:t});
        });
        // buttons
        document.querySelectorAll('button,[role="button"],a[class*="btn"],a[class*="button"],.ant-btn,.MuiButton-root').forEach(el => {
            const t = (el.textContent||el.getAttribute('aria-label')||'').trim();
            if(t&&t.length<100) data.buttons.push({text:t,type:el.getAttribute('type')||'button',disabled:!!(el.disabled||el.hasAttribute('disabled'))});
        });
        // links
        document.querySelectorAll('a[href]:not([href="#"]):not([href=""])').forEach(el => {
            const t = (el.textContent||'').trim();
            if(t&&t.length<150) data.links.push({text:t,href:el.getAttribute('href')||''});
        });
        // menu items (sidebar, nav, etc)
        document.querySelectorAll('[role="menuitem"],.ant-menu-item,.MuiMenuItem-root,.nav-item,[class*="menuItem"],[class*="menu-item"],[class*="sidebar"] li,[class*="navigation"] li,[class*="sider"] li,li[class*="menu"]').forEach(el => {
            const t = (el.textContent||el.getAttribute('aria-label')||'').trim();
            if(t&&t.length<100&&!data.menu_items.some(m=>m.text===t)) data.menu_items.push({text:t,active:!!(el.classList.contains('active')||el.classList.contains('ant-menu-item-selected')),href:el.getAttribute('href')||el.dataset.path||''});
        });
        // form labels
        document.querySelectorAll('label,[class*="form-label"],[class*="FormLabel"],legend').forEach(el => {
            const t = (el.textContent||'').trim();
            if(t&&t.length<150) data.form_labels.push(t);
        });
        // dropdown options
        document.querySelectorAll('select option,[role="option"],.ant-select-item-option,.MuiMenuItem-root[role="option"],[class*="dropdown"] [class*="option"],[class*="select"] [class*="option"]').forEach(el => {
            const t = (el.textContent||el.getAttribute('aria-label')||'').trim();
            if(t&&t.length<100&&!data.dropdown_options.includes(t)) data.dropdown_options.push(t);
        });
        // tabs
        document.querySelectorAll('[role="tab"],.ant-tabs-tab,.MuiTab-root,[class*="tab"],button[class*="tab"]').forEach(el => {
            const t = (el.textContent||el.getAttribute('aria-label')||'').trim();
            if(t&&t.length<100) data.tabs.push({text:t,active:!!(el.classList.contains('active')||el.classList.contains('ant-tabs-tab-active')||el.getAttribute('aria-selected')==='true')});
        });
        // cards/panels
        document.querySelectorAll('[class*="card"],[class*="Card"],[class*="panel"],[class*="Panel"],.ant-card,.MuiCard-root').forEach(el => {
            const t = (el.textContent||'').trim().substring(0,200);
            const title = el.querySelector('h1,h2,h3,h4,h5,h6,[class*="header"],[class*="Header"],[class*="title"],[class*="Title"]');
            if(t||title) data.cards.push({title:title?(title.textContent||'').trim():'',preview:t.substring(0,100)});
        });
        // table headers
        document.querySelectorAll('th,[role="columnheader"]').forEach(el => {
            const t = (el.textContent||'').trim();
            if(t&&t.length<100) data.table_headers.push(t);
        });
        // badges/tags
        document.querySelectorAll('[class*="badge"],[class*="Badge"],[class*="tag"],[class*="Tag"],.ant-badge,.ant-tag,.MuiChip-root').forEach(el => {
            const t = (el.textContent||'').trim();
            if(t&&t.length<50) data.badges.push(t);
        });
        // toggles/switches
        document.querySelectorAll('[role="switch"],[class*="toggle"],[class*="switch"],.ant-switch,.MuiSwitch-root').forEach(el => {
            const label = el.getAttribute('aria-label')||(el.previousElementSibling?el.previousElementSibling.textContent:'')||'';
            data.toggles.push({label:label.trim(),checked:!!(el.checked||el.getAttribute('aria-checked')==='true'||el.classList.contains('ant-switch-checked'))});
        });
        // accordions/collapsible
        document.querySelectorAll('[class*="accordion"],[class*="Accordion"],[class*="collapse"],[class*="Collapse"],details summary').forEach(el => {
            const t = (el.textContent||'').trim();
            if(t&&t.length<150) data.accordions.push(t.substring(0,100));
        });
        // collect all short visible text
        const seen = new Set();
        document.querySelectorAll('p,span:not(:empty),div[class*="text"],div[class*="description"],li:not([class*="menu"])').forEach(el => {
            if(el.children.length>0) return;
            const t = (el.textContent||'').trim();
            if(t&&t.length>2&&t.length<150&&!seen.has(t)){seen.add(t);data.all_text.push(t);}
        });
        return data;
    }""")


def try_click_sidebar(page, label: str) -> bool:
    """Try to click a sidebar/menu item matching the label text."""
    selectors = [
        f'[class*="sidebar"] *:text-is("{label}")',
        f'[class*="sider"] *:text-is("{label}")',
        f'[class*="menu"] *:text-is("{label}")',
        f'[class*="navigation"] *:text-is("{label}")',
        f'nav *:text-is("{label}")',
        f'aside *:text-is("{label}")',
        f'button:has-text("{label}")',
        f'a:has-text("{label}")',
        f'[role="menuitem"]:has-text("{label}")',
        f'li:has-text("{label}")',
        f'div:has-text("{label}")',
    ]
    for sel in selectors:
        try:
            el = page.locator(sel).first
            if el.is_visible(timeout=2000):
                el.click()
                page.wait_for_load_state("networkidle", timeout=10000)
                return True
        except Exception:
            continue
    return False


def crawl_page(page, module_name: str, module_label: str) -> dict:
    """Screenshot + extract UI elements from current page."""
    print(f"  Crawling: {module_label} ...")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    ss_path = SCREENSHOTS_DIR / f"{module_name}_{ts}.png"
    page.screenshot(path=str(ss_path), full_page=True)
    print(f"  Screenshot -> {ss_path}")

    elements = extract_ui_elements(page)
    elements["module"] = module_name
    elements["module_label"] = module_label

    js_path = PAGES_DIR / f"{module_name}.json"
    with open(js_path, "w", encoding="utf-8") as f:
        json.dump(elements, f, indent=2, ensure_ascii=False)
    print(f"  UI JSON    -> {js_path}")
    print(f"    {len(elements['headings'])} headings, {len(elements['buttons'])} buttons, "
          f"{len(elements['menu_items'])} menu items, {len(elements['tabs'])} tabs, "
          f"{len(elements['cards'])} cards, {len(elements['table_headers'])} table headers")

    return elements


def crawl_subpages(page, module_name: str, module_label: str, elements: dict):
    """Click each tab and crawl sub-pages within the module."""
    for tab in elements.get("tabs", []):
        tab_text = tab["text"]
        if not tab_text:
            continue
        print(f"  Exploring tab: {tab_text}")
        try:
            tab_el = page.locator(
                f'[role="tab"]:has-text("{tab_text}"),'
                f'.ant-tabs-tab:has-text("{tab_text}"),'
                f'button:has-text("{tab_text}")'
            ).first
            if tab_el.is_visible(timeout=2000):
                tab_el.click()
                page.wait_for_load_state("networkidle", timeout=10000)
                time.sleep(1)

                sub_elems = extract_ui_elements(page)
                safe = tab_text.lower().replace(" ", "_").replace("/", "_")
                sub_path = PAGES_DIR / f"{module_name}_{safe}.json"
                with open(sub_path, "w", encoding="utf-8") as f:
                    json.dump(sub_elems, f, indent=2, ensure_ascii=False)

                ss_path = SCREENSHOTS_DIR / f"{module_name}_{safe}.png"
                page.screenshot(path=str(ss_path), full_page=True)
                print(f"    Tab '{tab_text}' -> {sub_path.name}")
        except Exception as e:
            print(f"    Tab '{tab_text}' skipped: {e}")


def build_capabilities(all_pages: list) -> list:
    """Convert extracted UI elements into structured capability records."""
    capabilities = []
    seen = set()

    for page_data in all_pages:
        module = page_data.get("module", "unknown")
        module_label = page_data.get("module_label", "")

        def add_cap(name, source, category=""):
            key = name.lower().strip()
            if key and key not in seen:
                seen.add(key)
                capabilities.append({
                    "id": f"{module}_{name.lower().replace(' ', '_').replace('/', '_')}",
                    "capability": name,
                    "module": module,
                    "module_label": module_label,
                    "category": category,
                    "source": source,
                    "discovered_at": page_data.get("timestamp", ""),
                })

        # buttons
        for btn in page_data.get("buttons", []):
            t = btn["text"]
            if any(i in t.lower() for i in ["login", "sign", "cancel", "close", "back"]):
                continue
            add_cap(t, f"button:{t}")

        # menu items
        for mi in page_data.get("menu_items", []):
            add_cap(mi["text"], f"menu:{mi['text']}")

        # headings (section-level)
        for h in page_data.get("headings", []):
            t = h["text"]
            if 5 < len(t) < 80:
                add_cap(t, f"heading:{t}")

        # tabs
        for tab in page_data.get("tabs", []):
            add_cap(tab["text"], f"tab:{tab['text']}", category="sub_feature")

        # cards (feature blocks)
        for card in page_data.get("cards", []):
            if card["title"]:
                add_cap(card["title"], f"card:{card['title']}")

        # table headers = data fields
        for th in page_data.get("table_headers", []):
            if len(th) > 2:
                add_cap(th, f"table_column:{th}", category="data_field")

        # dropdown options
        for opt in page_data.get("dropdown_options", []):
            if len(opt) > 2:
                add_cap(opt, f"dropdown:{opt}", category="option")

        # form labels = input fields
        for fl in page_data.get("form_labels", []):
            if len(fl) > 3:
                add_cap(fl, f"form:{fl}", category="input_field")

        # badges/tags = status indicators
        for b in page_data.get("badges", []):
            add_cap(b, f"badge:{b}", category="status_tag")

        # links
        for link in page_data.get("links", []):
            t = link["text"]
            if 3 < len(t) < 60:
                add_cap(t, f"link:{t}")

        # toggles = settings
        for tg in page_data.get("toggles", []):
            if tg["label"]:
                add_cap(tg["label"], f"toggle:{tg['label']}", category="setting")

    capabilities.sort(key=lambda c: (c["module"], c["capability"]))
    return capabilities


def main():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False, slow_mo=200)
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )

        # -- try loading saved session ----------------------------------------
        if SESSION_FILE.exists():
            print(f"[*] Loading saved session from {SESSION_FILE}")
            with open(SESSION_FILE) as f:
                storage = json.load(f)
            context.add_cookies(storage.get("cookies", []))
            page = context.new_page()
            page.goto(PLATFORM_URL, wait_until="networkidle", timeout=30000)
        else:
            page = context.new_page()
            page.goto(PLATFORM_URL, wait_until="networkidle", timeout=30000)

            print("\n" + "=" * 60)
            print("  Browser opened. Please LOG IN and complete OTP.")
            print("  Script auto-detects when you're logged in.")
            print("=" * 60 + "\n")

            # wait for login detection
            logged_in = False
            for attempt in range(180):  # 3 min
                try:
                    cur = page.url
                    login_paths = ["/dashboard", "/home", "/app", "/journey",
                                   "/campaign", "/segment", "/message"]
                    if any(p in cur for p in login_paths):
                        logged_in = True
                        break
                    indicators = [
                        '[class*="sidebar"]', '[class*="sider"]',
                        '[class*="dashboard"]', '[class*="menu"]',
                        'nav:has(a)', 'button:has-text("Logout")',
                        'button:has-text("Profile")',
                    ]
                    for sel in indicators:
                        if page.locator(sel).first.is_visible(timeout=500):
                            logged_in = True
                            break
                    if logged_in:
                        break
                except Exception:
                    pass
                time.sleep(1)
                if attempt % 15 == 0 and attempt > 0:
                    print(f"  Waiting for login... ({attempt+1}s)")

            if not logged_in:
                print("[!] Login timeout. Continuing anyway.")
            else:
                print(f"[✓] Logged in! Current URL: {page.url}")

        # -- save session ----------------------------------------------------
        storage = {
            "cookies": context.cookies(),
            "local_storage": page.evaluate("() => JSON.stringify(window.localStorage)"),
            "session_storage": page.evaluate("() => JSON.stringify(window.sessionStorage)"),
            "url": page.url,
            "saved_at": datetime.now().isoformat(),
        }
        with open(SESSION_FILE, "w") as f:
            json.dump(storage, f, indent=2)
        print(f"[*] Session saved to {SESSION_FILE}")

        # -- crawl modules ---------------------------------------------------
        print(f"\n[*] Starting crawl of {len(MODULES)} modules...\n")
        all_page_data = []

        for mod in MODULES:
            name = mod["name"]
            label = mod["label"]
            print(f"[{label}] Navigating...")

            if mod.get("url_path"):
                nav_url = PLATFORM_URL.rstrip("/") + "/" + mod["url_path"].lstrip("/")
                page.goto(nav_url, wait_until="networkidle", timeout=20000)
            else:
                found = try_click_sidebar(page, label)
                if not found:
                    print(f"  [!] Could not find '{label}' in sidebar. Trying URL...")
                    try:
                        page.goto(f"{PLATFORM_URL.rstrip('/')}/{name}",
                                  wait_until="networkidle", timeout=10000)
                    except Exception:
                        print(f"  [!] Skipping '{label}'.")
                        continue

            time.sleep(1)
            page.wait_for_load_state("networkidle", timeout=10000)

            elements = crawl_page(page, name, label)
            all_page_data.append(elements)
            crawl_subpages(page, name, label, elements)

        # -- build capabilities catalog --------------------------------------
        print(f"\n[*] Building capability catalog from {len(all_page_data)} pages...")
        capabilities = build_capabilities(all_page_data)

        output_path = CAPABILITIES_DIR / "capabilities.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump({
                "catalog_info": {
                    "platform": PLATFORM_URL,
                    "crawled_at": datetime.now().isoformat(),
                    "modules_crawled": len(all_page_data),
                    "total_capabilities": len(capabilities),
                },
                "capabilities": capabilities,
            }, f, indent=2, ensure_ascii=False)

        print(f"\n[✓] Capability catalog saved: {output_path}")
        print(f"    {len(capabilities)} capabilities across {len(MODULES)} modules")

        by_mod = {}
        for c in capabilities:
            by_mod.setdefault(c["module_label"], []).append(c)
        for mod_name, caps in by_mod.items():
            print(f"    {mod_name}: {len(caps)} capabilities")

        browser.close()
        print("\n[DONE] Crawl complete. Results saved to:")
        print(f"  Screenshots: {SCREENSHOTS_DIR}")
        print(f"  Page JSON:   {PAGES_DIR}")
        print(f"  Catalog:     {output_path}")


if __name__ == "__main__":
    main()
