// Contract smoke test for api/email.js, run in CI after the pipeline renders
// site/feed.json and before the commit step. Exercises the handler directly
// (no network, no secrets) and fails the workflow when the email contract
// breaks: gate behavior, no-store, window default, selection consistency,
// subject shape, section skeleton, and the no-fallback-summary rule.
const assert = require("node:assert");
const path = require("node:path");

const handler = require(path.join(__dirname, "..", "api", "email.js"));
const { runSmokeApiRoutes } = require("./smoke-api-routes.js");

function makeRes() {
  const res = { headers: {}, code: null, payload: null };
  res.status = (c) => {
    res.code = c;
    return res;
  };
  res.setHeader = (k, v) => {
    res.headers[k] = v;
  };
  res.json = (p) => {
    res.payload = p;
  };
  return res;
}

function run(query, method = "GET", headers = {}) {
  const res = makeRes();
  return handler(
    { method, headers: { "user-agent": "smoke-test", ...headers }, query: query || {} },
    res,
  ).then(() => res);
}

function fetchResponse(payload, status = 200) {
  const text = JSON.stringify(payload);
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => text,
  };
}

async function withEnv(values, fn) {
  const before = {};
  for (const [key, value] of Object.entries(values)) {
    before[key] = Object.prototype.hasOwnProperty.call(process.env, key)
      ? process.env[key]
      : undefined;
    if (value === undefined) delete process.env[key];
    else process.env[key] = value;
  }
  try {
    return await fn();
  } finally {
    for (const [key, value] of Object.entries(before)) {
      if (value === undefined) delete process.env[key];
      else process.env[key] = value;
    }
  }
}

(async () => {
  // Default dry run: gate evaluated, nothing sent, selection consistent.
  let res = await run({ dryRun: "1", includeHtml: "1" });
  assert.strictEqual(res.code, 200, "dryRun should return 200");
  assert.strictEqual(res.headers["Cache-Control"], "no-store", "responses must be no-store");
  const p = res.payload;
  assert.strictEqual(p.ok, true, "dryRun payload.ok");
  assert.strictEqual(p.email.attempted, false, "dryRun must not attempt a send");
  assert.strictEqual(p.emailPreview.windowHours, 170, "default window is 170h");
  assert.strictEqual(
    p.emailPreview.ids.length,
    p.emailPreview.itemCount,
    "itemCount must match ids",
  );
  assert.strictEqual(
    new Set(p.emailPreview.ids).size,
    p.emailPreview.ids.length,
    "selected ids must be unique",
  );
  assert.strictEqual(p.email.to, undefined, "recipient addresses must not appear in responses");
  assert.strictEqual(typeof p.email.toCount, "number", "responses carry a recipient count only");
  const subject = p.emailPreview.subject;
  if (p.emailPreview.itemCount === 0) {
    assert.ok(/no new items/.test(subject), `zero-item subject says so: ${subject}`);
  } else {
    assert.ok(
      new RegExp(`${p.emailPreview.itemCount} new item`).test(subject),
      `subject encodes the count: ${subject}`,
    );
  }
  assert.ok(/<h2[^>]*>House<\/h2>/.test(p.emailHtml), "House section always present");
  assert.ok(/<h2[^>]*>Senate<\/h2>/.test(p.emailHtml), "Senate section always present");
  // Generated fallback summaries restate the title and must never reach the
  // email. Their shape is "Committee (lane) ..." with no sentence text.
  assert.ok(
    !/\((?:majority|minority|committee)\) (?:letter|subpoena|statement|hearing notice|investigation|demand for answers)/.test(
      p.emailHtml,
    ),
    "generated fallback summaries must not appear in the email body",
  );

  // Manual sinceHours bounds.
  res = await run({ dryRun: "1", sinceHours: "999999" });
  assert.ok(res.payload.emailPreview.windowHours <= 744, "manual window is capped");

  // Test send without authorization must not attempt.
  res = await run({ testEmail: "1" });
  assert.strictEqual(res.payload.email.attempted, false, "unauthorized test send rejected");

  // Non-GET rejected.
  res = await run({}, "POST");
  assert.strictEqual(res.code, 405, "POST returns 405");
  assert.strictEqual(res.headers.Allow, "GET", "method error keeps Allow header");
  assert.strictEqual(res.headers["Cache-Control"], "no-store", "method error is no-store");
  assert.deepStrictEqual(res.payload, {
    ok: false,
    error: "Method not allowed.",
  });

  await withEnv(
    {
      CRON_SECRET: "smoke-cron-secret",
      CONGRESS_TEST_SECRET: "smoke-test-secret",
      RESEND_API_KEY: "smoke-resend-key",
      CONGRESS_EMAIL_FROM: "tracker@example.com",
      CONGRESS_EMAIL_TO: "fallback@example.com",
      CONGRESS_EMAIL_TEST_TO: "test-only@example.com",
    },
    async () => {
      const originalFetch = global.fetch;
      const requests = [];
      let emailStatus = 200;
      global.fetch = async (url, options = {}) => {
        requests.push({ url, options });
        if (url === "https://api.resend.com/audiences") {
          return fetchResponse({
            data: [
              {
                id: "audience-id",
                name: "Congressional investigations tracker",
              },
            ],
          });
        }
        if (url === "https://api.resend.com/audiences/audience-id/contacts") {
          return fetchResponse({
            data: [
              { id: "one", email: "one@example.com", unsubscribed: false },
              { id: "two", email: "two@example.com", unsubscribed: false },
            ],
          });
        }
        if (url === "https://api.resend.com/emails") {
          return fetchResponse(
            emailStatus === 409 ? { message: "duplicate" } : { id: "email-id" },
            emailStatus,
          );
        }
        throw new Error(`Unexpected mocked request: ${url}`);
      };
      try {
        let beforeCount = requests.length;
        let send = await run(
          { sendEmail: "1", sinceHours: "24" },
          "GET",
          { authorization: "Bearer smoke-cron-secret" },
        );
        assert.strictEqual(send.code, 200, "authorized manual send returns 200");
        assert.strictEqual(send.payload.email.attempted, true, "manual send attempted");
        assert.strictEqual(send.payload.email.sent, true, "manual send reports sent");
        assert.strictEqual(send.payload.email.to, undefined, "manual response stays redacted");
        assert.strictEqual(send.payload.email.toCount, 2, "manual response has recipient count");
        assert.strictEqual(send.payload.emailPreview.recipientSource, "audience");
        let emailRequest = requests
          .slice(beforeCount)
          .find((request) => request.url === "https://api.resend.com/emails");
        assert.ok(emailRequest, "manual send reaches mocked Resend email route");
        assert.match(
          emailRequest.options.headers["idempotency-key"],
          /^congressional-manual-\d{4}-\d{2}-\d{2}-24$/,
          "manual send has a window-specific idempotency key",
        );
        assert.deepStrictEqual(JSON.parse(emailRequest.options.body).to, [
          "one@example.com",
          "two@example.com",
        ]);

        emailStatus = 409;
        beforeCount = requests.length;
        send = await run(
          {},
          "GET",
          { authorization: "Bearer smoke-cron-secret" },
        );
        assert.strictEqual(send.code, 200, "duplicate cron send remains a success");
        assert.strictEqual(send.payload.email.attempted, true);
        assert.strictEqual(send.payload.email.sent, false);
        assert.strictEqual(send.payload.email.deduped, true);
        emailRequest = requests
          .slice(beforeCount)
          .find((request) => request.url === "https://api.resend.com/emails");
        assert.match(
          emailRequest.options.headers["idempotency-key"],
          /^congressional-weekly-\d{4}-\d{2}-\d{2}$/,
          "weekly send keeps its issue idempotency key",
        );

        emailStatus = 200;
        beforeCount = requests.length;
        send = await run({
          testEmail: "1",
          key: "smoke-test-secret",
        });
        assert.strictEqual(send.code, 200, "authorized test send returns 200");
        assert.strictEqual(send.payload.email.sent, true);
        assert.strictEqual(send.payload.email.toCount, 1);
        emailRequest = requests
          .slice(beforeCount)
          .find((request) => request.url === "https://api.resend.com/emails");
        assert.strictEqual(
          emailRequest.options.headers["idempotency-key"],
          undefined,
          "test sends carry no idempotency key",
        );
        const testPayload = JSON.parse(emailRequest.options.body);
        assert.deepStrictEqual(testPayload.to, ["test-only@example.com"]);
        assert.match(testPayload.subject, /^\[Test\] /);

        beforeCount = requests.length;
        send = await run({ sendEmail: "1" });
        assert.strictEqual(send.code, 200, "unauthorized manual request is reported");
        assert.strictEqual(send.payload.email.attempted, false);
        assert.match(send.payload.email.reason, /Manual trigger rejected/);
        assert.strictEqual(
          requests
            .slice(beforeCount)
            .filter((request) => request.url === "https://api.resend.com/emails")
            .length,
          0,
          "unauthorized manual request does not send",
        );

        await withEnv({ CONGRESS_EMAIL_FROM: undefined }, async () => {
          const failed = await run(
            {},
            "GET",
            { authorization: "Bearer smoke-cron-secret" },
          );
          assert.strictEqual(failed.code, 502, "missing send config returns 502");
          assert.strictEqual(failed.payload.ok, false);
          assert.deepStrictEqual(Object.keys(failed.payload).sort(), [
            "detail",
            "error",
            "ok",
          ]);
        });
      } finally {
        global.fetch = originalFetch;
      }
    },
  );

  await runSmokeApiRoutes();
  console.log("smoke-email: all contract checks passed");
})().catch((err) => {
  console.error("smoke-email FAILED:", err.message);
  process.exit(1);
});
