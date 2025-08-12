# Makefile for Bluetooth Heatmap System

.PHONY: help install test run-api run-dashboard run-all docker-up docker-down clean

help:
	@echo "Available commands:"
	@echo "  make install       - Install dependencies"
	@echo "  make test         - Run tests"
	@echo "  make run-api      - Run FastAPI server"
	@echo "  make run-dashboard - Run dashboard"
	@echo "  make run-all      - Run all services locally"
	@echo "  make docker-up    - Start Docker services"
	@echo "  make docker-down  - Stop Docker services"
	@echo "  make clean        - Clean temporary files"

install:
	pip install -r requirements.txt

test:
	pytest tests/ -v

run-api:
	uvicorn src.api.app:app --reload --host 0.0.0.0 --port 8000

run-dashboard:
	python -c "from src.visualization.dashboard import Dashboard; Dashboard({}).run()"

run-all:
	@echo "Starting all services..."
	@make run-api &
	@make run-dashboard &
	@python src/main.py

docker-up:
	docker-compose up -d

docker-down:
	docker-compose down

docker-logs:
	docker-compose logs -f

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.pyd" -delete
	find . -type f -name ".coverage" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true

format:
	black src/ tests/
	isort src/ tests/

lint:
	flake8 src/ tests/
	mypy src/

init-db:
	python scripts/init_db.py

check-db:
	python scripts/init_db.py --check

reset-db:
	python scripts/init_db.py --reset