"""One-time manual login. hh.ru's captcha/2FA can't be scripted, so this just
opens a browser and waits for you to log in by hand, then saves the session
into the persistent profile for every later script to reuse.

Usage:
    venv/bin/python scripts/login.py
    (log in to hh.ru in the browser window that opens)
    touch data/done.flag
"""

import os
import time

from playwright.sync_api import sync_playwright

import hh_common

DONE_FLAG = os.path.join(hh_common.DATA_DIR, "done.flag")
TIMEOUT_SECONDS = 600

os.makedirs(hh_common.DATA_DIR, exist_ok=True)
if os.path.exists(DONE_FLAG):
    os.remove(DONE_FLAG)

with sync_playwright() as p:
    context, page = hh_common.launch(p)
    page.goto("https://hh.ru/account/login", wait_until="domcontentloaded", timeout=90000)

    print(f"Открыт браузер. Залогинься в hh.ru вручную. Жду файл {DONE_FLAG} (макс {TIMEOUT_SECONDS}с)...", flush=True)

    waited = 0
    while not os.path.exists(DONE_FLAG) and waited < TIMEOUT_SECONDS:
        time.sleep(3)
        waited += 3

    if os.path.exists(DONE_FLAG):
        print("Флаг найден, сохраняю сессию и закрываю браузер.", flush=True)
        os.remove(DONE_FLAG)
    else:
        print("Таймаут ожидания, закрываю браузер как есть.", flush=True)

    hh_common.close_clean(context)

print("Готово.")
