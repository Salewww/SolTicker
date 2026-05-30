/**
 * SolTicker Chrome Extension — Popup Script
 * Handles search, auto-detection, and UI updates.
 */

// API endpoint — change for production
const API_BASE = 'https://solticker.app';
// const API_BASE = 'http://localhost:8000'; // Dev

// State
let currentTab = null;
let userTier = 'free';
let lookupsToday = 0;
const FREE_LIMIT = 5;

// Initialize
document.addEventListener('DOMContentLoaded', async () => {
  // Get current tab
  [currentTab] = await chrome.tabs.query({ active: true, currentWindow: true });
  
  // Load user state
  const stored = await chrome.storage.local.get(['tier', 'lookupsToday', 'lastReset']);
  userTier = stored.tier || 'free';
  lookupsToday = stored.lookupsToday || 0;
  
  // Reset daily counter if new day
  const today = new Date().toDateString();
  if (stored.lastReset !== today) {
    lookupsToday = 0;
    await chrome.storage.local.set({ lookupsToday: 0, lastReset: today });
  }
  
  updateUI();
  
  // Auto-detect if on TikTok Shop
  if (currentTab?.url?.includes('tiktok.com')) {
    autoDetect();
  }
  
  // Enter key to search
  document.getElementById('searchInput').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') searchProducts();
  });
});

function updateUI() {
  // Tier badge
  const badge = document.getElementById('tierBadge');
  badge.textContent = userTier.toUpperCase();
  badge.className = `badge tier-${userTier}`;
  
  // Lookup count
  if (userTier === 'free') {
    const remaining = Math.max(0, FREE_LIMIT - lookupsToday);
    document.getElementById('lookupCount').textContent = `${remaining} lookups left today`;
    
    if (remaining === 0) {
      document.getElementById('upgradeBanner').classList.add('visible');
      document.getElementById('searchBtn').disabled = true;
    }
  } else {
    document.getElementById('lookupCount').textContent = `${userTier.toUpperCase()} — Unlimited`;
  }
}

async function autoDetect() {
  if (!currentTab) return;
  
  // Inject content script to extract product info from current page
  try {
    const [result] = await chrome.scripting.executeScript({
      target: { tabId: currentTab.id },
      func: extractPageProduct,
    });
    
    if (result?.result) {
      const product = result.result;
      document.getElementById('currentTitle').textContent = product.title || 'Unknown Product';
      document.getElementById('currentPrice').textContent = product.price ? `$${product.price}` : '—';
      document.getElementById('currentProduct').classList.add('visible');
      
      // Auto-search with detected product
      document.getElementById('searchInput').value = product.title;
      searchProducts();
    }
  } catch (err) {
    console.log('Auto-detect failed:', err);
  }
}

// This function runs in the context of the web page
function extractPageProduct() {
  const url = window.location.href;
  let title = '';
  let price = null;
  let productId = null;
  
  // TikTok Shop product page
  if (url.includes('/shop/product/')) {
    const match = url.match(/\/shop\/product\/(\d+)/);
    if (match) productId = match[1];
    
    // Try to extract from page
    const titleEl = document.querySelector('h1') || document.querySelector('[class*="title"]');
    if (titleEl) title = titleEl.textContent.trim();
    
    // Price from meta or structured data
    const priceEl = document.querySelector('[class*="price"]');
    if (priceEl) {
      const priceText = priceEl.textContent.replace(/[^0-9.]/g, '');
      price = parseFloat(priceText) || null;
    }
  }
  
  // Amazon product page
  if (url.includes('amazon.com')) {
    const titleEl = document.getElementById('productTitle');
    if (titleEl) title = titleEl.textContent.trim();
    
    const priceEl = document.querySelector('.a-price-whole') || document.querySelector('#priceblock_ourprice');
    if (priceEl) {
      price = parseFloat(priceEl.textContent.replace(/[^0-9.]/g, '')) || null;
    }
  }
  
  return { title, price, productId, url };
}

async function searchProducts() {
  const query = document.getElementById('searchInput').value.trim();
  if (!query) return;
  
  // Check limits
  if (userTier === 'free' && lookupsToday >= FREE_LIMIT) {
    document.getElementById('upgradeBanner').classList.add('visible');
    return;
  }
  
  // Show loading
  document.getElementById('loading').classList.add('visible');
  document.getElementById('results').innerHTML = '';
  
  try {
    const resp = await fetch(`${API_BASE}/api/search?q=${encodeURIComponent(query)}&platform=all&limit=10`);
    const data = await resp.json();
    
    // Increment lookup counter
    lookupsToday++;
    await chrome.storage.local.set({ lookupsToday });
    updateUI();
    
    renderResults(data);
  } catch (err) {
    document.getElementById('results').innerHTML = `
      <div class="empty-state">
        <div class="icon">⚠️</div>
        <p>Search failed. Check your connection or try again later.</p>
        <p style="font-size:11px;color:#52525b;margin-top:8px;">${err.message}</p>
      </div>
    `;
  } finally {
    document.getElementById('loading').classList.remove('visible');
  }
}

function renderResults(data) {
  const container = document.getElementById('results');
  
  if (!data.results || data.results.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="icon">📭</div>
        <p>No results found for "${data.query}"</p>
        <p style="font-size:11px;color:#52525b;margin-top:8px;">Try different keywords or check spelling</p>
      </div>
    `;
    return;
  }
  
  let html = `<div class="section-title">${data.results.length} results for "${data.query}"</div>`;
  
  for (const product of data.results) {
    const platform = product.platform || 'amazon';
    const originalPrice = product.original_price || product.compare_at_price;
    const sold = product.units_sold;
    const rating = product.rating;
    
    html += `
      <div class="result-card">
        <div class="platform ${platform}">
          ${getPlatformIcon(platform)} ${platform}
        </div>
        <div class="product-title">${escapeHtml(product.title)}</div>
        <div class="product-meta">
          <div>
            <span class="price">$${product.price?.toFixed(2) || '—'}</span>
            ${originalPrice ? `<span class="original-price">$${originalPrice.toFixed(2)}</span>` : ''}
          </div>
          <div style="display:flex;gap:10px;align-items:center;">
            ${rating ? `<span class="rating">★ ${rating.toFixed(1)}</span>` : ''}
            ${sold ? `<span class="sold">${sold.toLocaleString()} sold</span>` : ''}
          </div>
        </div>
      </div>
    `;
  }
  
  // TikTok note
  if (data.tiktok_note) {
    html += `<div style="font-size:11px;color:#52525b;padding:8px;background:#12121a;border-radius:6px;margin-top:8px;">${data.tiktok_note}</div>`;
  }
  
  container.innerHTML = html;
}

function getPlatformIcon(platform) {
  const icons = { amazon: '📦', shopify: '🛍️', tiktok: '🎵' };
  return icons[platform] || '🔗';
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}
