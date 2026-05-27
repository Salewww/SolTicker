# SolTicker — Infrastructure & Deployment

## Vercel Deployment (Backend)

### Environment Variables

Set these in Vercel dashboard → Project → Settings → Environment Variables:

```
APP_URL=https://solticker.app
API_BASE=https://solticker-api.vercel.app

# Stripe
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_BASIC=price_...   # $29/mo
STRIPE_PRICE_PRO=price_...      # $59/mo

# Supabase
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_SERVICE_KEY=eyJ...
SUPABASE_ANON_KEY=eyJ...

# JWT
JWT_SECRET=your-secret-key-here
```

### vercel.json

```json
{
  "version": 2,
  "framework": "fastapi",
  "buildCommand": "pip install -r backend/requirements.txt",
  "outputDirectory": "backend",
  "routes": [
    { "src": "/api/(.*)", "dest": "backend/api/main.py" },
    { "src": "/(.*)", "dest": "backend/api/main.py" }
  ],
  "env": {
    "APP_ENV": "production"
  }
}
```

## Database Setup

1. Create new Supabase project (or reuse existing)
2. Run `migrations/001_schema.sql` in Supabase SQL Editor
3. Enable Email auth provider in Supabase Dashboard → Authentication

## Chrome Extension

1. Load unpacked in Chrome: `chrome://extensions` → Load unpacked → select `extension/`
2. For production: package as `.crx` and submit to Chrome Web Store
3. Required Chrome Web Store listing assets:
   - Extension name, description, category
   - Screenshots (1280x800)
   - Promotional images
   - Privacy policy URL

## Daily Scraper Cron

Set up a cron job (e.g., GitHub Actions or Vercel Cron) to run daily:

```
0 6 * * *  # 6 AM UTC
```

Run: `python -m scrapers.daily_update`

## Cost Estimate (Monthly)

| Service | Tier | Cost |
|---|---|---|
| Vercel | Pro | $20 |
| Supabase | Pro | $25 |
| Stripe | Pay-per-use | ~$0.30/transaction |
| Domain (solticker.app) | — | ~$12/year |
| Chrome Web Store | One-time | $5 |
| **Total** | | **~$45/mo** |

Revenue needed to break even: ~2 Basic subscribers ($29 × 2 = $58)
