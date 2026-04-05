#!/bin/bash
# Entrypoint for Chainlit frontend — v2 (case law expansion)

# Use PORT from environment (Railway injects this) or default to 8080
PORT=${PORT:-8080}

echo "Starting Project Adil Frontend on port $PORT"
exec chainlit run app.py --host 0.0.0.0 --port $PORT

