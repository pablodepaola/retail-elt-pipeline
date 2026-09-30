.PHONY: help setup sample run backfill quality dbt test docs clean status publish-dry lineage

VENV ?= .venv
PY   := $(VENV)/bin/python
DBT  := $(VENV)/bin/dbt
export DBT_DUCKDB_PATH := $(CURDIR)/data/warehouse/retail.duckdb

help:
	@echo "make setup        - create venv + install pinned deps + dbt deps"
	@echo "make sample       - (re)generate the committed Olist-schema sample"
	@echo "make run          - full incremental pipeline on the sample (dry-run serve)"
	@echo "make backfill S=YYYY-MM-DD E=YYYY-MM-DD - backfill a date range"
	@echo "make quality      - run the Great Expectations raw gate"
	@echo "make dbt          - dbt build (+tests) only"
	@echo "make test         - python unit tests"
	@echo "make docs         - generate dbt docs + lineage (open dbt/target/index.html)"
	@echo "make status       - show watermark + recent run history"
	@echo "make clean        - wipe raw/warehouse/exports/state (keeps sample)"

setup:
	python3 -m venv $(VENV)
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -r requirements.txt pytest==8.3.4
	$(DBT) deps --project-dir dbt --profiles-dir dbt

sample:
	$(PY) -m pipeline.generate_sample

run:
	$(PY) -m pipeline.cli --sample run --dry-run

backfill:
	$(PY) -m pipeline.cli --sample backfill --start $(S) --end $(E) --dry-run

quality:
	$(PY) -m pipeline.cli --sample quality

dbt:
	$(DBT) build --project-dir dbt --profiles-dir dbt --target dev

test:
	$(PY) -m pytest -q

docs:
	$(DBT) docs generate --project-dir dbt --profiles-dir dbt --target dev
	@echo "open dbt/target/index.html for the lineage graph"

status:
	$(PY) -m pipeline.cli --sample status

clean:
	rm -rf data/raw data/warehouse data/exports pipeline/state/watermark.json
	mkdir -p data/raw data/warehouse data/exports
	touch data/raw/.gitkeep data/warehouse/.gitkeep data/exports/.gitkeep
