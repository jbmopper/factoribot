# factoribot dev tasks. Run `make` for the list.
VENV := .venv
PY   := $(VENV)/bin/python
PIP  := $(VENV)/bin/pip

# Where Factorio writes `--dump-data` output. Override for other OSes/installs:
#   make dump FACTORIO_SCRIPT_OUTPUT=/path/to/factorio/script-output
FACTORIO_SCRIPT_OUTPUT ?= $(HOME)/Library/Application Support/factorio/script-output
DUMP_SRC := $(FACTORIO_SCRIPT_OUTPUT)/data-raw-dump.json

.DEFAULT_GOAL := help
.PHONY: help setup dump test ask chat analyze serve play clean

help:
	@echo "factoribot dev tasks:"
	@echo "  make setup   create .venv and install the package (dev + openai extras)"
	@echo "  make dump    copy data-raw-dump.json from Factorio's script-output"
	@echo "  make test    run the test suite"
	@echo "  make ask Q='purple science, AM2'   one-off LLM query"
	@echo "  make chat    interactive multi-turn chat in the terminal"
	@echo "  make analyze BP=data/bp1.txt   analyze a blueprint string (offline)"
	@echo "  make serve   run the UDP daemon for the in-game mod (ARGS='--verbose')"
	@echo "  make play    start daemon + launch Factorio with the UDP flag (macOS)"
	@echo "  make clean   remove .venv and caches"

setup:
	python3 -m venv $(VENV)
	$(PIP) install -U pip
	$(PIP) install -e 'daemon[dev,openai]'
	@echo "Installed. Next: 'make dump' (after a Factorio --dump-data), then 'make test'."

dump:
	@test -f "$(DUMP_SRC)" || { \
	  echo "No dump at $(DUMP_SRC)"; \
	  echo "Generate it first: run 'factorio --dump-data' (or set FACTORIO_SCRIPT_OUTPUT)."; \
	  exit 1; }
	@mkdir -p data
	cp "$(DUMP_SRC)" data/data-raw-dump.json
	@echo "Copied dump -> data/data-raw-dump.json"

test:
	$(PY) -m pytest daemon/tests -q

ask:
	$(PY) -m factoribot.cli ask "$(Q)"

chat:
	$(PY) -m factoribot.cli chat $(ARGS)

analyze:
	$(PY) -m factoribot.cli analyze --bp $(BP) $(ARGS)

serve:
	$(PY) -m factoribot.cli serve $(ARGS)

play:
	./scripts/factoribot-play.command

clean:
	rm -rf $(VENV) .pytest_cache daemon/factoribot.egg-info
	find daemon -name __pycache__ -type d -prune -exec rm -rf {} +
