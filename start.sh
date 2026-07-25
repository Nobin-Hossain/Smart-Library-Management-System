#!/bin/bash

# ─────────────────────────────────────────────
#  SmartLibrary — Manual Start Script
# ─────────────────────────────────────────────

set -e  # Exit immediately on error

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$PROJECT_DIR/venv"

echo ""
echo "╔══════════════════════════════════════╗"
echo "║        SmartLibrary Startup          ║"
echo "╚══════════════════════════════════════╝"
echo ""

# ── 1. Activate virtual environment ──────────
if [ -d "$VENV_DIR" ]; then
    echo "▶ Activating virtual environment..."
    source "$VENV_DIR/bin/activate"
else
    echo "⚠  No virtual environment found at $VENV_DIR"
    echo "   Running with system Python. To create one:"
    echo "   python -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
    echo ""
fi

# ── 2. Move into project directory ───────────
cd "$PROJECT_DIR"

# ── 3. Apply database migrations ─────────────
echo "▶ Applying migrations..."
python manage.py migrate

# ── 4. Collect static files (optional) ───────
# Uncomment the line below if you use WhiteNoise or serve static files:
# python manage.py collectstatic --noinput

# ── 5. Start the development server ──────────
echo ""
echo "▶ Starting development server at http://127.0.0.1:8000/"
echo "   Press Ctrl+C to stop."
echo ""
python manage.py runserver
