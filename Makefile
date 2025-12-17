.PHONY: setup setup-playwright run prepare clean migrate import-snapshots fetch-calendar fetch-news generate-prompt capture-screenshots capture-symbol docker-up docker-up-playwright analyze reanalyze watch

# ========================================
# ONE-COMMAND ANALYSIS (Main Entry Points)
# ========================================

# Full end-to-end analysis - THE MAIN COMMAND
# Fetches data, captures screenshots, submits to ChatGPT, generates reports
analyze:
	@echo "🚀 Starting full analysis workflow..."
	./venv/bin/python run.py analyze

# Reanalyze - clears old data and runs fresh
reanalyze:
	@echo "🔄 Clearing old data and reanalyzing..."
	./venv/bin/python run.py reanalyze

# Watch for manual response file (fallback)
watch:
	./venv/bin/python run.py watch-responses

# ========================================
# SETUP
# ========================================

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

# Install Playwright for automated screenshots
setup-playwright:
	./venv/bin/pip install playwright
	./venv/bin/playwright install chromium
	@echo "Playwright setup complete!"

# Capture TradingView screenshots (requires Playwright)
capture-screenshots:
	./venv/bin/python run.py capture-screenshots

# Capture screenshots for a single symbol
capture-symbol:
	./venv/bin/python run.py capture-symbol $(SYMBOL)

# Docker: Start lightweight stack (n8n + advisor)
docker-up:
	docker-compose up -d

# Docker: Start with Playwright for automated screenshots
docker-up-playwright:
	docker-compose --profile playwright up -d

# Docker: Stop all containers
docker-down:
	docker-compose down
