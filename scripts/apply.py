"""Sends applications from data/shortlist.json (an array of objects with at
least `url`, and optionally `title`, `employer`, `cover_letter`, `resume_name`).

Anti-ban safety by design, do not remove without a good reason:
  - MAX_APPLICATIONS caps how many go out in one run.
  - A random 20-60s pause runs between each application.

Employer forms with extra screening questions are detected and skipped as
`needs_manual` — this script never guesses answers to those.

Success verification reloads the vacancy page and checks whether the
response button is actually gone, and a missing submit button is now an
honest `fail`/`needs_manual` instead of a silently-swallowed
`success_unconfirmed` — see SKILL.md step 10 for the full reasoning behind
each status. Re-attempting a vacancy already logged as needs_manual/fail
does not work reliably (hh.ru shows a stripped-down UI on repeat clicks);
don't build an auto-retry loop around this script.
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


def select_resume(page, resume_name):
    """Best-effort resume switch in the response popup. UNTESTED beyond a
    single-resume account — resume-title/resume-detail only render a picker
    when the account has more than one resume. If no matching resume is
    found, leaves whatever hh.ru pre-selected (its own default) alone."""
    if not resume_name:
        return
    resume_title = page.locator("[data-qa='resume-title']").first
    if resume_title.count() == 0:
        return
    try:
        current = resume_title.inner_text(timeout=2000)
    except Exception:
        return
    if resume_name.strip().lower() in current.strip().lower():
        return  # already selected
    try:
        resume_title.click(timeout=3000)
        page.wait_for_timeout(500)
        option = page.get_by_text(resume_name, exact=False).first
        if option.count() > 0:
            option.click(timeout=3000)
            page.wait_for_timeout(500)
    except Exception:
        pass  # picker UI not present/changed — fall back to hh.ru's default resume


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

    select_resume(page, item.get("resume_name"))

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

    # A missing submit button used to be skipped silently here and still fell
    # through to "success_unconfirmed" below, logging a send that never
    # happened — this was the actual root cause behind a chunk of applications
    # that never reached hh.ru at all. Two real cases distinguished below:
    # inline hh.ru quick-questions (contact method, is the vacancy still open,
    # salary — data-qa^='vacancy-response-question', NOT an employer form)
    # collapse the popup down to just those fields with no letter/submit when
    # you re-click respond on a vacancy already touched by a previous attempt.
    # A genuinely fresh vacancy renders those same fields fine alongside a
    # working submit button, so presence alone isn't the signal — only
    # presence together with a missing submit is.
    if submit_btn.count() == 0:
        if page.locator("[data-qa^='vacancy-response-question']").count() > 0:
            return {"status": "needs_manual", "reason": "vacancy_response_quick_questions_no_submit"}
        return {"status": "fail", "reason": "no_submit_button_found"}

    try:
        submit_btn.click(timeout=10000)
    except PWTimeout:
        return {"status": "fail", "reason": "submit_timeout"}
    page.wait_for_timeout(2000)

    # Best-effort confirmation check: response link should now read differently / a success toast may appear.
    success_markers = page.locator(
        "[data-qa='vacancy-response-link-top'][disabled], .supernova-notification, [data-qa='notification']"
    )
    if success_markers.count() > 0:
        return {"status": "success"}

    # The old code stopped verifying here and always logged
    # success_unconfirmed regardless of what actually happened — that's how
    # applications got silently lost with no way to tell. Reload the vacancy
    # page and check whether the response button is actually gone; hh.ru
    # removes/replaces it once an application is registered.
    try:
        page.goto(item["url"], wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(1500)
        recheck_btn = page.locator(
            "[data-qa='vacancy-response-link-top'], [data-qa='vacancy-response-link-bottom']"
        )
        response_button_still_present = recheck_btn.count() > 0
    except Exception:
        return {"status": "success_unconfirmed", "reason": "verify_reload_failed"}

    if response_button_still_present:
        return {"status": "fail", "reason": "response_button_still_present_after_submit"}
    return {"status": "success"}


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
