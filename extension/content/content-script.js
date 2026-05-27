/**
 * SolTicker Chrome Extension — Content Script
 * Injected into TikTok Shop pages to detect products and show price overlays.
 */

// Only run on TikTok Shop pages
if (window.location.href.includes('tiktok.com/shop/product/')) {
  initTiktokOverlay();
}

function initTiktokOverlay() {
  // Wait for page to fully load
  const observer = new MutationObserver((mutations, obs) => {
    // Look for product price elements
    const priceEl = document.querySelector('[class*="price"]');
    if (priceEl) {
      obs.disconnect();
      showPriceComparison(priceEl);
    }
  });
  
  observer.observe(document.body, { childList: true, subtree: true });
  
  // Timeout: stop observing after 10s
  setTimeout(() => observer.disconnect(), 10000);
}

function showPriceComparison(targetEl) {
  // Remove existing overlay
  const existing = document.getElementById('solticker-overlay');
  if (existing) existing.remove();
  
  // Create floating comparison badge
  const badge = document.createElement('div');
  badge.id = 'solticker-overlay';
  badge.innerHTML = `
    <div style="
      position: fixed;
      bottom: 20px;
      right: 20px;
      background: linear-gradient(135deg, #1a1a2e, #16213e);
      border: 1px solid #6366f1;
      border-radius: 12px;
      padding: 16px;
      z-index: 99999;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      color: #e4e4e7;
      box-shadow: 0 8px 32px rgba(0,0,0,0.4);
      min-width: 260px;
    ">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;">
        <span style="font-size:18px;">📊</span>
        <span style="font-weight:700;font-size:14px;">SolTicker</span>
        <span style="
          font-size:9px;
          padding:2px 6px;
          background:#6366f120;
          color:#6366f1;
          border-radius:4px;
          font-weight:600;
        ">FREE</span>
      </div>
      <div style="font-size:12px;color:#a1a1aa;margin-bottom:8px;">
        Click to search this product across Amazon & Shopify
      </div>
      <button id="solticker-search-btn" style="
        width:100%;
        padding:8px;
        background:linear-gradient(135deg,#6366f1,#8b5cf6);
        color:#fff;
        border:none;
        border-radius:6px;
        font-size:12px;
        font-weight:600;
        cursor:pointer;
      ">
        🔍 Compare Prices
      </button>
      <button id="solticker-close-btn" style="
        position:absolute;
        top:8px;
        right:8px;
        background:none;
        border:none;
        color:#52525b;
        font-size:16px;
        cursor:pointer;
        padding:4px;
      ">×</button>
    </div>
  `;
  
  document.body.appendChild(badge);
  
  // Close button
  document.getElementById('solticker-close-btn').addEventListener('click', () => {
    badge.remove();
  });
  
  // Search button — open popup
  document.getElementById('solticker-search-btn').addEventListener('click', async () => {
    const productTitle = document.querySelector('h1')?.textContent?.trim() || '';
    
    // Send message to background to open popup with query
    chrome.runtime.sendMessage({
      type: 'OPEN_POPUP',
      query: productTitle,
    });
  });
}

// Listen for messages from popup/background
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'GET_PRODUCT_INFO') {
    const title = document.querySelector('h1')?.textContent?.trim() || '';
    const priceText = document.querySelector('[class*="price"]')?.textContent || '';
    const price = parseFloat(priceText.replace(/[^0-9.]/g, '')) || null;
    sendResponse({ title, price });
  }
});
