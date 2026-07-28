"""Pulls the text of your first resume on hh.ru into data/resume.txt.

If you have more than one resume, edit `resume_links.first` below to
`resume_links.nth(N)` for the one you want the agent to use.
"""

import os

from playwright.sync_api import sync_playwright

import hh_common

RESUME_OUT = os.path.join(hh_common.DATA_DIR, "resume.txt")

os.makedirs(hh_common.DATA_DIR, exist_ok=True)

with sync_playwright() as p:
    context, page = hh_common.launch(p)
    print("Открываю /applicant/resumes ...", flush=True)
    page.goto("https://hh.ru/applicant/resumes", wait_until="domcontentloaded", timeout=60000)
    print(f"URL после загрузки: {page.url}", flush=True)

    if "login" in page.url:
        print("Не залогинен — сначала запусти scripts/login.py")
        hh_common.close_clean(context)
        raise SystemExit(1)

    resume_links = page.locator("a[data-qa='resume-link']")
    count = resume_links.count()
    if count == 0:
        resume_links = page.locator("a[href*='/resume/']")
        count = resume_links.count()
    print(f"Найдено ссылок на резюме: {count}", flush=True)

    if count == 0:
        print("Резюме не найдено на странице /applicant/resumes")
        page.screenshot(path=os.path.join(hh_common.DATA_DIR, "debug_resumes_list.png"))
        hh_common.close_clean(context)
        raise SystemExit(1)

    href = resume_links.first.get_attribute("href")
    resume_url = href if href.startswith("http") else f"https://hh.ru{href}"
    print(f"Открываю резюме: {resume_url}", flush=True)

    page.goto(resume_url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(2000)

    body_text = page.locator("body").inner_text()

    with open(RESUME_OUT, "w", encoding="utf-8") as f:
        f.write(body_text)

    print(f"Резюме сохранено в {RESUME_OUT} ({len(body_text)} символов)")

    hh_common.close_clean(context)
