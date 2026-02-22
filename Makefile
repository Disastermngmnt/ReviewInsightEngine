# Makefile for ReviewInsightEngine

.PHONY: help install install-dev test test-cov lint format clean run

help:
	@echo "Available commands:"
	@echo "  make install      - Install production dependencies"
	@echo "  make install-dev  - Install development dependencies"
	@echo "  make test         - Run tests"
	@echo "  make test-cov     - Run tests with coverage report"
	@echo "  make lint         - Run linters"
	@echo "  make format       - Format code"
	@echo "  make clean        - Clean temporary files"
	@echo "  make run          - Run the application"

install:
	pip install -r requirements.txt

install-dev:
	pip install -r requirements-dev.txt

test:
	pytest -v

test-cov:
	pytest --cov=core --cov=utils --cov=config --cov-report=html --cov-report=term

lint:
	flake8 core utils config tests --max-line-length=120
	mypy core utils config --ignore-missing-imports

format:
	black core utils config tests
	isort core utils config tests

clean:
	python -c "import pathlib; [p.unlink() for p in pathlib.Path('.').rglob('*.py[co]')]"
	python -c "import pathlib; [p.rmdir() for p in pathlib.Path('.').rglob('__pycache__')]"
	rm -rf .pytest_cache .coverage htmlcov .mypy_cache

run:
	python main.py
