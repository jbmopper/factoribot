# factoribot dev tasks. Run `make` for the list.
VENV := .venv
PY   := $(VENV)/bin/python
PIP  := $(VENV)/bin/pip

# Where Factorio writes `--dump-data` output. Override for other OSes/installs:
#   make dump FACTORIO_SCRIPT_OUTPUT=/path/to/factorio/script-output
FACTORIO_SCRIPT_OUTPUT ?= $(HOME)/Library/Application Support/factorio/script-output
DUMP_SRC := $(FACTORIO_SCRIPT_OUTPUT)/data-raw-dump.json

# The base-only dump the routing evidence is pinned to, and the one `find_dump`
# prefers. It is deliberately NOT the same file as `make dump` copies: that one
# carries whatever mods you play with. Override for another install:
#   make dump-base FACTORIO_APP=/path/to/factorio.app
FACTORIO_APP ?= $(HOME)/Library/Application Support/Steam/steamapps/common/Factorio/factorio.app
BASE_DUMP := data/data-raw-dump-2.0.77-base.json

.DEFAULT_GOAL := help
.PHONY: help setup setup-codex dump dump-base test ask chat analyze serve mcp plan play clean

help:
	@echo "factoribot dev tasks:"
	@echo "  make setup   create .venv and install the package (dev + openai extras)"
	@echo "  make setup-codex   install planning/MCP and register the project skill + server"
	@echo "  make plan SPEC=daemon/examples/balanced_six_outputs.json   offline optimization"
	@echo "  make mcp     run the MCP stdio server (normally started by Codex)"
	@echo "  make dump    copy data-raw-dump.json from Factorio's script-output"
	@echo "  make dump-base   regenerate the pinned base-only 2.0.77 dump the tests need"
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

setup-codex:
	@test -x $(PY) || python3 -m venv $(VENV)
	$(PIP) install -e 'daemon[dev,mcp]'
	$(PY) scripts/configure-codex.py

plan:
	$(PY) -m factoribot.cli plan --spec $(SPEC)

# Keep stdout exclusively for the MCP protocol.
mcp:
	@$(PY) -m factoribot.cli mcp

dump:
	@test -f "$(DUMP_SRC)" || { \
	  echo "No dump at $(DUMP_SRC)"; \
	  echo "Generate it first: run 'factorio --dump-data' (or set FACTORIO_SCRIPT_OUTPUT)."; \
	  exit 1; }
	@mkdir -p data
	cp "$(DUMP_SRC)" data/data-raw-dump.json
	@echo "Copied dump -> data/data-raw-dump.json"

# Dumps base-only prototypes from a temporary config/write/mod directory, so
# your own Factorio config, mods and saves are never read or written.
dump-base:
	@test -x "$(FACTORIO_APP)/Contents/MacOS/factorio" || { \
	  echo "No Factorio at $(FACTORIO_APP)"; \
	  echo "Set FACTORIO_APP=/path/to/factorio.app and re-run."; \
	  exit 1; }
	@tmp=$$(mktemp -d) && mkdir -p "$$tmp/write" "$$tmp/mods" && \
	  printf '[path]\nread-data=%s/Contents/data\nwrite-data=%s/write\n[general]\nlocale=en\n' \
	    "$(FACTORIO_APP)" "$$tmp" > "$$tmp/config.ini" && \
	  "$(FACTORIO_APP)/Contents/MacOS/factorio" --config "$$tmp/config.ini" \
	    --mod-directory "$$tmp/mods" --dump-data >/dev/null && \
	  mkdir -p data && \
	  cp "$$tmp/write/script-output/data-raw-dump.json" $(BASE_DUMP); \
	  status=$$?; rm -rf "$$tmp"; test $$status -eq 0 || exit $$status
	@echo "Wrote $(BASE_DUMP)"
	@shasum -a 256 $(BASE_DUMP)
	@echo "The routing evidence is pinned to be65dc36...670f60 (Factorio 2.0.77 build 84539)."

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
