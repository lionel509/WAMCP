.PHONY: dev test lint format smoke db-migrate db-revision clean

dev:
	docker-compose up --build

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
