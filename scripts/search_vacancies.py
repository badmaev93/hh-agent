"""Search hh.ru with one or more free-text queries and dump unique results
to data/vacancies.json. Each run OVERWRITES that file — copy it aside
(`cp data/vacancies.json data/vacancies_<label>.json`) between passes if you
want to run several searches (e.g. remote + a specific city) and merge them
later, deduped by url.

Usage:
    HH_REMOTE=1 venv/bin/python scripts/search_vacancies.py "query1" "query2" ...
    HH_CITY=Moscow venv/bin/python scripts/search_vacancies.py "query1" ...
"""

import json
import os
import re
import sys
import urllib.request
import urllib.parse

from playwright.sync_api import sync_playwright

import hh_common

OUT_FILE = os.path.join(hh_common.DATA_DIR, "vacancies.json")


def resolve_area_id(city_name):
    """Resolve a city name to an HH area id via the public (unauthenticated) areas dictionary."""
    if not city_name:
        return None
    with urllib.request.urlopen("https://api.hh.ru/areas") as resp:
        countries = json.loads(resp.read().decode("utf-8"))

    def walk(nodes):
        for node in nodes:
            if node.get("name", "").lower() == city_name.lower():
                return node["id"]
            found = walk(node.get("areas", []))
            if found:
                return found
        return None

    return walk(countries)


def build_search_url(query, area_id=None, remote=False, page=0):
    params = {
        "text": query,
        "order_by": "relevance",
        "items_on_page": 50,
        "page": page,
    }
    if area_id:
        params["area"] = area_id
    if remote:
        params["schedule"] = "remote"
    return "https://hh.ru/search/vacancy?" + urllib.parse.urlencode(params)


def scrape_page(page):
    cards = page.locator("[data-qa='vacancy-serp__vacancy']")
    count = cards.count()
    results = []
    for i in range(count):
        card = cards.nth(i)
        try:
            title_el = card.locator("a[data-qa='serp-item__title']").first
            title = title_el.inner_text(timeout=2000)
            href = title_el.get_attribute("href", timeout=2000)
        except Exception:
            continue
        try:
            employer = card.locator("[data-qa='vacancy-serp__vacancy-employer']").first.inner_text(timeout=2000)
        except Exception:
            employer = ""
        try:
            salary = card.locator("[data-qa^='vacancy-serp__vacancy-compensation']").first.inner_text(timeout=2000)
        except Exception:
            salary = ""
        results.append({
            "title": title,
            "url": href.split("?")[0] if href else "",
            "employer": employer,
            "salary": salary,
        })
    return results


def main():
    queries = sys.argv[1:]
    if not queries:
        print("Usage: search_vacancies.py 'query1' 'query2' ...")
        print("Env vars: HH_CITY (город), HH_REMOTE=1 (удалёнка)")
        raise SystemExit(1)

    os.makedirs(hh_common.DATA_DIR, exist_ok=True)

    city = os.environ.get("HH_CITY")
    remote = os.environ.get("HH_REMOTE") == "1"

    area_id = None
    if city:
        try:
            area_id = resolve_area_id(city)
            print(f"Город '{city}' -> area_id={area_id}")
        except Exception as e:
            print(f"Не удалось резолвить город '{city}': {e}")

    all_results = {}

    with sync_playwright() as p:
        context, page = hh_common.launch(p)

        for query in queries:
            url = build_search_url(query, area_id=area_id, remote=remote)
            print(f"Поиск: {query} -> {url}", flush=True)
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(2000)

            results = scrape_page(page)
            print(f"  найдено на странице: {len(results)}", flush=True)
            if not results:
                safe_query = re.sub(r'[^\w\-]', '_', query[:20])
                debug_path = os.path.join(hh_common.DATA_DIR, f"debug_search_{safe_query}.png")
                page.screenshot(path=debug_path)
                print(f"  0 результатов, скриншот -> {debug_path}")

            for r in results:
                if r["url"]:
                    all_results[r["url"]] = r

        hh_common.close_clean(context)

    out = list(all_results.values())
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"Всего уникальных вакансий: {len(out)} -> {OUT_FILE}")


if __name__ == "__main__":
    main()
