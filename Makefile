# ──────────────────────────────────────────────────────────────────────
# BAAKI Credit Scoring — Common Commands
# ──────────────────────────────────────────────────────────────────────
# Usage:
#   make data      — Generate synthetic data
#   make train     — Train both cold start + full models
#   make serve     — Start the FastAPI server
#   make test      — Run pytest unit tests
#   make eval      — Run model evaluation
#   make pipeline  — Run the full pipeline (data → train → eval)
#   make docker    — Build and run with Docker
#   make clean     — Remove generated data and models
# ──────────────────────────────────────────────────────────────────────

.PHONY: data train serve test eval pipeline docker clean install

install:
	pip install -r requirements.txt

data:
	python scripts/generate_all_data.py

train:
	python -m src.training.train

serve:
	uvicorn src.api.app:app --host 0.0.0.0 --port 8000 --reload

test:
	pytest tests/ -v --tb=short

eval:
	python -m src.training.evaluate

pipeline: data train eval
	@echo "✅ Full pipeline complete"

docker:
	docker-compose up --build

clean:
	rm -f data/*.csv
	rm -f models/*.pkl models/*.png
	@echo "🧹 Cleaned data/ and models/"
