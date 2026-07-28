"""Shared browser launch helper for all hh-agent scripts.

Supports picking a real browser (Chrome / Edge / Brave) so the agent can log
in with your normal cookies and passkeys, or falling back to Playwright's
bundled Chromium if you don't want to touch a real browser profile at all.
Select with the HH_BROWSER env var: chromium (default) | chrome | edge | brave.
"""

import json
import os
import platform
import shutil

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.environ.get("HH_DATA_DIR", os.path.join(REPO_ROOT, "data"))
PROFILE_DIR = os.path.join(DATA_DIR, "browser_profile")

BROWSER = os.environ.get("HH_BROWSER", "chromium").lower()


def _find_brave():
    system = platform.system()
    candidates = []
    if system == "Darwin":
        candidates = ["/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"]
    elif system == "Linux":
        candidates = ["/usr/bin/brave-browser", "/usr/bin/brave", "/snap/bin/brave"]
    elif system == "Windows":
        candidates = [
            os.path.expandvars(r"%PROGRAMFILES%\BraveSoftware\Brave-Browser\Application\brave.exe"),
            os.path.expandvars(r"%PROGRAMFILES(X86)%\BraveSoftware\Brave-Browser\Application\brave.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe"),
        ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return shutil.which("brave-browser") or shutil.which("brave")


def _mark_clean_exit():
    """Prevent Chromium's crash/restore-tabs prompt from piling up stale tabs
    after a prior run was killed instead of closed cleanly."""
    prefs_path = os.path.join(PROFILE_DIR, "Default", "Preferences")
    if not os.path.exists(prefs_path):
        return
    try:
        with open(prefs_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("profile", {})["exit_type"] = "Normal"
        data["profile"]["exited_cleanly"] = True
        with open(prefs_path, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception:
        pass


def launch(playwright, headless=False):
    os.makedirs(PROFILE_DIR, exist_ok=True)
    _mark_clean_exit()

    kwargs = dict(
        headless=headless,
        viewport={"width": 1280, "height": 900},
        args=["--restore-last-session=false"],
    )

    if BROWSER == "chromium":
        pass  # Playwright's bundled Chromium, downloaded by `playwright install chromium`.
    elif BROWSER == "chrome":
        kwargs["channel"] = "chrome"
    elif BROWSER == "edge":
        kwargs["channel"] = "msedge"
    elif BROWSER == "brave":
        brave_path = _find_brave()
        if not brave_path:
            raise SystemExit(
                "HH_BROWSER=brave, но исполняемый файл Brave не найден. "
                "Установи Brave Browser или выбери HH_BROWSER=chrome / edge / chromium."
            )
        kwargs["executable_path"] = brave_path
    else:
        raise SystemExit(
            f"Неизвестный HH_BROWSER={BROWSER!r}. Допустимые значения: chromium, chrome, edge, brave."
        )

    context = playwright.chromium.launch_persistent_context(PROFILE_DIR, **kwargs)
    # Close any tabs restored from a previous unclean shutdown, keep exactly one.
    for extra in context.pages[1:]:
        try:
            extra.close()
        except Exception:
            pass
    page = context.pages[0] if context.pages else context.new_page()
    return context, page


def close_clean(context):
    """Close context and mark exit as clean so the NEXT launch doesn't restore tabs."""
    context.close()
    _mark_clean_exit()
