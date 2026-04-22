#!/usr/bin/env bash
set -e

echo "=========================================="
echo "  BIOSIM RAILWAY STARTUP"
echo "=========================================="

# ─── VALIDATE ENV VARS ───
if [ -z "$DATABASE_URL" ]; then
    echo "❌ FATAL: DATABASE_URL is not set. Add your Neon connection string in Railway Variables."
    exit 1
fi

if [ -z "$SECRET_KEY" ]; then
    echo "❌ FATAL: SECRET_KEY is not set."
    exit 1
fi

echo "✅ Environment loaded"
echo "🔄 Running migrations..."

# ─── MIGRATIONS WITH RETRY ───
for i in {1..5}; do
    if alembic upgrade head; then
        echo "✅ Migrations complete"
        break
    else
        echo "⚠️ Migration attempt $i/5 failed. Retrying in 3s..."
        sleep 3
    fi
    if [ $i -eq 5 ]; then
        echo "❌ FATAL: Migrations failed after 5 attempts"
        exit 1
    fi
done

# ─── SEED DATA (idempotent) ───
echo "🌱 Running seeds..."
python -m app.db.seeds || echo "⚠️ Seed skipped or already exists"

# ─── START APP ───
echo "🚀 Starting Uvicorn on port ${PORT:-8000}"
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port "${PORT:-8000}" \
    --workers 1 \
    --proxy-headers