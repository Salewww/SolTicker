#!/usr/bin/env bash
# ── SolTicker Local Dev Launcher ──────────────────────────────────
# Starts the FastAPI backend. Load the Chrome extension separately.
#
# Usage:   bash dev.sh
#          bash dev.sh test    (run quick smoke tests)
# ──────────────────────────────────────────────────────────────────

set -euo pipefail

BACKEND_DIR="$(cd "$(dirname "$0")/backend" && pwd)"
JWT_SECRET="${JWT_SECRET:-solticker-local-dev-secret}"

# Kill any existing uvicorn
pkill -f "uvicorn api.main" 2>/dev/null || true
sleep 1

echo ""
echo "🚀  SolTicker Backend"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  Health:     http://localhost:8000/health"
echo "  Search:     http://localhost:8000/api/search?q=earbuds&platform=amazon&limit=5"
echo "  BestSell:   http://localhost:8000/api/scrape/amazon/electronics?limit=10"
echo "  Auth:       http://localhost:8000/api/auth/signup (POST)"
echo ""
echo "  Chrome Ext: Load unpacked from extension/ at chrome://extensions"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

cd "$BACKEND_DIR"

if [[ "${1:-}" == "test" ]]; then
  echo "🧪  Running smoke tests..."
  sleep 3
  echo ""
  
  echo "── Health ──"
  curl -s http://localhost:8000/health | python3 -m json.tool
  echo ""
  
  echo "── Amazon Best Sellers (top 5) ──"
  curl -s "http://localhost:8000/api/scrape/amazon/electronics?limit=5" | python3 -c "
import sys, json
d = json.load(sys.stdin)
for p in d['products']:
    price = f'\${p[\"price\"]:.2f}' if p.get('price') else 'N/A'
    print(f'  #{p[\"rank\"]} {p[\"title\"][:50]:50} {price}')
"
  echo ""
  
  echo "── Amazon Search (wireless earbuds) ──"
  curl -s "http://localhost:8000/api/search?q=wireless+earbuds&platform=amazon&limit=5" | python3 -c "
import sys, json
d = json.load(sys.stdin)
r = d.get('results', [])
print(f'  Results: {len(r)}')
for p in r:
    price = f'\${p[\"price\"]:.2f}' if p.get('price') else 'N/A'
    print(f'  {p[\"title\"][:50]:50} {price}')
"
  echo ""
  
  echo "── Signup Test ──"
  curl -s -X POST http://localhost:8000/api/auth/signup \
    -H "Content-Type: application/json" \
    -d '{"email":"test@solticker.local","password":"password123"}' | python3 -m json.tool
  echo ""
  
  echo "── Login Test ──"
  curl -s -X POST http://localhost:8000/api/auth/login \
    -H "Content-Type: application/json" \
    -d '{"email":"test@solticker.local","password":"password123"}' | python3 -m json.tool
  echo ""
  
  echo "✅  Smoke tests complete"
  exit 0
fi

# Start server (dev.sh without args starts the server)
JWT_SECRET="$JWT_SECRET" uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
