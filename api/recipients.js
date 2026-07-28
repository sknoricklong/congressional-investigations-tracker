// Self-service recipient list for the weekly email, following the CNMV
// tracker's api/recipients.js. The list lives in a Resend audience looked up
// by name (no audience id stored anywhere), seeded from CONGRESS_EMAIL_TO on
// first use, with the env var kept as the send-time fallback so recipient
// resolution can never skip a send because the audience lookup broke.
const crypto = require("crypto");

const RESEND_API = "https://api.resend.com";
const AUDIENCE_NAME = "Congressional investigations tracker";
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
// The operator runs the pipeline and always receives the email; these
// addresses are not relevant on the stakeholder's management page, so they
// are never shown there and cannot be removed there. Send-time resolution
// still emails every contact.
const HIDDEN_RECIPIENTS = new Set([
  "owner@example.com",
]);

function visibleContacts(contacts) {
  return contacts.filter((contact) => !HIDDEN_RECIPIENTS.has(contact.email.toLowerCase()));
}

function timingSafeEqualStr(a, b) {
  const left = Buffer.from(String(a));
  const right = Buffer.from(String(b));
  if (left.length !== right.length) {
    // Self-compare keeps the timing profile flat for wrong-length guesses.
    crypto.timingSafeEqual(left, left);
    return false;
  }
  return crypto.timingSafeEqual(left, right);
}

async function resendRequest(apiKey, method, path, body) {
  const attempt = async () =>
    fetch(`${RESEND_API}${path}`, {
      method,
      headers: {
        authorization: `Bearer ${apiKey}`,
        "content-type": "application/json",
      },
      body: body ? JSON.stringify(body) : undefined,
    });

  let response = await attempt();
  if (response.status === 429) {
    // Resend rate limit; one retry covers the seed loop's burst.
    await new Promise((resolve) => setTimeout(resolve, 700));
    response = await attempt();
  }

  const text = await response.text();
  let parsed;
  try {
    parsed = JSON.parse(text);
  } catch (_error) {
    parsed = { raw: text };
  }
  if (!response.ok) {
    const detail = parsed && parsed.message ? parsed.message : text;
    const error = new Error(`Resend ${method} ${path} returned ${response.status}: ${detail}`);
    error.status = response.status;
    throw error;
  }
  return parsed;
}

function fallbackRecipients() {
  return (process.env.CONGRESS_EMAIL_TO || "")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
}

async function findAudienceId(apiKey) {
  const audiences = await resendRequest(apiKey, "GET", "/audiences");
  const match = (audiences.data || []).find((audience) => audience.name === AUDIENCE_NAME);
  return match ? match.id : null;
}

async function listContacts(apiKey, audienceId) {
  const contacts = await resendRequest(apiKey, "GET", `/audiences/${audienceId}/contacts`);
  return (contacts.data || []).filter((contact) => !contact.unsubscribed);
}

async function addContact(apiKey, audienceId, email) {
  try {
    await resendRequest(apiKey, "POST", `/audiences/${audienceId}/contacts`, {
      email,
      unsubscribed: false,
    });
  } catch (error) {
    // An email already in the audience makes "add" idempotent, not a failure.
    if (!/already|exist/i.test(error.message || "")) throw error;
  }
}

// Find the audience, creating and seeding it from CONGRESS_EMAIL_TO on first
// use so the page never starts from an empty list.
async function ensureAudience(apiKey) {
  const existingId = await findAudienceId(apiKey);
  if (existingId) return existingId;

  const created = await resendRequest(apiKey, "POST", "/audiences", { name: AUDIENCE_NAME });
  for (const email of fallbackRecipients()) {
    await addContact(apiKey, created.id, email.toLowerCase());
  }
  return created.id;
}

// Recipient list for the weekly send: the audience when it has members, the
// CONGRESS_EMAIL_TO env var otherwise. Never throws; the weekly email must go
// out even if the audience lookup breaks.
async function resolveRecipients(apiKey, fallbackList) {
  const fallback = { list: fallbackList, source: "env", error: null };
  if (!apiKey) return { ...fallback, error: "RESEND_API_KEY missing" };
  try {
    const audienceId = await findAudienceId(apiKey);
    if (!audienceId) return { ...fallback, error: `Audience "${AUDIENCE_NAME}" not found` };
    const contacts = await listContacts(apiKey, audienceId);
    if (!contacts.length) return { ...fallback, error: `Audience "${AUDIENCE_NAME}" is empty` };
    return { list: contacts.map((contact) => contact.email), source: "audience", error: null };
  } catch (error) {
    return { ...fallback, error: error instanceof Error ? error.message : String(error) };
  }
}

async function readJsonBody(req) {
  if (req.body !== undefined) {
    if (typeof req.body === "string") {
      try {
        return JSON.parse(req.body);
      } catch (_error) {
        return {};
      }
    }
    return req.body || {};
  }
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  if (!chunks.length) return {};
  try {
    return JSON.parse(Buffer.concat(chunks).toString("utf8"));
  } catch (_error) {
    return {};
  }
}

function sendJson(res, payload, status) {
  res.status(status);
  res.setHeader("Cache-Control", "no-store");
  res.json(payload);
}

function recipientsPayload(contacts) {
  return {
    ok: true,
    recipients: visibleContacts(contacts)
      .map((contact) => contact.email)
      .sort((a, b) => a.localeCompare(b)),
  };
}

module.exports = async function handler(req, res) {
  // POST only: the password travels in the body, never in a URL that could
  // land in access logs or browser history.
  if (req.method !== "POST") {
    sendJson(res, { ok: false, error: "Method not allowed." }, 405);
    return;
  }

  const password = process.env.CONGRESS_LIST_PASSWORD;
  const apiKey = process.env.RESEND_API_KEY;
  if (!password || !apiKey) {
    const missing = [!password && "CONGRESS_LIST_PASSWORD", !apiKey && "RESEND_API_KEY"]
      .filter(Boolean)
      .join(", ");
    sendJson(res, { ok: false, error: `Configuration incomplete: ${missing}.` }, 503);
    return;
  }

  try {
    const body = await readJsonBody(req);

    if (!body.password || !timingSafeEqualStr(body.password, password)) {
      // Flat delay to slow down password guessing.
      await new Promise((resolve) => setTimeout(resolve, 300));
      sendJson(res, { ok: false, error: "Incorrect password." }, 401);
      return;
    }

    const action = String(body.action || "list");
    const audienceId = await ensureAudience(apiKey);

    if (action === "list") {
      sendJson(res, recipientsPayload(await listContacts(apiKey, audienceId)), 200);
      return;
    }

    const email = String(body.email || "").trim().toLowerCase();

    if (action === "add") {
      if (!EMAIL_PATTERN.test(email)) {
        sendJson(res, { ok: false, error: "Enter a valid email address." }, 400);
        return;
      }
      await addContact(apiKey, audienceId, email);
      sendJson(res, recipientsPayload(await listContacts(apiKey, audienceId)), 200);
      return;
    }

    if (action === "remove") {
      const contacts = await listContacts(apiKey, audienceId);
      // Hidden recipients are invisible to this page, so they cannot be
      // matched or removed here.
      const removable = visibleContacts(contacts);
      const match = removable.find((contact) => contact.email.toLowerCase() === email);
      if (!match) {
        sendJson(res, { ok: false, error: "That email is not on the list." }, 404);
        return;
      }
      if (removable.length === 1) {
        sendJson(
          res,
          { ok: false, error: "The last recipient on the list cannot be removed." },
          400,
        );
        return;
      }
      await resendRequest(apiKey, "DELETE", `/audiences/${audienceId}/contacts/${match.id}`);
      sendJson(res, recipientsPayload(await listContacts(apiKey, audienceId)), 200);
      return;
    }

    sendJson(res, { ok: false, error: "Unrecognized action." }, 400);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    console.error("recipients-error " + JSON.stringify({ message }));
    // Reaching this catch requires a valid password (wrong passwords return
    // early above), so the Resend detail goes only to authorized callers.
    sendJson(
      res,
      { ok: false, error: "The list could not be updated. Try again.", detail: message },
      502,
    );
  }
};

// Shared with api/email.js (recipient resolution) and local harnesses.
module.exports.helpers = { resolveRecipients, findAudienceId, listContacts, AUDIENCE_NAME };
