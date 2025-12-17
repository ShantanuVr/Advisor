.PHONY: setup run prepare clean migrate import-snapshots fetch-calendar fetch-news generate-prompt

# Create virtual environment and install dependencies
setup:
	python3 -m venv venv
	./venv/bin/pip install --upgrade pip
	./venv/bin/pip install -r requirements.txt
	./venv/bin/alembic upgrade head
	@echo "Setup complete! Activate venv with: source venv/bin/activate"

# Run the portal server
run:
	./venv/bin/python run.py serve

# Run full data collection + prompt generation
prepare:
	./venv/bin/python run.py prepare

# Import screenshots from inbox
import-snapshots:
	./venv/bin/python run.py import-snapshots

# Fetch ForexFactory calendar
fetch-calendar:
	./venv/bin/python run.py fetch-calendar

# Fetch news
fetch-news:
	./venv/bin/python run.py fetch-news

# Generate today's analysis prompt
generate-prompt:
	./venv/bin/python run.py generate-prompt

# Run database migrations
migrate:
	./venv/bin/alembic upgrade head

# Clean generated files (keeps database)
clean:
	rm -rf data/prompts/*
	rm -rf data/responses/*
	rm -rf data/reports/*
	@echo "Cleaned generated files"

# Full reset (removes everything including database)
reset:
	rm -rf data/prompts/*
	rm -rf data/responses/*
	rm -rf data/reports/*
	rm -rf data/screenshots/*
	rm -f data/advisor.db
	./venv/bin/alembic upgrade head
	@echo "Full reset complete"
