# PicoWave Assistant -- project-level convenience targets.
# (Individual generated C files are compiled automatically by the pipeline.)

PYTHON      ?= python3
export PYTHONPATH := src

.PHONY: help setup ollama test demo run voice clean distclean

help:
	@echo "PicoWave Assistant targets:"
	@echo "  make setup     Install system + Python deps (Ubuntu; runs scripts/install_ubuntu.sh)"
	@echo "  make ollama    Install Ollama and pull the local model"
	@echo "  make test      Run the unit tests"
	@echo "  make demo      Offline demo: batch commands via mock LLM + mock SDK"
	@echo "  make run       Interactive text mode (mock SDK)"
	@echo "  make voice     Interactive voice mode (needs mic + Ollama + PicoSDK)"
	@echo "  make clean     Remove build artifacts, logs, backups (keeps generated .c)"
	@echo "  make distclean Also remove generated .c files and CSVs"

setup:
	bash scripts/install_ubuntu.sh

ollama:
	bash scripts/setup_ollama.sh

test:
	$(PYTHON) tests/test_intent.py
	$(PYTHON) tests/test_codegen.py

demo:
	$(PYTHON) -m picowave.main --batch tests/sample_commands.txt --sdk mock --llm mock --no-tts

run:
	$(PYTHON) -m picowave.main --text --sdk mock

voice:
	$(PYTHON) -m picowave.main --sdk real --llm ollama

clean:
	rm -f build/* logs/*.log logs/*.jsonl backup/*.bak
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +
	@touch build/.gitkeep logs/.gitkeep backup/.gitkeep

distclean: clean
	rm -f generated/acquisition_*.c generated/*.csv
