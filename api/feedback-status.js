// Update the status of one feedback record in the review queue.
//
// Used by triage (manual or automated) to close the loop after a feedback
// item has been handled. Gated by the same admin secret as
// /api/feedback-export.
const { redisCommand } = require('./feedback-redis.js');

const FEEDBACK_KEY = 'congressional_investigations_feedback';
const ALLOWED_STATUS = new Set(['new', 'processed', 'dismissed']);
const MAX_SCAN = 1000;

module.exports = async function handler(req, res) {
  if (req.method !== 'POST') {
    res.setHeader('Allow', 'POST');
    res.status(405).json({ error: 'method not allowed' });
    return;
  }

  const secret = process.env.FEEDBACK_ADMIN_SECRET;
  if (!secret || req.query.key !== secret) {
    res.status(401).json({ error: 'unauthorized' });
    return;
  }

  const redisUrl = process.env.UPSTASH_REDIS_REST_URL;
  const redisToken = process.env.UPSTASH_REDIS_REST_TOKEN;
  if (!redisUrl || !redisToken) {
    res.status(500).json({ error: 'feedback storage not configured' });
    return;
  }

  let body;
  try {
    body = typeof req.body === 'string' ? JSON.parse(req.body || '{}') : req.body || {};
  } catch {
    res.status(400).json({ error: 'invalid JSON payload' });
    return;
  }

  const id = typeof body.id === 'string' ? body.id.trim() : '';
  const status = typeof body.status === 'string' ? body.status.trim() : '';
  const resolution = typeof body.resolution === 'string' ? body.resolution.slice(0, 500) : '';
  if (!id || !ALLOWED_STATUS.has(status)) {
    res.status(400).json({ error: 'body must include id and status (new|processed|dismissed)' });
    return;
  }

  try {
    const response = await redisCommand(redisUrl, redisToken, 'lrange', FEEDBACK_KEY, '0', String(MAX_SCAN - 1));
    const rows = response.result || [];
    for (let index = 0; index < rows.length; index += 1) {
      let record;
      try {
        record = JSON.parse(rows[index]);
      } catch {
        continue;
      }
      if (record && record.id === id) {
        record.status = status;
        record.status_updated_at = new Date().toISOString();
        if (resolution) record.resolution = resolution;
        // LSET rewrites the record in place; the queue keeps its order, so
        // export output stays stable for anything still unprocessed.
        await redisCommand(redisUrl, redisToken, 'lset', FEEDBACK_KEY, String(index), JSON.stringify(record));
        res.status(200).json({ ok: true, id, status });
        return;
      }
    }
    res.status(404).json({ error: `no feedback record with id ${id}` });
  } catch (err) {
    res.status(502).json({ error: err.message || 'could not update feedback status' });
  }
};
