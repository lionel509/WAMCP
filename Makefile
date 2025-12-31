.PHONY: dev dev-tunnel down test lint format smoke db-migrate db-revision clean logs-api logs-cloudflared tunnel tunnel-logs tunnel-url rebuild-clean

dev:
	docker-compose up --build

rebuild-clean:
	docker-compose down
	docker-compose build --no-cache
	docker-compose up

dev-tunnel:
	docker-compose --profile tunnel up --build

tunnel:
	docker-compose --profile tunnel up --build

tunnel-logs:
	docker-compose logs -f cloudflared

tunnel-url:
	@docker-compose logs --no-color cloudflared 2>/dev/null | grep -Eo 'https://[a-zA-Z0-9.-]+' | head -n 1 || echo "⚠️  Tunnel URL not found. Check 'make tunnel-logs' for details."

down:
	docker-compose down

test:
	pytest tests/unit tests/integration

smoke:
	docker-compose run --rm -e API_URL=http://wamcp-api-1:8000 api pytest tests/smoke

lint:
	ruff check .
	mypy .
	black --check .

format:
	ruff check --fix .
	black .

db-migrate:
	docker-compose run --rm api alembic upgrade head

db-revision:
	@read -p "Enter migration message: " msg; \
	alembic revision --autogenerate -m "$$msg"

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

logs-api:
	docker-compose logs -f api

logs-cloudflared:
	docker-compose logs -f cloudflared
