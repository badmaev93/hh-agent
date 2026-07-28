"""Best-effort check that cover letters sent by apply.py actually landed in
the employer chat thread. Runs automatically at the end of apply.py, or on
its own: `venv/bin/python scripts/verify_letters.py`.
"""

import glob
import json
import os

from playwright.sync_api import sync_playwright

import hh_common

LOG_FILE = os.path.join(hh_common.DATA_DIR, "apply_log.json")


def load_cover_letters():
    """url -> cover_letter, the text actually submitted.

    data/shortlist.json holds the final text apply.py put in the form
    (after any polishing pass) — it takes priority over data/scored_batch_*.json
    drafts, otherwise this compares against stale text and reports false
    negatives for every letter that got edited before sending.
    """
    letters = {}
    for f in glob.glob(os.path.join(hh_common.DATA_DIR, "scored_batch_*.json")):
        for v in json.load(open(f, encoding="utf-8")):
            if v.get("cover_letter") and v.get("url"):
                letters[v["url"]] = v["cover_letter"]

    shortlist_path = os.path.join(hh_common.DATA_DIR, "shortlist.json")
    if os.path.exists(shortlist_path):
        for v in json.load(open(shortlist_path, encoding="utf-8")):
            if v.get("cover_letter") and v.get("url"):
                letters[v["url"]] = v["cover_letter"]

    return letters


def find_negotiation_item(page, employer, title):
    items = page.locator("[data-qa='negotiations-item']")
    for i in range(items.count()):
        try:
            txt = items.nth(i).inner_text(timeout=2000)
        except Exception:
            continue
        if employer and employer.split()[-1] in txt:
            return items.nth(i)
    # fallback: match by title fragment
    for i in range(items.count()):
        try:
            txt = items.nth(i).inner_text(timeout=2000)
        except Exception:
            continue
        if title and title[:15] in txt:
            return items.nth(i)
    return None


def get_chat_text(page, item):
    item.locator("[data-qa='open_chat']").first.click(timeout=10000)

    chat_frame = None
    for attempt in range(3):
        page.wait_for_timeout(2500)
        for f in page.frames:
            if "chatik.hh.ru" in f.url:
                chat_frame = f
                break
        if chat_frame is not None:
            try:
                text = chat_frame.locator("body").inner_text(timeout=5000)
                if text.strip():
                    return text
            except Exception:
                pass
    return None


def main():
    log = json.load(open(LOG_FILE, encoding="utf-8"))
    letters = load_cover_letters()

    to_check = [
        a for a in log
        if a.get("status") in ("success", "success_unconfirmed")
        and a["url"] in letters
        and "letter_verified" not in a
    ]
    print(f"К проверке: {len(to_check)} откликов с ожидаемым письмом")

    if not to_check:
        return

    with sync_playwright() as p:
        context, page = hh_common.launch(p)
        page.goto("https://hh.ru/applicant/negotiations", wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(2000)

        for entry in to_check:
            expected = letters[entry["url"]]
            item = find_negotiation_item(page, entry.get("employer", ""), entry.get("title", ""))
            if item is None:
                entry["letter_verified"] = None
                entry["letter_verify_note"] = "negotiation item not found in list"
                print(f"  {entry['title']} @ {entry['employer']} -> не найдено в списке откликов")
                continue

            chat_text = get_chat_text(page, item)
            if chat_text is None:
                entry["letter_verified"] = None
                entry["letter_verify_note"] = "chat frame not found"
            else:
                snippet = expected[:80]
                entry["letter_verified"] = snippet in chat_text
                if not entry["letter_verified"]:
                    entry["letter_verify_note"] = "letter text not found in chat thread"

            print(f"  {entry['title']} @ {entry['employer']} -> letter_verified={entry.get('letter_verified')}")

            # вернуться к списку откликов для следующей проверки
            page.goto("https://hh.ru/applicant/negotiations", wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(1500)

        hh_common.close_clean(context)

    json.dump(log, open(LOG_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"apply_log.json обновлён -> {LOG_FILE}")


if __name__ == "__main__":
    main()
