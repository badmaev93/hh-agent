"""Sends applications from data/shortlist.json (an array of objects with at
least `url`, and optionally `title`, `employer`, `cover_letter`).

Anti-ban safety by design, do not remove without a good reason:
  - MAX_APPLICATIONS caps how many go out in one run.
  - A random 20-60s pause runs between each application.

Employer forms with extra screening questions are detected and skipped as
`needs_manual` — this script never guesses answers to those.
"""

import json
import os
import random
import time
from datetime import datetime, timezone

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

import hh_common

SHORTLIST_FILE = os.path.join(hh_common.DATA_DIR, "shortlist.json")
LOG_FILE = os.path.join(hh_common.DATA_DIR, "apply_log.json")

MAX_APPLICATIONS = int(os.environ.get("HH_MAX_APPLICATIONS", "10"))
MIN_DELAY = 20
MAX_DELAY = 60


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def apply_to_one(page, item):
    page.goto(item["url"], wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(1500)

    resp_btn = page.locator(
        "[data-qa='vacancy-response-link-top'], [data-qa='vacancy-response-link-bottom']"
    ).first

    if resp_btn.count() == 0:
        return {"status": "needs_manual", "reason": "no_response_button_found"}

    pre_click_url = page.url

    try:
        resp_btn.click(timeout=10000)
    except PWTimeout:
        return {"status": "fail", "reason": "click_timeout"}

    page.wait_for_timeout(1500)

    # Employer has custom free-text screening questions -> hh navigates to a
    # standalone /applicant/vacancy_response page instead of the popup. Bail out,
    # don't guess answers to questions like "your experience with Airflow?".
    if "vacancy_response" in page.url and page.url != pre_click_url:
        return {"status": "needs_manual", "reason": "employer_custom_questions_page"}

    # Employer requires answering additional screening questions -> bail out, don't guess.
    if page.locator("[data-qa='vacancy-response-popup-form-quick-questions']").count() > 0:
        return {"status": "needs_manual", "reason": "employer_screening_questions"}

    if item.get("cover_letter"):
        add_letter_btn = page.locator("[data-qa='add-cover-letter']")
        if add_letter_btn.count() > 0:
            try:
                add_letter_btn.first.click(timeout=5000)
                page.wait_for_timeout(800)
            except PWTimeout:
                pass

        letter_field = page.locator("[data-qa='vacancy-response-popup-form-letter-input']")
        if letter_field.count() > 0:
            try:
                letter_field.first.fill(item["cover_letter"])
            except Exception:
                pass

    submit_btn = page.locator(
        "[data-qa='vacancy-response-submit-popup'], [data-qa='vacancy-response-popup-form-submit']"
    ).first

    if submit_btn.count() > 0:
        try:
            submit_btn.click(timeout=10000)
        except PWTimeout:
            return {"status": "fail", "reason": "submit_timeout"}
        page.wait_for_timeout(1500)

    # Best-effort confirmation check: response link should now read differently / a success toast may appear.
    success_markers = page.locator(
        "[data-qa='vacancy-response-link-top'][disabled], .supernova-notification, [data-qa='notification']"
    )
    if success_markers.count() > 0:
        return {"status": "success"}

    return {"status": "success_unconfirmed"}


def main():
    with open(SHORTLIST_FILE, "r", encoding="utf-8") as f:
        shortlist = json.load(f)

    shortlist = shortlist[:MAX_APPLICATIONS]
    print(f"К отправке: {len(shortlist)} вакансий (лимит {MAX_APPLICATIONS})", flush=True)

    log = []
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            log = json.load(f)

    with sync_playwright() as p:
        context, page = hh_common.launch(p)

        for idx, item in enumerate(shortlist):
            print(f"[{idx + 1}/{len(shortlist)}] {item.get('title')} @ {item.get('employer')}", flush=True)
            try:
                result = apply_to_one(page, item)
            except Exception as e:
                result = {"status": "fail", "reason": str(e)}

            entry = {
                "url": item["url"],
                "title": item.get("title"),
                "employer": item.get("employer"),
                "timestamp": now_iso(),
                **result,
            }
            log.append(entry)
            print(f"  -> {entry['status']} ({entry.get('reason', '')})", flush=True)

            with open(LOG_FILE, "w", encoding="utf-8") as f:
                json.dump(log, f, ensure_ascii=False, indent=2)

            if idx < len(shortlist) - 1:
                delay = random.randint(MIN_DELAY, MAX_DELAY)
                print(f"  пауза {delay}с...", flush=True)
                time.sleep(delay)

        hh_common.close_clean(context)

    print(f"Готово. Лог -> {LOG_FILE}", flush=True)

    print("Проверяю доставку сопроводительных писем через чат...", flush=True)
    import verify_letters
    verify_letters.main()


if __name__ == "__main__":
    main()
