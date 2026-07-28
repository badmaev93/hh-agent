#!/usr/bin/env bash
# Sets up hh-agent: python venv, Playwright, browser choice, ai-copywriter skill.
# Safe to re-run.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

echo "== hh-agent install =="
echo "Repo root: $REPO_ROOT"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 не найден. Установи Python 3.9+ и запусти install.sh снова." >&2
  exit 1
fi

# --- venv ---
if [ ! -d venv ]; then
  echo "-- creating venv --"
  python3 -m venv venv
fi

echo "-- installing playwright --"
venv/bin/pip install --upgrade pip >/dev/null
venv/bin/pip install playwright

# --- browser choice ---
echo
echo "Каким браузером пользоваться?"
echo "  1) chromium  - Playwright сам скачает Chromium, ничего трогать не нужно (по умолчанию)"
echo "  2) chrome    - твой установленный Google Chrome (нужны твои cookies/пароли для входа)"
echo "  3) edge      - твой установленный Microsoft Edge"
echo "  4) brave     - твой установленный Brave Browser"
read -r -p "Выбор [1-4, Enter = 1]: " BROWSER_CHOICE
case "${BROWSER_CHOICE:-1}" in
  2) HH_BROWSER=chrome ;;
  3) HH_BROWSER=edge ;;
  4) HH_BROWSER=brave ;;
  *) HH_BROWSER=chromium ;;
esac
echo "Выбрано: HH_BROWSER=$HH_BROWSER"

if [ "$HH_BROWSER" = "chromium" ]; then
  echo "-- downloading bundled Chromium (Playwright) --"
  venv/bin/playwright install chromium
else
  echo "-- registering system browser with Playwright ($HH_BROWSER) --"
  venv/bin/playwright install "$HH_BROWSER" || true
fi

# --- persist choice for future runs ---
cat > .env <<EOF
# Загружай перед каждым запуском: set -a; source .env; set +a
HH_BROWSER=$HH_BROWSER
EOF
echo "Сохранил выбор браузера в .env"

# --- ai-copywriter skill (used to polish cover letters) ---
echo
echo "-- installing ai-copywriter skill --"
if command -v npx >/dev/null 2>&1; then
  npx --yes skills add mikiarlo3/ai-copywriter --global || \
    echo "Не удалось поставить через 'npx skills'. Поставь вручную (см. ниже) или как Claude Code plugin."
else
  echo "npx не найден — пропускаю автоматическую установку ai-copywriter."
fi
echo "Ручная установка (Claude Code plugin), выполнить в самом Claude Code:"
echo "  /plugin marketplace add mikiarlo3/ai-copywriter"
echo "  /plugin install ai-copywriter@ai-copywriter"

mkdir -p data

echo
echo "== Готово =="
echo "Дальше:"
echo "  1. set -a; source .env; set +a"
echo "  2. venv/bin/python scripts/login.py   # залогинься в hh.ru вручную, потом: touch data/done.flag"
echo "  3. venv/bin/python scripts/fetch_resume.py"
echo "  4. Открой этот репозиторий в Claude Code — навык hh-job-search в .claude/skills/ подхватится сам."
echo
echo "Прочти README.md и docs/RESUME_TIPS.md перед первым запуском."
