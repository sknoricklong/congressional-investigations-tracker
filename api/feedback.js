// Right-click feedback channel, following the German AGM tracker's
// api/feedback.js. Records land in the shared tracker Redis (one Upstash
// store for all house trackers) under this tracker's own list key, so
// feedback routes only to this repo.
const crypto = require('node:crypto');
const { redisCommand } = require('./feedback-redis.js');

const FEEDBACK_KEY = 'congressional_investigations_feedback';
const MAX_BODY_BYTES = 25_000;
const MAX_FEEDBACK_PER_HOUR = 12;

module.exports = async function handler(req, res) {
  if (req.method !== 'POST') {
    res.setHeader('Allow', 'POST');
    res.status(405).json({ error: 'method not allowed' });
    return;
  }

  if (isOversizedRequest(req)) {
    res.status(413).json({ error: 'feedback payload is too large' });
    return;
  }

  const redisUrl = process.env.UPSTASH_REDIS_REST_URL;
  const redisToken = process.env.UPSTASH_REDIS_REST_TOKEN;
  if (!redisUrl || !redisToken) {
    res.status(500).json({
      error: 'feedback storage not configured',
      message: 'Feedback storage is not configured yet.',
    });
    return;
  }

  let body;
  try {
    body = parseBody(req.body);
  } catch {
    res.status(400).json({ error: 'invalid JSON payload' });
    return;
  }

  const validation = validateFeedback(body);
  if (!validation.ok) {
    res.status(400).json({ error: validation.error });
    return;
  }

  try {
    const rateLimit = await checkRateLimit(redisUrl, redisToken, clientKey(req));
    if (!rateLimit.allowed) {
      res.status(429).json({
        error: 'too many feedback submissions',
        message: 'Please wait before sending more feedback.',
      });
      return;
    }

    const createdAt = new Date();
    const record = {
      id: feedbackId(createdAt),
      created_at: createdAt.toISOString(),
      note: validation.value.note,
      context: {
        ...validation.value.context,
        user_agent: req.headers['user-agent'] || validation.value.context.user_agent || '',
      },
      status: 'new',
    };

    await redisCommand(redisUrl, redisToken, 'lpush', FEEDBACK_KEY, JSON.stringify(record));
    await redisCommand(redisUrl, redisToken, 'ltrim', FEEDBACK_KEY, '0', '999');

    res.status(200).json({
      ok: true,
      id: record.id,
      message: 'Feedback submitted for review.',
    });
  } catch (err) {
    res.status(502).json({ error: err.message || 'could not store feedback' });
  }
};

function isOversizedRequest(req) {
  const contentLength = Number(req.headers['content-length'] || 0);
  if (contentLength > MAX_BODY_BYTES) return true;
  if (typeof req.body === 'string' && Buffer.byteLength(req.body, 'utf8') > MAX_BODY_BYTES) {
    return true;
  }
  if (req.body && typeof req.body === 'object') {
    return Buffer.byteLength(JSON.stringify(req.body), 'utf8') > MAX_BODY_BYTES;
  }
  return false;
}

function parseBody(body) {
  if (typeof body === 'string') return JSON.parse(body || '{}');
  if (body && typeof body === 'object') return body;
  return {};
}

function validateFeedback(body) {
  const note = sanitizeText(body.note, 2_000);
  if (!note) return { ok: false, error: 'Add a note before submitting.' };

  return {
    ok: true,
    value: {
      note,
      context: sanitizeContext(body.context),
    },
  };
}

function sanitizeText(value, maxLength) {
  if (typeof value !== 'string') return '';
  return value
    .replace(/<[^>]*>/g, ' ')
    .replace(/[<>]/g, '')
    .replace(/[\u0000-\u001F\u007F]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, maxLength);
}

function sanitizeContext(context) {
  const input = context && typeof context === 'object' ? context : {};
  const filters = input.filters && typeof input.filters === 'object' ? input.filters : {};
  const item = input.item && typeof input.item === 'object' ? input.item : {};
  // Right-click feedback points at an arbitrary spot on the page instead of
  // (or in addition to) a table row.
  const target = input.target && typeof input.target === 'object' ? input.target : {};

  return {
    page_url: sanitizeText(input.page_url, 500),
    page_time: sanitizeText(input.page_time, 80),
    target: {
      region: sanitizeText(target.region, 120),
      column: sanitizeText(target.column, 120),
      text: sanitizeText(target.text, 300),
    },
    filters: {
      search: sanitizeText(filters.search, 300),
      date_range: sanitizeText(filters.date_range, 40),
      recent_only: sanitizeText(filters.recent_only, 10),
      chambers: sanitizeText(filters.chambers, 200),
      party_lanes: sanitizeText(filters.party_lanes, 200),
      item_types: sanitizeText(filters.item_types, 300),
      committees: sanitizeText(filters.committees, 1_000),
    },
    item: {
      id: sanitizeText(item.id, 200),
      title: sanitizeText(item.title, 500),
      url: sanitizeText(item.url, 500),
      committee: sanitizeText(item.committee, 200),
      chamber: sanitizeText(item.chamber, 40),
      party_lane: sanitizeText(item.party_lane, 40),
      item_type: sanitizeText(item.item_type, 80),
      source: sanitizeText(item.source, 200),
      published_at: sanitizeText(item.published_at, 80),
    },
    user_agent: sanitizeText(input.user_agent, 500),
  };
}

async function checkRateLimit(redisUrl, redisToken, key) {
  const rateKey = `congressional_feedback_rate:${key}`;
  const countResponse = await redisCommand(redisUrl, redisToken, 'incr', rateKey);
  const count = Number(countResponse.result || 0);
  if (count === 1) {
    await redisCommand(redisUrl, redisToken, 'expire', rateKey, '3600');
  }
  return { allowed: count <= MAX_FEEDBACK_PER_HOUR };
}

function clientKey(req) {
  const forwarded = String(req.headers['x-forwarded-for'] || '').split(',')[0].trim();
  const ip = forwarded || req.socket?.remoteAddress || 'unknown';
  return crypto.createHash('sha256').update(ip).digest('hex').slice(0, 24);
}

function feedbackId(date) {
  const day = date.toISOString().slice(0, 10).replace(/-/g, '');
  return `congress_fb_${day}_${crypto.randomUUID().slice(0, 8)}`;
}
