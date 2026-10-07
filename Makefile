IMAGE ?= artcraft-in-a-box:local
PORT  ?= 8080
VENV  ?= .venv

export PYTHONPATH := tools

.PHONY: help test lint check build smoke run site update check-updates clean

help:  ## List targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-14s %s\n", $$1, $$2}'

$(VENV)/.installed: requirements-dev.txt
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install -q -r requirements-dev.txt
	touch $@

test: $(VENV)/.installed  ## Unit tests with coverage
	$(VENV)/bin/pytest

lint: $(VENV)/.installed  ## Lint and format check
	$(VENV)/bin/ruff check tools tests
	$(VENV)/bin/ruff format --check tools tests

check: lint test  ## Lint + unit tests

build:  ## Build the image (IMAGE=artcraft-in-a-box:local)
	docker buildx build --load -t $(IMAGE) .

smoke: build  ## Build, then smoke-test the image
	tests/smoke.sh $(IMAGE)

run: build  ## Build, then serve on http://localhost:8080 (PORT=...)
	docker run --rm -p $(PORT):8080 $(IMAGE)

site:  ## Build the static site into dist/ without Docker
	rm -rf dist
	python3 -m artbox.build --manifest apps.json --site site --cache .cache --out dist

update:  ## Pin apps.json to the latest upstream releases
	python3 -m artbox.update --manifest apps.json

check-updates:  ## Report newer upstream releases without changing anything
	python3 -m artbox.update --manifest apps.json --check

clean:  ## Remove build output and caches
	rm -rf dist .cache .pytest_cache .ruff_cache .coverage
