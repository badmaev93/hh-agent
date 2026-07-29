"""Cross-checks data/apply_log.json against the applicant's real outcomes on
hh.ru/applicant/negotiations (Отказ / Просмотрен / Не просмотрен /
Собеседование). apply_log.json only records that a submission was attempted,
not what the employer actually did with it — this is the only way to see the
real funnel (rejections, silent views, interview invites) and to catch
applications that were logged as sent but never actually reached hh.ru at all
(compare returned urls against apply_log by vacancy id; anything missing
either failed silently before the apply.py verification fix, or was removed/
archived by the applicant).

Paginates the full negotiations list (20 items per page) and writes
data/negotiations_status.json: [{status, title, employer, url, raw_text}].
"""

import json
import os
import re

from playwright.sync_api import sync_playwright
import hh_common

OUT_FILE = os.path.join(hh_common.DATA_DIR, "negotiations_status.json")
DEBUG_DUMP = os.path.join(hh_common.DATA_DIR, "negotiations_page_dump.txt")

KNOWN_STATUSES = {
    "Отказ", "Не просмотрен", "Приглашение", "Приглашён", "Приглашена",
    "Просмотрено", "Ожидание", "Собеседование",
}


def vacancy_id(url):
    m = re.search(r"/vacancy/(\d+)", url or "")
    return m.group(1) if m else None


def parse_item(row):
    try:
        text = row.inner_text(timeout=2000)
    except Exception:
        text = ""
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    try:
        href = row.locator("a[href*='/vacancy/']").first.get_attribute("href", timeout=2000)
    except Exception:
        href = None

    status = lines[0] if lines else ""
    title = lines[1] if len(lines) > 1 else ""
    employer = lines[2] if len(lines) > 2 else ""
    return {"status": status, "title": title, "employer": employer, "url": href, "raw_text": text}


def main():
    all_items = []
    seen_urls = set()
    with sync_playwright() as p:
        context, page = hh_common.launch(p)

        page_num = 0
        while True:
            url = f"https://hh.ru/applicant/negotiations?page={page_num}" if page_num else "https://hh.ru/applicant/negotiations"
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(2500)

            if page_num == 0:
                try:
                    dump = page.locator("body").inner_text(timeout=5000)
                    with open(DEBUG_DUMP, "w", encoding="utf-8") as f:
                        f.write(dump)
                except Exception as e:
                    print("dump failed:", e)

            rows = page.locator("[data-qa='negotiations-item']")
            count = rows.count()
            print(f"page {page_num}: {count} items", flush=True)
            if count == 0:
                break

            new_on_page = 0
            for i in range(count):
                item = parse_item(rows.nth(i))
                key = item["url"] or item["raw_text"][:80]
                if key in seen_urls:
                    continue
                seen_urls.add(key)
                all_items.append(item)
                new_on_page += 1

            if new_on_page == 0:
                break
            page_num += 1
            if page_num > 20:
                print("safety cap: stopping at 20 pages")
                break

        hh_common.close_clean(context)

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_items, f, ensure_ascii=False, indent=2)
    print(f"Готово: {len(all_items)} записей -> {OUT_FILE}")
    print(f"Debug dump -> {DEBUG_DUMP}")


if __name__ == "__main__":
    main()
