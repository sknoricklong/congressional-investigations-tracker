// Export feedback records for triage, gated by the admin secret. Used by the
// daily workflow's queue snapshot and by manual review.
const { redisCommand } = require('./feedback-redis.js');

const FEEDBACK_KEY = 'congressional_investigations_feedback';
const MAX_EXPORT_LIMIT = 500;

module.exports = async function handler(req, res) {
  if (req.method !== 'GET') {
    res.setHeader('Allow', 'GET');
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

  const limit = boundedLimit(req.query.limit);
  const status = typeof req.query.status === 'string' ? req.query.status : '';
  const format = typeof req.query.format === 'string' ? req.query.format.toLowerCase() : 'json';

  try {
    const response = await redisCommand(redisUrl, redisToken, 'lrange', FEEDBACK_KEY, '0', String(limit - 1));
    const records = (response.result || [])
      .map(parseRecord)
      .filter(Boolean)
      .filter((record) => !status || record.status === status);

    if (format === 'markdown' || format === 'md') {
      res.setHeader('Content-Type', 'text/markdown; charset=utf-8');
      res.status(200).send(toMarkdown(records));
      return;
    }

    res.status(200).json({
      ok: true,
      count: records.length,
      records,
    });
  } catch (err) {
    res.status(502).json({ error: err.message || 'could not export feedback' });
  }
};

function boundedLimit(value) {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed) || parsed < 1) return 100;
  return Math.min(parsed, MAX_EXPORT_LIMIT);
}

function parseRecord(value) {
  try {
    const parsed = JSON.parse(value);
    return parsed && typeof parsed === 'object' ? parsed : null;
  } catch {
    return null;
  }
}

function toMarkdown(records) {
  const lines = ['# Congressional investigations feedback', ''];
  if (!records.length) {
    lines.push('No feedback records found.');
    return `${lines.join('\n')}\n`;
  }

  records.forEach((record) => {
    const context = record.context || {};
    const item = context.item || {};
    const target = context.target || {};
    const filters = context.filters || {};

    lines.push(`## ${safe(record.id)} - ${safe(item.title || target.region || 'Feedback')}`);
    lines.push('');
    lines.push(`- Status: ${safe(record.status || 'new')}`);
    lines.push(`- Created: ${safe(record.created_at || '')}`);
    lines.push(`- Page: ${safe(context.page_url || '')}`);
    lines.push(`- Item: ${safe(item.title || '')}`);
    lines.push(`- Item URL: ${safe(item.url || '')}`);
    lines.push(`- Committee: ${safe(item.committee || '')}`);
    lines.push(`- Chamber: ${safe(item.chamber || '')} / ${safe(item.party_lane || '')}`);
    lines.push(`- Type: ${safe(item.item_type || '')}`);
    lines.push(`- Published: ${safe(item.published_at || '')}`);
    lines.push(`- Target: ${safe(target.region || '')}${target.column ? ` / ${safe(target.column)}` : ''}`);
    lines.push(`- Target text: ${safe(target.text || '')}`);
    lines.push(`- Filters: ${safe(JSON.stringify(filters))}`);
    lines.push('');
    lines.push('### Reviewer note');
    lines.push('');
    lines.push(safe(record.note || ''));
    lines.push('');
  });

  return `${lines.join('\n')}\n`;
}

function safe(value) {
  return String(value || '').replace(/[<>]/g, '').trim();
}
