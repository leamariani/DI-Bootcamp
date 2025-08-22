.PHONY: setup run run-ollama zip clean

setup:
	python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
	. .venv/bin/activate && pip install -r requirements.txt

run:
	. .venv/bin/activate && streamlit run app/app.py

run-ollama:
	ollama pull $(or $(OLLAMA_MODEL),llama3.1)

zip:
	python - <<'PY'\nimport shutil; shutil.make_archive('mini-mcp-research-notebook-part2', 'zip', '.')\nPY

clean:
	rm -rf __pycache__ .pytest_cache .mypy_cache
