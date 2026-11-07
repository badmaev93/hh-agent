"""For vacancies logged as needs_manual / employer_custom_questions_page,
opens the response form and pulls out the raw question text so the agent (or
you) can draft honest answers. Writes data/questions_extracted.json.

Never auto-answers these — screening questions are exactly the case where a
wrong guess (inflated experience, a made-up salary) does real damage.
"""

import json
import os

from playwright.sync_api import sync_playwright
import hh_common

LOG_FILE = os.path.join(hh_common.DATA_DIR, "apply_log.json")
OUT_FILE = os.path.join(hh_common.DATA_DIR, "questions_extracted.json")

log = json.load(open(LOG_FILE, encoding="utf-8"))
TARGETS = [
    (a["url"], a.get("employer", ""))
    for a in log
    if a.get("status") == "needs_manual" and a.get("reason") == "employer_custom_questions_page"
]

result = []

with sync_playwright() as p:
    context, page = hh_common.launch(p)

    for url, employer in TARGETS:
        if not hh_common.is_safe_url(url):
            result.append({"url": url, "employer": employer, "title": "", "questions": [], "note": "invalid_url_scheme"})
            continue

        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(1500)
        title = page.locator("h1").first.inner_text(timeout=3000)

        resp_btn = page.locator(
            "[data-qa='vacancy-response-link-top'], [data-qa='vacancy-response-link-bottom']"
        ).first
        if resp_btn.count() == 0:
            result.append({"url": url, "employer": employer, "title": title, "questions": [], "note": "no response button"})
            continue

        resp_btn.click(timeout=10000)
        page.wait_for_timeout(2000)

        if "vacancy_response" not in page.url:
            result.append({"url": url, "employer": employer, "title": title, "questions": [], "note": f"not a question page, url={page.url}"})
            continue

        full_text = page.locator("body").inner_text(timeout=5000)
        textareas = page.locator("textarea")
        questions = []
        for i in range(textareas.count()):
            ta = textareas.nth(i)
            try:
                q_text = ta.locator("xpath=preceding::*[self::label or self::h3 or self::div][1]").first.inner_text(timeout=2000)
            except Exception:
                q_text = None
            questions.append({"index": i, "question_guess": q_text})

        result.append({"url": url, "employer": employer, "title": title, "questions": questions, "page_text_dump": full_text[:3000]})

    hh_common.close_clean(context)

with open(OUT_FILE, "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

print(f"done -> {OUT_FILE}")
