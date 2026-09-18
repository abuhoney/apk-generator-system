/**
 * render-backend/src/server.js — Express backend for APK build triggers.
 *
 * This is an alternative Node.js backend (from the bardom-platform pattern).
 * The primary backend is Python Flask (backend/app.py).
 * This Node.js server can be deployed as a separate Render service if needed.
 *
 * Endpoints:
 *   GET  /health           — Health check
 *   POST /api/build        — Trigger a build via GitHub Actions
 *   GET  /api/build/:id    — Get build status from Firebase
 *   POST /webhook/github   — Receive GitHub Actions progress
 *   POST /api/telegram/send — Send a Telegram message
 */

const express = require('express');
const cors = require('cors');
const crypto = require('crypto');

const ENV = process.env;
const PORT = ENV.PORT || 3000;
const FIREBASE_DB = ENV.FIREBASE_DATABASE_URL;
const GITHUB_TOKEN = ENV.GITHUB_TOKEN;
const GITHUB_REPO = ENV.GITHUB_REPO || 'abuhoney/apk-generator-system';
const TG_BOT_TOKEN = ENV.BOT_TOKEN;
const TG_ADMIN_CHAT_ID = ENV.TELEGRAM_ADMIN_CHAT_ID;
const BACKEND_SECRET = ENV.BACKEND_SECRET || 'bardom-v17-secret';

const app = express();
app.use(cors());
app.use(express.json({ limit: '10mb' }));

// ==================== Firebase REST helpers ==================== //
async function fbGet(path) {
  const res = await fetch(`${FIREBASE_DB}${path}.json`);
  if (!res.ok) throw new Error(`FB GET ${path} HTTP ${res.status}`);
  return res.json();
}
async function fbPut(path, body) {
  const res = await fetch(`${FIREBASE_DB}${path}.json`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: typeof body === 'string' ? body : JSON.stringify(body)
  });
  if (!res.ok) throw new Error(`FB PUT ${path} HTTP ${res.status}`);
  return res.json();
}
async function fbPatch(path, body) {
  const res = await fetch(`${FIREBASE_DB}${path}.json`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: typeof body === 'string' ? body : JSON.stringify(body)
  });
  if (!res.ok) throw new Error(`FB PATCH ${path} HTTP ${res.status}`);
  return res.json();
}

// ==================== Telegram helpers ==================== //
async function tgSend(chatId, text) {
  if (!TG_BOT_TOKEN) return;
  await fetch(`https://api.telegram.org/bot${TG_BOT_TOKEN}/sendMessage`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ chat_id: chatId, text, parse_mode: 'HTML', disable_web_page_preview: true })
  });
}

// ==================== GitHub Actions trigger ==================== //
async function triggerGitHubBuild(buildId, userId, appJson) {
  try {
    const url = `https://api.github.com/repos/${GITHUB_REPO}/dispatches`;
    const payload = {
      event_type: 'bardom_build',
      client_payload: {
        build_id: buildId,
        user_id: userId,
        app_json: appJson,
        timestamp: Date.now()
      }
    };

    const res = await fetch(url, {
      method: 'POST',
      headers: {
        'Authorization': `token ${GITHUB_TOKEN}`,
        'Accept': 'application/vnd.github+json',
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(payload)
    });

    if (!res.ok) {
      const text = await res.text();
      throw new Error(`GitHub HTTP ${res.status}: ${text}`);
    }

    await fbPatch(`/build_queue/${buildId}`, {
      status: 'building',
      progress: 5,
      stage: 'GitHub Actions build started',
      updated_at: Date.now()
    });

    return true;
  } catch (e) {
    console.error('[trigger]', e.message);
    await fbPatch(`/build_queue/${buildId}`, {
      status: 'failed',
      error: e.message,
      updated_at: Date.now()
    });
    return false;
  }
}

// ==================== Endpoints ==================== //

app.get('/health', (req, res) => {
  res.json({
    status: 'ok',
    version: '6.0.0',
    backend: 'render-backend (Node.js)',
    timestamp: new Date().toISOString()
  });
});

app.post('/api/build', async (req, res) => {
  const { function: fnName, user_id, app_json } = req.body;
  if (!fnName) return res.status(400).json({ error: 'function required' });

  const buildId = `bld-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  await fbPut(`/build_queue/${buildId}`, {
    function: fnName,
    user_id: user_id || 'anonymous',
    status: 'queued',
    progress: 0,
    created_at: Date.now()
  });

  await triggerGitHubBuild(buildId, user_id || 'anonymous', app_json || fnName);

  res.json({ ok: true, build_id: buildId, status: 'building' });
});

app.get('/api/build/:id', async (req, res) => {
  const build = await fbGet(`/build_queue/${req.params.id}`);
  if (!build) return res.status(404).json({ error: 'build not found' });
  res.json(build);
});

app.post('/webhook/github', async (req, res) => {
  const { build_id, status, progress, stage, apk_url } = req.body;
  if (!build_id) return res.status(400).json({ error: 'build_id required' });

  const update = { updated_at: Date.now() };
  if (status) update.status = status;
  if (progress !== undefined) update.progress = progress;
  if (stage) update.stage = stage;
  if (apk_url) update.apk_url = apk_url;

  await fbPatch(`/build_queue/${build_id}`, update);

  if (status === 'completed' && TG_ADMIN_CHAT_ID) {
    await tgSend(TG_ADMIN_CHAT_ID, `✅ Build <b>${build_id}</b> completed!\n${apk_url || ''}`);
  }

  res.json({ ok: true });
});

app.post('/api/telegram/send', async (req, res) => {
  const { chat_id, text } = req.body;
  if (!chat_id || !text) return res.status(400).json({ error: 'chat_id and text required' });
  await tgSend(chat_id, text);
  res.json({ ok: true });
});

app.listen(PORT, '0.0.0.0', () => {
  console.log(`BardomPro render-backend listening on port ${PORT}`);
});
