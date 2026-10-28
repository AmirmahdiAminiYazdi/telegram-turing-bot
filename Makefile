.PHONY: install test lint cov run up up-https down logs ps backup update shell
install:  ## وابستگی‌های توسعه
	pip install -r requirements-dev.txt
test:     ## تست‌ها
	python -m pytest -q
cov:      ## تست با پوشش
	python -m pytest -q --cov=bot --cov-report=term-missing
lint:
	ruff check .
run:      ## اجرای محلی (با .env)
	set -a; . ./.env; set +a; python -m bot.main
up:       ## اجرا با Docker (بدون HTTPS)
	docker compose up -d --build
up-https: ## اجرا با Docker + Caddy (DOMAIN لازم است)
	docker compose --profile https up -d --build
down:
	docker compose --profile https down
logs:
	docker compose logs -f --tail=100 bot
ps:
	docker compose --profile https ps
backup:   ## پشتیبان فوری
	docker compose exec -T backup python -m bot.tools.backup --db /data/bot.sqlite3 --out /backups --keep 14
update:   ## آپدیت امن: پشتیبان، pull، ساخت مجدد
	./deploy/install.sh --update
shell:
	docker compose exec bot sh
