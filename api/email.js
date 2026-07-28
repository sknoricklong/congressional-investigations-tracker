// Weekly email for the Congressional Investigations Monitor.
//
// Mechanics follow the German AGM tracker (api/cron.js there) and the CNMV
// tracker: the send gate trusts only `Authorization: Bearer $CRON_SECRET`,
// `?dryRun=1` returns the gate decision and item selection without sending,
// scheduled sends use one Resend idempotency key per issue week, a Resend 409
// is a suppressed duplicate rather than an error, every run logs one
// structured `cron-run` line, and responses are no-store.
//
// Data source: the feed.json bundled into this deployment. The daily capture
// workflow commits data and site files to master and the git-connected Vercel
// project redeploys on push, so this function always reads the same data the
// page serves. No live committee-page request happens at send time.
//
// Selection: items whose first_seen_at falls inside a rolling window before
// the send. Committee pages stamp publication dates (often date-only), and a
// release can enter the tracker days after its publication date, so windowing
// on publication date would silently drop late-discovered items. first_seen_at
// is written once at first capture and never rewritten.
const feed = require("../site/feed.json");
const { resolveRecipients } = require("./recipients.js").helpers;

const APP_URL = "https://your-deployment.vercel.app/";
const DEFAULT_TEST_EMAIL_TO = "owner@example.com";

// The cron fires Monday 13:00 UTC. 168h would be exact; the extra 2h absorbs
// scheduler jitter and the race with Monday morning's capture deploy. A rare
// duplicate mention across two issues is acceptable; a silently missed item
// is not.
const DEFAULT_WINDOW_HOURS = 170;
const MAX_WINDOW_HOURS = 24 * 31;

const ET = "America/New_York";

// sv-SE gives zero-padded ISO output; year must stay numeric (a 2-digit year
// sorts before every 4-digit date and silently empties the selection).
function etDateIso(date) {
  return new Intl.DateTimeFormat("sv-SE", {
    timeZone: ET,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(date);
}

function shortDate(value) {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "";
  return new Intl.DateTimeFormat("en-US", {
    timeZone: "UTC",
    month: "short",
    day: "numeric",
  }).format(d);
}

function normalizeItem(raw) {
  const meta = raw._congress_monitor || {};
  return {
    id: raw.id,
    title: raw.title,
    url: raw.url,
    published_at: raw.date_published || null,
    committee: (raw.tags && raw.tags[0]) || "",
    chamber: (raw.tags && raw.tags[1]) || "",
    item_type: (raw.tags && raw.tags[2]) || "",
    party_lane: meta.party_lane || "",
    source_name: meta.source_name || "",
    first_seen_at: meta.first_seen_at || null,
    // Only source-scraped summaries reach the email; generated fallbacks
    // restate the title. The flag must be explicitly false — a feed.json
    // rendered before the flag existed includes no summaries at all rather
    // than leaking fallback text.
    summary: meta.summary_generated === false ? raw.summary || "" : "",
  };
}

// Same truncation the page applies, so page and email show identical text.
function summaryExcerpt(item) {
  const text = String(item.summary || "").trim();
  if (!text) return "";
  return text.length > 200 ? `${text.slice(0, 200)}...` : text;
}

function itemsSince(items, windowHours, now) {
  const cutoff = new Date(now.getTime() - windowHours * 3600 * 1000).toISOString();
  return items
    .filter((item) => item.first_seen_at && item.first_seen_at > cutoff)
    .sort(
      (a, b) =>
        String(b.published_at || b.first_seen_at).localeCompare(
          String(a.published_at || a.first_seen_at),
        ) || String(a.committee).localeCompare(String(b.committee)),
    );
}

function resolveWindowHours(raw) {
  const parsed = Number.parseInt(String(raw ?? ""), 10);
  if (!Number.isFinite(parsed)) return { hours: DEFAULT_WINDOW_HOURS, explicit: false };
  return { hours: Math.min(MAX_WINDOW_HOURS, Math.max(1, parsed)), explicit: true };
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function typeLabel(item) {
  return String(item.item_type || "").replace(/_/g, " ");
}

// The send date renders in the stakeholder's wall clock (ET), never UTC: a
// Monday-evening UTC rollover must not label the email with Tuesday's date.
// Items are selected by first capture, not publication, so the label names
// the send date rather than implying a publication-date range.
function sendDateLabel(now) {
  return new Intl.DateTimeFormat("en-US", {
    timeZone: ET,
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(now);
}

function buildEmailSubject(items, windowHours, now) {
  const sent = sendDateLabel(now);
  if (!items.length) return `Congressional investigations tracker: no new items (${sent})`;
  const noun = items.length === 1 ? "new item" : "new items";
  return `Congressional investigations tracker: ${items.length} ${noun} (${sent})`;
}

// The same release can reach the tracker from two committee pages (a press
// release and its letters-page copy). The email shows one entry per release:
// identical normalized title + publication date collapse, press release
// preferred. Exact-match only; near-duplicate grouping stays a human call.
function dedupeSameRelease(items) {
  const keyOf = (item) =>
    String(item.title).toLowerCase().replace(/[^a-z0-9]+/g, " ").trim() +
    "|" +
    String(item.published_at || "").slice(0, 10);
  const rank = (item) => {
    const i = ["press_release", "statement", "letter", "document"].indexOf(item.item_type);
    return i === -1 ? 99 : i;
  };
  const chosen = new Map();
  for (const item of items) {
    const key = keyOf(item);
    const prev = chosen.get(key);
    if (!prev || rank(item) < rank(prev)) chosen.set(key, item);
  }
  return items.filter((item) => chosen.get(keyOf(item)) === item);
}

function groupByChamberCommittee(items) {
  const chambers = { House: new Map(), Senate: new Map() };
  for (const item of items) {
    const bucket = chambers[item.chamber] || (chambers[item.chamber] = new Map());
    if (!bucket.has(item.committee)) bucket.set(item.committee, []);
    bucket.get(item.committee).push(item);
  }
  return chambers;
}

function buildEmailText(items, windowHours, now) {
  const lines = [
    `New congressional committee activity since the previous weekly email (${sendDateLabel(now)})`,
    "",
    `Tracker: ${APP_URL}`,
    "",
  ];

  const grouped = groupByChamberCommittee(items);
  for (const chamber of ["House", "Senate"]) {
    const committees = grouped[chamber] || new Map();
    lines.push(`${chamber}`);
    if (!committees.size) {
      lines.push(`No new ${chamber} committee items this week.`);
      lines.push("");
      continue;
    }
    for (const committee of [...committees.keys()].sort()) {
      lines.push("");
      lines.push(committee);
      for (const item of committees.get(committee)) {
        const date = item.published_at ? shortDate(item.published_at) : "no date";
        lines.push(`- ${date}: ${item.title} (${item.party_lane}, ${typeLabel(item)})`);
        const excerpt = summaryExcerpt(item);
        if (excerpt) lines.push(`  ${excerpt}`);
        lines.push(`  ${item.url}`);
      }
    }
    lines.push("");
  }

  lines.push("---");
  lines.push(
    `Sources checked daily: ${feed.items ? sourceCount() : 0} committee pages. ` +
      `This email covers items first captured in the ${windowHours}-hour window before send time.`,
  );
  lines.push("Reply to this email with feedback, or right-click any item on the tracker page to flag it.");
  return lines.join("\n");
}

function sourceCount() {
  return new Set(feed.items.map((raw) => (raw._congress_monitor || {}).source_name)).size;
}

function buildEmailHtml(items, windowHours, now) {
  const grouped = groupByChamberCommittee(items);

  const sections = ["House", "Senate"]
    .map((chamber) => {
      const committees = grouped[chamber] || new Map();
      let body;
      if (!committees.size) {
        body = `<p style="margin:6px 0 18px;color:#5c5c56;">No new ${chamber} committee items this week.</p>`;
      } else {
        body = [...committees.keys()]
          .sort()
          .map((committee) => {
            const rows = committees
              .get(committee)
              .map((item) => {
                const date = item.published_at ? shortDate(item.published_at) : "no date";
                const excerpt = summaryExcerpt(item);
                return `<p style="margin:0 0 9px;">
                  <a href="${escapeHtml(`${APP_URL}?q=${item.id}`)}" style="color:#9a958a;text-decoration:none;">${escapeHtml(date)}</a>
                  &nbsp;·&nbsp;
                  <a href="${escapeHtml(item.url)}" style="color:#174d78;">${escapeHtml(item.title)}</a>
                  <span style="color:#5c5c56;font-size:13px;">(${escapeHtml(item.party_lane)}, ${escapeHtml(typeLabel(item))})</span>
                  ${excerpt ? `<br><span style="color:#5c5c56;font-size:13px;">${escapeHtml(excerpt)}</span>` : ""}
                </p>`;
              })
              .join("");
            return `<p style="margin:14px 0 8px;font-weight:bold;">${escapeHtml(committee)}</p>${rows}`;
          })
          .join("");
      }
      return `<h2 style="font-size:16px;border-bottom:1px solid #CCCBBE;padding-bottom:4px;margin:22px 0 6px;">${chamber}</h2>${body}`;
    })
    .join("");

  return `<!doctype html>
<html>
  <body style="font-family:Georgia,'Times New Roman',serif;color:#151515;max-width:720px;">
    <h1 style="font-size:20px;font-weight:bold;margin:0 0 2px;">Congressional investigations tracker</h1>
    <p style="margin:0 0 14px;color:#5c5c56;">New since the previous weekly email · ${escapeHtml(sendDateLabel(now))} · <a href="${APP_URL}" style="color:#174d78;">Open the tracker</a></p>
    ${
      !items.length
        ? `<p>No new committee items were captured since the previous weekly email.</p>${sections}`
        : sections
    }
    <p style="margin:24px 0 0;padding-top:10px;border-top:1px solid #CCCBBE;color:#5c5c56;font-size:13px;">
      ${sourceCount()} committee pages are checked daily; this email covers everything first captured since the previous weekly email.
      Reply with feedback, or right-click any item on the <a href="${APP_URL}" style="color:#174d78;">tracker page</a> to flag it.
    </p>
  </body>
</html>`;
}

async function sendEmail(items, windowHours, now, options) {
  const { idempotencyKey, testSend, to } = options;
  const apiKey = process.env.RESEND_API_KEY;
  const from = process.env.CONGRESS_EMAIL_FROM;
  // Test sends go to the test inbox only. Production sends use the recipient
  // list the handler resolved (Resend audience, env fallback).
  const toList = testSend
    ? (process.env.CONGRESS_EMAIL_TEST_TO || DEFAULT_TEST_EMAIL_TO)
        .split(",")
        .map((value) => value.trim())
        .filter(Boolean)
    : to || [];

  if (!apiKey || !from || !toList.length) {
    const missing = [
      !apiKey && "RESEND_API_KEY",
      !from && "CONGRESS_EMAIL_FROM",
      !toList.length && "recipients (audience/CONGRESS_EMAIL_TO)",
    ]
      .filter(Boolean)
      .join(", ");
    // Throw so the handler returns 502 instead of a silent 200 with
    // sent:false. A missing-config no-op is how the CNMV non-send hid.
    throw new Error(`Email configuration missing: ${missing}`);
  }

  const payload = {
    from,
    to: toList,
    subject: `${testSend ? "[Test] " : ""}${buildEmailSubject(items, windowHours, now)}`,
    text: buildEmailText(items, windowHours, now),
    html: buildEmailHtml(items, windowHours, now),
  };

  const headers = {
    authorization: `Bearer ${apiKey}`,
    "content-type": "application/json",
  };
  // Test sends carry no idempotency key: repeats always send.
  if (idempotencyKey) headers["idempotency-key"] = idempotencyKey;

  const response = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
  });

  const body = await response.text();
  let parsed;
  try {
    parsed = JSON.parse(body);
  } catch (_error) {
    parsed = { raw: body };
  }

  if (response.status === 409) {
    // Same idempotency key already used: Resend already sent this email.
    // A suppressed duplicate is a success with a dedup flag, not an outage.
    return {
      attempted: true,
      sent: false,
      deduped: true,
      reason: `Resend idempotency key ${idempotencyKey} already used; duplicate send suppressed.`,
      to: toList,
      subject: payload.subject,
      provider: "resend",
      response: parsed,
    };
  }

  if (!response.ok) {
    throw new Error(`Resend returned ${response.status}: ${body}`);
  }

  return {
    attempted: true,
    sent: true,
    to: toList,
    subject: payload.subject,
    provider: "resend",
    response: parsed,
  };
}

function sendJson(res, payload, status) {
  res.status(status);
  // no-store: an edge-cached response could answer a verification request
  // without invoking the function, hiding whether a send happened.
  res.setHeader("Cache-Control", "no-store");
  res.json(payload);
}

module.exports = async function handler(req, res) {
  if (req.method !== "GET") {
    res.setHeader("Allow", "GET");
    sendJson(res, { ok: false, error: "Method not allowed." }, 405);
    return;
  }

  try {
    const now = new Date();
    const dateIso = etDateIso(now);

    // The send gate trusts ONLY the CRON_SECRET Authorization header. Vercel
    // sends `Authorization: Bearer <CRON_SECRET>` on scheduled cron requests
    // when the env var is set. Schedule headers and the User-Agent are
    // client-forgeable and stay diagnostics-only.
    const cronSecret = process.env.CRON_SECRET;
    const authHeader = req.headers["authorization"] || "";
    const authedCron = Boolean(cronSecret) && authHeader === `Bearer ${cronSecret}`;
    const cronTriggered = authedCron;
    const manualRequested = req.query.sendEmail === "1";
    const manualTrigger = manualRequested && (!cronSecret || authedCron);
    // `?testEmail=1&key=<CONGRESS_TEST_SECRET>` sends the exact weekly email
    // to the test inbox only, never to the production list.
    const testSecret = process.env.CONGRESS_TEST_SECRET;
    const testRequested = req.query.testEmail === "1";
    const testTrigger =
      testRequested && (authedCron || (Boolean(testSecret) && req.query.key === testSecret));
    const dryRun = req.query.dryRun === "1";
    const detect = {
      authedCron,
      hasScheduleHeader: Boolean(req.headers["x-vercel-cron-schedule"]),
      manualRequested,
      manualTrigger,
      testRequested,
      testTrigger,
      cronTriggered,
      dryRun,
    };

    // `?sinceHours=N` widens or narrows the window for manual catch-up sends;
    // scheduled runs always use the 170h default.
    const window = resolveWindowHours(req.query.sinceHours);
    const allItems = (feed.items || []).map(normalizeItem);
    const emailItems = dedupeSameRelease(itemsSince(allItems, window.hours, now));

    // Production recipients live in the Resend audience the recipients page
    // manages; CONGRESS_EMAIL_TO is the fallback when the audience is
    // missing, empty, or unreachable. Test sends never use this list.
    const fallbackTo = (process.env.CONGRESS_EMAIL_TO || "")
      .split(",")
      .map((value) => value.trim())
      .filter(Boolean);
    const recipients = testRequested
      ? { list: fallbackTo, source: "env", error: null }
      : await resolveRecipients(process.env.RESEND_API_KEY, fallbackTo);

    const emailPreview = {
      windowHours: window.hours,
      itemCount: emailItems.length,
      ids: emailItems.map((item) => item.id),
      recipientSource: recipients.source,
      recipientCount: recipients.list.length,
      recipientError: recipients.error,
      subject: buildEmailSubject(emailItems, window.hours, now),
    };
    const idempotencyKey = window.explicit
      ? `congressional-manual-${dateIso}-${window.hours}`
      : `congressional-weekly-${dateIso}`;

    let reason;
    if (dryRun) {
      reason = "Dry run: gate evaluated, no email sent.";
    } else if (testRequested && !testTrigger) {
      reason = "Test send rejected: missing or invalid test authorization.";
    } else if (manualRequested && !manualTrigger) {
      reason = "Manual trigger rejected: missing or invalid CRON_SECRET authorization.";
    } else {
      reason = "Email send skipped: not a Vercel cron request and no manual trigger.";
    }

    let email = {
      attempted: false,
      sent: false,
      reason,
      to: testRequested
        ? (process.env.CONGRESS_EMAIL_TEST_TO || DEFAULT_TEST_EMAIL_TO).split(",")
        : recipients.list,
    };

    // A test request never falls through to a production send, even when the
    // caller also carries valid cron credentials.
    if (!dryRun && testRequested) {
      if (testTrigger) {
        email = await sendEmail(emailItems, window.hours, now, { testSend: true });
      }
    } else if (!dryRun && (cronTriggered || manualTrigger)) {
      email = await sendEmail(emailItems, window.hours, now, {
        idempotencyKey,
        to: recipients.list,
      });
    }

    // One structured line per invocation so every scheduled run is
    // self-documenting: which signal matched, which items were selected, and
    // the send outcome. Header keys only, never values, so the Authorization
    // secret is not logged.
    console.log(
      "cron-run " +
        JSON.stringify({
          at: dateIso,
          userAgent: req.headers["user-agent"] || null,
          headerKeys: Object.keys(req.headers),
          detect,
          emailPreview,
          email: {
            attempted: email.attempted,
            sent: email.sent,
            deduped: email.deduped || false,
            reason: email.reason || null,
            to: email.to,
            subject: email.subject || null,
            resendId: email.response && email.response.id ? email.response.id : null,
          },
        }),
    );

    // Recipient addresses never leave the server: the recipients page is
    // password-gated, so an unauthenticated endpoint must not hand out the
    // same list. The structured log above keeps the full addresses.
    const { to: _redactedTo, ...emailPublic } = email;
    const responsePayload = {
      ok: true,
      date: dateIso,
      dataset: { itemsTotal: allItems.length },
      detect,
      emailPreview,
      email: {
        ...emailPublic,
        toCount: Array.isArray(email.to) ? email.to.filter(Boolean).length : 0,
      },
    };
    // `?includeHtml=1` returns the exact email body so the email preview page
    // shows the identical bytes the send path would use (one builder, no
    // drift between page and email).
    if (req.query.includeHtml === "1") {
      responsePayload.emailHtml = buildEmailHtml(emailItems, window.hours, now);
    }

    sendJson(res, responsePayload, 200);
  } catch (error) {
    console.error(
      "cron-error " +
        JSON.stringify({ message: error instanceof Error ? error.message : String(error) }),
    );
    sendJson(
      res,
      {
        ok: false,
        error: "Weekly email run failed.",
        detail: error instanceof Error ? error.message : String(error),
      },
      502,
    );
  }
};
