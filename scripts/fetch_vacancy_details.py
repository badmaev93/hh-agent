"""Fetches the full description/skills/experience for every vacancy in
data/vacancies.json and writes data/vacancies_detailed.json.
"""

import json
import os

from playwright.sync_api import sync_playwright

import hh_common

IN_FILE = os.path.join(hh_common.DATA_DIR, "vacancies.json")
OUT_FILE = os.path.join(hh_common.DATA_DIR, "vacancies_detailed.json")


def scrape_vacancy(page, url):
    if not hh_common.is_safe_url(url):
        raise ValueError("Invalid URL scheme")
    page.goto(url, wait_until="domcontentloaded", timeout=45000)
    try:
        page.wait_for_selector("[data-qa='vacancy-description']", timeout=15000)
    except Exception:
        pass

    def text_of(selector):
        try:
            return page.locator(selector).first.inner_text(timeout=3000)
        except Exception:
            return ""

    description = text_of("[data-qa='vacancy-description']")
    experience = text_of("[data-qa='vacancy-experience']")
    skills = page.locator("[data-qa='skills-element']")
    try:
        skill_count = skills.count()
        key_skills = ", ".join(skills.nth(i).inner_text(timeout=1500) for i in range(skill_count))
    except Exception:
        key_skills = ""

    return {
        "description": description,
        "experience": experience,
        "key_skills": key_skills,
    }


def main():
    with open(IN_FILE, "r", encoding="utf-8") as f:
        vacancies = json.load(f)

    detailed = []
    with sync_playwright() as p:
        context, page = hh_common.launch(p)

        for i, v in enumerate(vacancies):
            try:
                extra = scrape_vacancy(page, v["url"])
            except Exception as e:
                print(f"[{i+1}/{len(vacancies)}] {v['title'][:40]!r} — ошибка: {e}", flush=True)
                continue

            entry = {**v, **extra}
            detailed.append(entry)
            print(f"[{i+1}/{len(vacancies)}] {v['title'][:40]!r} @ {v['employer'][:30]!r} — ok "
                  f"(desc {len(extra['description'])} симв.)", flush=True)

            with open(OUT_FILE, "w", encoding="utf-8") as f:
                json.dump(detailed, f, ensure_ascii=False, indent=2)

        hh_common.close_clean(context)

    print(f"\nГотово: {len(detailed)}/{len(vacancies)} -> {OUT_FILE}")


if __name__ == "__main__":
    main()
