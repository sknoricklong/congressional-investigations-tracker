async function redisCommand(redisUrl, redisToken, command, ...args) {
  const path = [command, ...args].map((part) => encodeURIComponent(String(part))).join('/');
  const response = await fetch(`${redisUrl}/${path}`, {
    headers: { Authorization: `Bearer ${redisToken}` },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || payload.error) {
    throw new Error(payload.error || `Redis ${command} failed with status ${response.status}`);
  }
  return payload;
}

module.exports = { redisCommand };
