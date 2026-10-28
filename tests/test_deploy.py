"""زیرساخت استقرار: کامپوز، Caddy، Dockerfile، اسکریپت نصب و هم‌خوانی .env.example."""
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
INSTALL = ROOT / "deploy" / "install.sh"
GOOD_TOKEN = "123456789:AAH-abcdefghijklmnopqrstuvwxyz012345"


def test_compose_services_are_hardened():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    svc = compose["services"]
    assert {"bot", "backup", "caddy"} <= set(svc)
    for name in ("bot", "backup"):
        s = svc[name]
        assert s["read_only"] is True and s["cap_drop"] == ["ALL"], name
        assert "no-new-privileges:true" in s["security_opt"], name
        assert s["restart"] == "unless-stopped"
        assert "ports" not in s, f"{name} نباید مستقیم روی هاست باز باشد"
    assert svc["caddy"]["profiles"] == ["https"]  # بدون دامنه بالا نمی‌آید
    assert svc["backup"]["volumes"][0].endswith(":ro")  # پشتیبان‌گیر فقط می‌خواند
    assert {"bot-data", "bot-backups"} <= set(compose["volumes"])
    assert svc["backup"]["healthcheck"] == {"disable": True}  # وگرنه همیشه unhealthy می‌شود


def test_caddy_exposes_only_callback_and_health():
    text = (ROOT / "deploy" / "Caddyfile").read_text()
    assert "/pay/callback /health" in text
    assert "respond \"not found\" 404" in text
    assert "Strict-Transport-Security" in text


def test_dockerfile_runs_unprivileged_with_healthcheck():
    text = (ROOT / "Dockerfile").read_text()
    assert re.search(r"^USER botuser$", text, re.M)
    assert "HEALTHCHECK" in text and "/health" in text
    assert "COPY .env" not in text


def test_dockerignore_keeps_secrets_out_of_image():
    ignored = (ROOT / ".dockerignore").read_text().split()
    assert ".env" in ignored and ".git" in ignored


def test_env_is_gitignored_and_example_has_no_secret():
    gitignore = (ROOT / ".gitignore").read_text().splitlines()
    assert ".env" in gitignore
    example = (ROOT / ".env.example").read_text()
    assert not re.search(r"\d{6,}:[A-Za-z0-9_-]{30,}", example)


def test_env_example_keys_match_config():
    keys = set(re.findall(r"^([A-Z_]+)=", (ROOT / ".env.example").read_text(), re.M))
    cfg = (ROOT / "bot" / "config.py").read_text()
    used = set(re.findall(r'env\.get\("([A-Z_]+)"', cfg)) | {"BOT_TOKEN"}
    assert keys - {"DOMAIN"} == used, f"ناهماهنگ: {keys ^ used}"  # DOMAIN فقط برای compose


# ---- install.sh ----
def _run(script: str, env: dict[str, str], tmp: Path) -> subprocess.CompletedProcess:
    full = {"PATH": os.environ["PATH"], "INSTALL_LIB_ONLY": "1", "HOME": str(tmp), **env}
    return subprocess.run(
        ["bash", "-c", f'source "{INSTALL}"; ROOT="{tmp}"; ENV_FILE="{tmp}/.env"; {script}'],
        env=full, capture_output=True, text=True, cwd=tmp,
    )


def test_install_script_syntax():
    assert subprocess.run(["bash", "-n", str(INSTALL)]).returncode == 0
    assert os.access(INSTALL, os.X_OK)


@pytest.mark.skipif(not shutil.which("shellcheck"), reason="shellcheck نصب نیست")
def test_install_script_shellcheck_clean():
    r = subprocess.run(["shellcheck", str(INSTALL)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout


def test_write_env_creates_private_file(tmp_path):
    r = _run("write_env", {"BOT_TOKEN": GOOD_TOKEN, "ADMIN_IDS": "12,34", "DOMAIN": "bot.example.com",
                           "CARD_NUMBER": "6037"}, tmp_path)
    assert r.returncode == 0, r.stderr
    env = tmp_path / ".env"
    assert oct(env.stat().st_mode & 0o777) == "0o600"
    body = env.read_text()
    assert f"BOT_TOKEN={GOOD_TOKEN}" in body and "ADMIN_IDS=12,34" in body
    assert "PUBLIC_BASE_URL=https://bot.example.com" in body and "DB_PATH=/data/bot.sqlite3" in body
    assert GOOD_TOKEN not in r.stdout + r.stderr  # توکن چاپ نمی‌شود


def test_write_env_without_domain_has_empty_public_url(tmp_path):
    r = _run("write_env", {"BOT_TOKEN": GOOD_TOKEN}, tmp_path)
    assert r.returncode == 0
    assert "PUBLIC_BASE_URL=\n" in (tmp_path / ".env").read_text()


@pytest.mark.parametrize("env,msg", [
    ({"BOT_TOKEN": "bad"}, "BOT_TOKEN"),
    ({"BOT_TOKEN": GOOD_TOKEN, "ADMIN_IDS": "12,abc"}, "ADMIN_IDS"),
    ({"BOT_TOKEN": GOOD_TOKEN, "DOMAIN": "not a domain"}, "DOMAIN"),
])
def test_write_env_rejects_bad_input_and_writes_nothing(tmp_path, env, msg):
    r = _run("write_env", env, tmp_path)
    assert r.returncode != 0 and msg in r.stderr
    assert not (tmp_path / ".env").exists()


def test_write_env_never_overwrites_existing(tmp_path):
    (tmp_path / ".env").write_text("KEEP=1\n")
    r = _run("write_env", {"BOT_TOKEN": GOOD_TOKEN}, tmp_path)
    assert r.returncode == 0 and (tmp_path / ".env").read_text() == "KEEP=1\n"
