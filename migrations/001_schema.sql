-- SolTicker Database Schema
-- Compatible with PostgreSQL / Supabase

-- Users table (extends Supabase auth.users)
CREATE TABLE IF NOT EXISTS public.profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email TEXT UNIQUE NOT NULL,
    tier TEXT DEFAULT 'free' CHECK (tier IN ('free', 'basic', 'pro')),
    stripe_customer_id TEXT,
    lookups_today INTEGER DEFAULT 0,
    last_lookup_reset DATE DEFAULT CURRENT_DATE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Products catalog
CREATE TABLE IF NOT EXISTS public.products (
    id BIGSERIAL PRIMARY KEY,
    platform TEXT NOT NULL CHECK (platform IN ('amazon', 'shopify', 'tiktok')),
    external_id TEXT NOT NULL,  -- ASIN, handle, or TikTok product ID
    title TEXT NOT NULL,
    url TEXT,
    image_url TEXT,
    category TEXT,
    vendor TEXT,
    tags TEXT[],
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(platform, external_id)
);

-- Price snapshots (daily tracking)
CREATE TABLE IF NOT EXISTS public.price_snapshots (
    id BIGSERIAL PRIMARY KEY,
    product_id BIGINT REFERENCES public.products(id) ON DELETE CASCADE,
    price DECIMAL(10, 2),
    original_price DECIMAL(10, 2),
    currency TEXT DEFAULT 'USD',
    units_sold INTEGER,
    rating DECIMAL(3, 2),
    review_count INTEGER,
    rank INTEGER,  -- Best Seller rank (Amazon)
    inventory_quantity INTEGER,  -- Shopify
    snapshot_date DATE DEFAULT CURRENT_DATE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Product matches (cross-platform linking)
CREATE TABLE IF NOT EXISTS public.product_matches (
    id BIGSERIAL PRIMARY KEY,
    query TEXT NOT NULL,
    amazon_product_id BIGINT REFERENCES public.products(id),
    shopify_product_id BIGINT REFERENCES public.products(id),
    tiktok_product_id BIGINT REFERENCES public.products(id),
    match_score DECIMAL(5, 2),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Price alerts
CREATE TABLE IF NOT EXISTS public.price_alerts (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID REFERENCES public.profiles(id) ON DELETE CASCADE,
    product_id BIGINT REFERENCES public.products(id) ON DELETE CASCADE,
    target_price DECIMAL(10, 2),
    alert_type TEXT DEFAULT 'below' CHECK (alert_type IN ('below', 'above', 'drop_percent')),
    is_active BOOLEAN DEFAULT TRUE,
    triggered_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Subscriptions
CREATE TABLE IF NOT EXISTS public.subscriptions (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID REFERENCES public.profiles(id) ON DELETE CASCADE,
    stripe_subscription_id TEXT UNIQUE,
    tier TEXT DEFAULT 'free',
    status TEXT DEFAULT 'active',
    current_period_start TIMESTAMPTZ,
    current_period_end TIMESTAMPTZ,
    cancel_at_period_end BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Lookup usage tracking
CREATE TABLE IF NOT EXISTS public.lookup_logs (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    query TEXT NOT NULL,
    platform TEXT,
    results_count INTEGER DEFAULT 0,
    response_time_ms INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_products_platform ON public.products(platform);
CREATE INDEX IF NOT EXISTS idx_products_external ON public.products(platform, external_id);
CREATE INDEX IF NOT EXISTS idx_products_title ON public.products USING gin(to_tsvector('english', title));
CREATE INDEX IF NOT EXISTS idx_price_snapshots_product ON public.price_snapshots(product_id);
CREATE INDEX IF NOT EXISTS idx_price_snapshots_date ON public.price_snapshots(snapshot_date);
CREATE INDEX IF NOT EXISTS idx_profiles_tier ON public.profiles(tier);
CREATE INDEX IF NOT EXISTS idx_lookup_logs_user ON public.lookup_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_lookup_logs_date ON public.lookup_logs(created_at);

-- RLS Policies
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.price_alerts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.subscriptions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own profile" ON public.profiles
    FOR SELECT USING (auth.uid() = id);
CREATE POLICY "Users can update own profile" ON public.profiles
    FOR UPDATE USING (auth.uid() = id);
CREATE POLICY "Users can view own alerts" ON public.price_alerts
    FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Users can view own subscriptions" ON public.subscriptions
    FOR SELECT USING (auth.uid() = user_id);

-- Public read access for products and snapshots
CREATE POLICY "Anyone can view products" ON public.products FOR SELECT USING (true);
CREATE POLICY "Anyone can view price snapshots" ON public.price_snapshots FOR SELECT USING (true);
CREATE POLICY "Anyone can view product matches" ON public.product_matches FOR SELECT USING (true);

-- Updated at trigger
CREATE OR REPLACE FUNCTION public.update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER set_updated_at_profiles
    BEFORE UPDATE ON public.profiles
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();

CREATE TRIGGER set_updated_at_products
    BEFORE UPDATE ON public.products
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();

CREATE TRIGGER set_updated_at_subscriptions
    BEFORE UPDATE ON public.subscriptions
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();
