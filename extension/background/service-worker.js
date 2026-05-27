/**
 * SolTicker Chrome Extension — Service Worker (Background)
 * Handles auth state, rate limiting, and cross-tab communication.
 */

// API base URL
const API_BASE = 'https://solticker.app';
// const API_BASE = 'http://localhost:8000'; // Dev

// Auth state
let authToken = null;

// Initialize
chrome.runtime.onInstalled.addListener(() => {
  console.log('SolTicker extension installed');
  
  // Set default state
  chrome.storage.local.set({
    tier: 'free',
    lookupsToday: 0,
    lastReset: new Date().toDateString(),
  });
});

// Listen for messages from popup or content scripts
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'AUTH_TOKEN') {
    authToken = message.token;
    chrome.storage.local.set({ authToken });
    sendResponse({ ok: true });
  }
  
  if (message.type === 'GET_AUTH') {
    sendResponse({ token: authToken });
  }
  
  if (message.type === 'API_REQUEST') {
    handleApiRequest(message).then(sendResponse).catch(e => sendResponse({ error: e.message }));
    return true; // Async response
  }
});

async function handleApiRequest(message) {
  const { endpoint, method = 'GET', body } = message;
  
  const headers = { 'Content-Type': 'application/json' };
  if (authToken) headers['Authorization'] = `Bearer ${authToken}`;
  
  const resp = await fetch(`${API_BASE}${endpoint}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
  
  return await resp.json();
}

// Daily reset alarm
chrome.alarms.create('dailyReset', { periodInMinutes: 60 });
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === 'dailyReset') {
    const today = new Date().toDateString();
    chrome.storage.local.get(['lastReset'], (data) => {
      if (data.lastReset !== today) {
        chrome.storage.local.set({ lookupsToday: 0, lastReset: today });
      }
    });
  }
});

// Check if current page is TikTok Shop and update icon
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status === 'complete' && tab.url?.includes('tiktok.com')) {
    // Could inject content script here for automatic price overlay
    console.log('TikTok page detected:', tab.url);
  }
});
