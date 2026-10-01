#!/bin/bash
uv pip install -q ruff black
echo "Running ruff format..."
.venv/bin/ruff format .
echo "Running ruff check..."
.venv/bin/ruff check . --fix
