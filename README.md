# SolTicker — TikTok Shop Pricing Intelligence

Cross-platform price intelligence for TikTok Shop sellers.
Shows real pricing data across TikTok Shop, Amazon, and Shopify.

## Structure

```
solticker/
├── backend/          # FastAPI backend + scrapers
│   ├── api/          # API routes
│   ├── scrapers/     # Platform scrapers
│   ├── models/       # DB models
│   └── utils/        # Shared utilities
├── extension/        # Chrome Extension (MV3)
│   ├── popup/        # Extension popup UI
│   ├── background/   # Service worker
│   ├── content/      # Content scripts
│   └── assets/       # Icons, images
├── infra/            # Deployment configs
└── migrations/       # DB migrations
```

## Quick Start

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn api.main:app --reload

# Extension
# Load unpacked from extension/ in Chrome dev mode
```

## License
Proprietary — All rights reserved.
