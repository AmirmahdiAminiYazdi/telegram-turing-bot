#!/usr/bin/env bash
# نصب/آپدیت ربات روی سرور اوبونتو/دبیان. چند بار اجرا شدنش بی‌خطر است.
#   ./deploy/install.sh                 نصب تعاملی
#   ./deploy/install.sh --update        پشتیبان، git pull، ساخت مجدد
#   ./deploy/install.sh --firewall      فعال‌سازی ufw (۲۲ و ۸۰ و ۴۴۳)
# حالت غیرتعاملی: متغیرهای BOT_TOKEN, ADMIN_IDS, DOMAIN, CARD_NUMBER, CARD_HOLDER,
# ZARINPAL_MERCHANT_ID, SUPPORT_USERNAME را قبل از اجرا export کن و --yes بده.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT/.env"
YES=0 UPDATE=0 FIREWALL=0

log()  { printf '\033[1;32m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!!\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31mxx\033[0m %s\n' "$*" >&2; exit 1; }

SUDO=""
[ "$(id -u)" -eq 0 ] || SUDO="sudo"

ask() { # ask VAR "متن" [پیش‌فرض] [secret]
  local var="$1" prompt="$2" def="${3:-}" secret="${4:-}" val="${!1:-}"
  if [ -n "$val" ] || [ "$YES" -eq 1 ]; then printf -v "$var" '%s' "${val:-$def}"; return; fi
  if [ -n "$secret" ]; then read -r -s -p "$prompt: " val; echo; else read -r -p "$prompt [${def}]: " val; fi
  printf -v "$var" '%s' "${val:-$def}"
}

valid_token() { [[ "$1" =~ ^[0-9]{6,12}:[A-Za-z0-9_-]{30,}$ ]]; }
valid_ids()   { [[ -z "$1" || "$1" =~ ^-?[0-9]+(,-?[0-9]+)*$ ]]; }
valid_domain(){ [[ -z "$1" || "$1" =~ ^([a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}$ ]]; }

write_env() { # از متغیرهای محیطی .env می‌نویسد؛ فایل موجود را دست نمی‌زند
  [ -f "$ENV_FILE" ] && { log ".env موجود است؛ بدون تغییر ماند"; return; }
  valid_token "${BOT_TOKEN:-}" || die "BOT_TOKEN معتبر نیست"
  valid_ids "${ADMIN_IDS:-}" || die "ADMIN_IDS باید آیدی‌های عددی با کاما باشد"
  valid_domain "${DOMAIN:-}" || die "DOMAIN معتبر نیست"
  umask 077
  {
    echo "BOT_TOKEN=${BOT_TOKEN}"
    echo "ADMIN_IDS=${ADMIN_IDS:-}"
    echo "DB_PATH=/data/bot.sqlite3"
    echo "SUPPORT_USERNAME=${SUPPORT_USERNAME:-}"
    echo "CARD_NUMBER=${CARD_NUMBER:-}"
    echo "CARD_HOLDER=${CARD_HOLDER:-}"
    echo "ZARINPAL_MERCHANT_ID=${ZARINPAL_MERCHANT_ID:-}"
    echo "ZARINPAL_SANDBOX=${ZARINPAL_SANDBOX:-false}"
    echo "DOMAIN=${DOMAIN:-}"
    if [ -n "${DOMAIN:-}" ]; then echo "PUBLIC_BASE_URL=https://${DOMAIN}"; else echo "PUBLIC_BASE_URL="; fi
    echo "WEB_HOST=0.0.0.0"
    echo "WEB_PORT=8080"
  } > "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  log ".env ساخته شد (دسترسی 600)"
}

compose() {
  local profile=()
  grep -q '^DOMAIN=.\+' "$ENV_FILE" 2>/dev/null && profile=(--profile https)
  (cd "$ROOT" && $SUDO docker compose "${profile[@]}" "$@")
}

install_docker() {
  command -v docker >/dev/null && docker compose version >/dev/null 2>&1 && return
  log "نصب Docker از مخزن‌های رسمی توزیع"
  $SUDO apt-get update -y
  $SUDO apt-get install -y docker.io docker-compose-v2 || \
    die "نصب خودکار Docker نشد؛ Docker Engine و Compose v2 را دستی نصب کن: https://docs.docker.com/engine/install/"
  $SUDO systemctl enable --now docker
}

setup_firewall() {
  command -v ufw >/dev/null || $SUDO apt-get install -y ufw
  $SUDO ufw allow 22/tcp; $SUDO ufw allow 80/tcp; $SUDO ufw allow 443/tcp
  $SUDO ufw --force enable
  log "فایروال فعال شد (۲۲، ۸۰، ۴۴۳)"
}

wait_healthy() {
  log "منتظر سالم شدن ربات…"
  for _ in $(seq 1 40); do
    state="$(compose ps --format '{{.Health}}' bot 2>/dev/null | head -n1 || true)"
    [ "$state" = "healthy" ] && { log "ربات سالم است ✅"; return 0; }
    sleep 3
  done
  warn "ربات در زمان انتظار سالم نشد. لاگ:"; compose logs --tail=40 bot || true
  return 1
}

show_claim_hint() {
  local line
  line="$(compose logs bot 2>/dev/null | grep -F '/claim ' | tail -n1 || true)"
  [ -n "$line" ] && warn "ادمینی تعریف نشده بود. این پیام را در تلگرام به ربات بفرست تا ادمین شوی:
   ${line##*: }"
}

main() {
  for arg in "$@"; do
    case "$arg" in
      --yes) YES=1 ;; --update) UPDATE=1 ;; --firewall) FIREWALL=1 ;;
      -h|--help) sed -n '2,9p' "$0"; exit 0 ;;
      *) die "گزینه ناشناخته: $arg" ;;
    esac
  done

  if [ "$UPDATE" -eq 1 ]; then
    [ -f "$ENV_FILE" ] || die ".env پیدا نشد؛ اول نصب کن"
    log "پشتیبان قبل از آپدیت"; compose exec -T backup python -m bot.tools.backup \
      --db /data/bot.sqlite3 --out /backups --keep 14 || warn "پشتیبان‌گیری ناموفق بود"
    (cd "$ROOT" && git pull --ff-only) || die "git pull ناموفق"
    compose up -d --build
    wait_healthy
    return
  fi

  install_docker
  [ -f "$ENV_FILE" ] || {
    ask BOT_TOKEN "توکن ربات (از BotFather؛ نمایش داده نمی‌شود)" "" secret
    ask ADMIN_IDS "آیدی عددی ادمین‌ها با کاما (خالی = با /claim اولین ادمین را تعیین کن)" ""
    ask DOMAIN "دامنه برای HTTPS و درگاه پرداخت (خالی = بدون دامنه)" ""
    ask CARD_NUMBER "شماره کارت (کارت‌به‌کارت؛ اختیاری)" ""
    ask CARD_HOLDER "نام صاحب کارت" ""
    ask ZARINPAL_MERCHANT_ID "مرچنت زرین‌پال (اختیاری)" ""
    ask SUPPORT_USERNAME "یوزرنیم پشتیبانی بدون @ (اختیاری)" ""
  }
  write_env
  [ "$FIREWALL" -eq 1 ] && setup_firewall
  compose up -d --build
  wait_healthy || true
  show_claim_hint
  log "تمام شد. لاگ زنده: make logs"
}

# با INSTALL_LIB_ONLY=1 فقط توابع بارگذاری می‌شوند (برای تست)
[ "${INSTALL_LIB_ONLY:-0}" = "1" ] || main "$@"
