// Local contract checks for the API routes that use Redis or Resend.
// Every external request is mocked. This script never reaches a live service.
const assert = require("node:assert");
const path = require("node:path");

const feedback = require(path.join(__dirname, "..", "api", "feedback.js"));
const feedbackExport = require(path.join(__dirname, "..", "api", "feedback-export.js"));
const feedbackStatus = require(path.join(__dirname, "..", "api", "feedback-status.js"));
const recipients = require(path.join(__dirname, "..", "api", "recipients.js"));

function makeRes() {
  const res = { headers: {}, code: null, payload: null, sent: null };
  res.status = (code) => {
    res.code = code;
    return res;
  };
  res.setHeader = (key, value) => {
    res.headers[key] = value;
  };
  res.json = (payload) => {
    res.payload = payload;
    return res;
  };
  res.send = (value) => {
    res.sent = value;
    return res;
  };
  return res;
}

async function call(handler, options = {}) {
  const res = makeRes();
  const req = {
    method: options.method || "GET",
    query: options.query || {},
    headers: options.headers || {},
    body: options.body,
    socket: options.socket || { remoteAddress: "127.0.0.1" },
  };
  await handler(req, res);
  return res;
}

function fetchResponse(payload, status = 200) {
  const text = typeof payload === "string" ? payload : JSON.stringify(payload);
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => JSON.parse(text),
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

function redisMock(responder, calls) {
  return async (url, options = {}) => {
    const parsed = new URL(url);
    assert.strictEqual(parsed.origin, "https://mock-redis.local");
    assert.strictEqual(options.headers.Authorization, "Bearer mock-token");
    const parts = parsed.pathname
      .split("/")
      .filter(Boolean)
      .map((part) => decodeURIComponent(part));
    const command = parts.shift();
    calls.push({ command, args: parts });
    const result = responder(command, parts);
    return fetchResponse(result.payload, result.status || 200);
  };
}

async function testFeedbackSubmission() {
  let res = await call(feedback, { method: "GET" });
  assert.strictEqual(res.code, 405);
  assert.strictEqual(res.headers.Allow, "POST");
  assert.deepStrictEqual(res.payload, { error: "method not allowed" });

  res = await call(feedback, {
    method: "POST",
    headers: { "content-length": "25001" },
    body: "{}",
  });
  assert.strictEqual(res.code, 413);

  await withEnv(
    {
      UPSTASH_REDIS_REST_URL: undefined,
      UPSTASH_REDIS_REST_TOKEN: undefined,
    },
    async () => {
      const missing = await call(feedback, { method: "POST", body: { note: "Note" } });
      assert.strictEqual(missing.code, 500);
      assert.deepStrictEqual(Object.keys(missing.payload).sort(), ["error", "message"]);
    },
  );

  await withEnv(
    {
      UPSTASH_REDIS_REST_URL: "https://mock-redis.local",
      UPSTASH_REDIS_REST_TOKEN: "mock-token",
    },
    async () => {
      let invalid = await call(feedback, { method: "POST", body: "{" });
      assert.strictEqual(invalid.code, 400);
      assert.deepStrictEqual(invalid.payload, { error: "invalid JSON payload" });

      invalid = await call(feedback, { method: "POST", body: {} });
      assert.strictEqual(invalid.code, 400);
      assert.deepStrictEqual(invalid.payload, {
        error: "Add a note before submitting.",
      });

      const calls = [];
      const originalFetch = global.fetch;
      global.fetch = redisMock((command) => {
        if (command === "incr") return { payload: { result: 1 } };
        return { payload: { result: "OK" } };
      }, calls);
      try {
        const valid = await call(feedback, {
          method: "POST",
          headers: {
            "user-agent": "route-smoke",
            "x-forwarded-for": "192.0.2.4, 198.51.100.2",
          },
          body: {
            note: "<b>Keep</b>   this clean",
            context: {
              page_url: "https://example.com/",
              filters: { recent_only: "no" },
              target: { region: "feed table", text: "<em>row</em>" },
              user_agent: "body-agent",
            },
          },
        });
        assert.strictEqual(valid.code, 200);
        assert.strictEqual(valid.payload.ok, true);
        assert.match(valid.payload.id, /^congress_fb_\d{8}_[a-f0-9]{8}$/);
        assert.deepStrictEqual(
          calls.map((entry) => entry.command),
          ["incr", "expire", "lpush", "ltrim"],
        );
        assert.match(calls[0].args[0], /^congressional_feedback_rate:[a-f0-9]{24}$/);
        assert.deepStrictEqual(calls[1].args.slice(1), ["3600"]);
        assert.strictEqual(calls[2].args[0], "congressional_investigations_feedback");
        const record = JSON.parse(calls[2].args[1]);
        assert.deepStrictEqual(Object.keys(record).sort(), [
          "context",
          "created_at",
          "id",
          "note",
          "status",
        ]);
        assert.strictEqual(record.note, "Keep this clean");
        assert.strictEqual(record.status, "new");
        assert.strictEqual(record.context.user_agent, "route-smoke");
        assert.strictEqual(record.context.filters.recent_only, "no");
        assert.strictEqual(record.context.target.text, "row");
        assert.deepStrictEqual(calls[3].args, [
          "congressional_investigations_feedback",
          "0",
          "999",
        ]);
      } finally {
        global.fetch = originalFetch;
      }

      const limitedCalls = [];
      const originalFetchForLimit = global.fetch;
      global.fetch = redisMock(
        (command) =>
          command === "incr"
            ? { payload: { result: 13 } }
            : { payload: { result: "OK" } },
        limitedCalls,
      );
      try {
        const limited = await call(feedback, {
          method: "POST",
          body: { note: "Too many" },
        });
        assert.strictEqual(limited.code, 429);
        assert.deepStrictEqual(
          limitedCalls.map((entry) => entry.command),
          ["incr"],
        );
      } finally {
        global.fetch = originalFetchForLimit;
      }

      const originalFetchForError = global.fetch;
      global.fetch = redisMock(
        () => ({
          payload: { error: "mock Redis failure" },
          status: 500,
        }),
        [],
      );
      try {
        const failed = await call(feedback, {
          method: "POST",
          body: { note: "Store this" },
        });
        assert.strictEqual(failed.code, 502);
        assert.deepStrictEqual(failed.payload, {
          error: "mock Redis failure",
        });
      } finally {
        global.fetch = originalFetchForError;
      }
    },
  );
}

async function testFeedbackExport() {
  let res = await call(feedbackExport, { method: "POST" });
  assert.strictEqual(res.code, 405);
  assert.strictEqual(res.headers.Allow, "GET");

  await withEnv(
    {
      FEEDBACK_ADMIN_SECRET: "admin-secret",
      UPSTASH_REDIS_REST_URL: undefined,
      UPSTASH_REDIS_REST_TOKEN: undefined,
    },
    async () => {
      const unauthorized = await call(feedbackExport, {
        query: { key: "wrong" },
      });
      assert.strictEqual(unauthorized.code, 401);

      const missing = await call(feedbackExport, {
        query: { key: "admin-secret" },
      });
      assert.strictEqual(missing.code, 500);
    },
  );

  await withEnv(
    {
      FEEDBACK_ADMIN_SECRET: "admin-secret",
      UPSTASH_REDIS_REST_URL: "https://mock-redis.local",
      UPSTASH_REDIS_REST_TOKEN: "mock-token",
    },
    async () => {
      const rows = [
        JSON.stringify({
          id: "new-id",
          status: "new",
          note: "Review this",
          context: { target: { region: "feed table" }, filters: {} },
        }),
        "{bad",
        JSON.stringify({ id: "done-id", status: "processed", note: "Done" }),
      ];
      const calls = [];
      const originalFetch = global.fetch;
      global.fetch = redisMock(
        () => ({ payload: { result: rows } }),
        calls,
      );
      try {
        const exported = await call(feedbackExport, {
          query: { key: "admin-secret", limit: "999", status: "new" },
        });
        assert.strictEqual(exported.code, 200);
        assert.deepStrictEqual(exported.payload, {
          ok: true,
          count: 1,
          records: [JSON.parse(rows[0])],
        });
        assert.deepStrictEqual(calls[0], {
          command: "lrange",
          args: ["congressional_investigations_feedback", "0", "499"],
        });

        const markdown = await call(feedbackExport, {
          query: { key: "admin-secret", format: "md", limit: "2" },
        });
        assert.strictEqual(markdown.code, 200);
        assert.strictEqual(
          markdown.headers["Content-Type"],
          "text/markdown; charset=utf-8",
        );
        assert.match(markdown.sent, /^# Congressional investigations feedback/m);
        assert.match(markdown.sent, /## new-id - feed table/);
      } finally {
        global.fetch = originalFetch;
      }

      const originalFetchForError = global.fetch;
      global.fetch = redisMock(
        () => ({
          payload: { error: "mock Redis failure" },
          status: 500,
        }),
        [],
      );
      try {
        const failed = await call(feedbackExport, {
          query: { key: "admin-secret" },
        });
        assert.strictEqual(failed.code, 502);
        assert.deepStrictEqual(failed.payload, {
          error: "mock Redis failure",
        });
      } finally {
        global.fetch = originalFetchForError;
      }
    },
  );
}

async function testFeedbackStatus() {
  let res = await call(feedbackStatus, { method: "GET" });
  assert.strictEqual(res.code, 405);
  assert.strictEqual(res.headers.Allow, "POST");

  await withEnv(
    {
      FEEDBACK_ADMIN_SECRET: "admin-secret",
      UPSTASH_REDIS_REST_URL: undefined,
      UPSTASH_REDIS_REST_TOKEN: undefined,
    },
    async () => {
      const unauthorized = await call(feedbackStatus, {
        method: "POST",
        query: { key: "wrong" },
      });
      assert.strictEqual(unauthorized.code, 401);

      const missing = await call(feedbackStatus, {
        method: "POST",
        query: { key: "admin-secret" },
      });
      assert.strictEqual(missing.code, 500);
    },
  );

  await withEnv(
    {
      FEEDBACK_ADMIN_SECRET: "admin-secret",
      UPSTASH_REDIS_REST_URL: "https://mock-redis.local",
      UPSTASH_REDIS_REST_TOKEN: "mock-token",
    },
    async () => {
      let invalid = await call(feedbackStatus, {
        method: "POST",
        query: { key: "admin-secret" },
        body: "{",
      });
      assert.strictEqual(invalid.code, 400);

      invalid = await call(feedbackStatus, {
        method: "POST",
        query: { key: "admin-secret" },
        body: { id: "target", status: "unknown" },
      });
      assert.strictEqual(invalid.code, 400);

      const rows = [
        "{bad",
        JSON.stringify({ id: "target", status: "new", note: "Note" }),
      ];
      const calls = [];
      const originalFetch = global.fetch;
      global.fetch = redisMock((command) => {
        if (command === "lrange") return { payload: { result: rows } };
        return { payload: { result: "OK" } };
      }, calls);
      try {
        const updated = await call(feedbackStatus, {
          method: "POST",
          query: { key: "admin-secret" },
          body: {
            id: "target",
            status: "processed",
            resolution: "Handled",
          },
        });
        assert.strictEqual(updated.code, 200);
        assert.deepStrictEqual(updated.payload, {
          ok: true,
          id: "target",
          status: "processed",
        });
        assert.deepStrictEqual(calls[0], {
          command: "lrange",
          args: ["congressional_investigations_feedback", "0", "999"],
        });
        assert.strictEqual(calls[1].command, "lset");
        assert.deepStrictEqual(calls[1].args.slice(0, 2), [
          "congressional_investigations_feedback",
          "1",
        ]);
        const stored = JSON.parse(calls[1].args[2]);
        assert.strictEqual(stored.status, "processed");
        assert.strictEqual(stored.resolution, "Handled");
        assert.match(stored.status_updated_at, /^\d{4}-\d{2}-\d{2}T/);
      } finally {
        global.fetch = originalFetch;
      }

      const originalFetchForMissing = global.fetch;
      global.fetch = redisMock(
        () => ({ payload: { result: [] } }),
        [],
      );
      try {
        const missing = await call(feedbackStatus, {
          method: "POST",
          query: { key: "admin-secret" },
          body: { id: "missing", status: "dismissed" },
        });
        assert.strictEqual(missing.code, 404);
        assert.deepStrictEqual(missing.payload, {
          error: "no feedback record with id missing",
        });
      } finally {
        global.fetch = originalFetchForMissing;
      }

      const originalFetchForError = global.fetch;
      global.fetch = redisMock(
        () => ({
          payload: { error: "mock Redis failure" },
          status: 500,
        }),
        [],
      );
      try {
        const failed = await call(feedbackStatus, {
          method: "POST",
          query: { key: "admin-secret" },
          body: { id: "target", status: "processed" },
        });
        assert.strictEqual(failed.code, 502);
        assert.deepStrictEqual(failed.payload, {
          error: "mock Redis failure",
        });
      } finally {
        global.fetch = originalFetchForError;
      }
    },
  );
}

function resendMock(state, calls) {
  return async (url, options = {}) => {
    const parsed = new URL(url);
    assert.strictEqual(parsed.origin, "https://api.resend.com");
    const method = options.method || "GET";
    calls.push({ method, path: parsed.pathname, body: options.body });

    if (method === "GET" && parsed.pathname === "/audiences") {
      return fetchResponse({
        data: [{ id: "audience-id", name: recipients.helpers.AUDIENCE_NAME }],
      });
    }
    if (method === "GET" && parsed.pathname === "/audiences/audience-id/contacts") {
      return fetchResponse({ data: state.contacts });
    }
    if (method === "POST" && parsed.pathname === "/audiences/audience-id/contacts") {
      const body = JSON.parse(options.body);
      state.contacts.push({
        id: `contact-${state.contacts.length + 1}`,
        email: body.email,
        unsubscribed: false,
      });
      return fetchResponse({ id: state.contacts.at(-1).id });
    }
    if (method === "DELETE" && parsed.pathname.startsWith("/audiences/audience-id/contacts/")) {
      const id = parsed.pathname.split("/").at(-1);
      state.contacts = state.contacts.filter((contact) => contact.id !== id);
      return fetchResponse({});
    }
    throw new Error(`Unexpected Resend request: ${method} ${parsed.pathname}`);
  };
}

async function testRecipients() {
  let res = await call(recipients, { method: "GET" });
  assert.strictEqual(res.code, 405);
  assert.strictEqual(res.headers["Cache-Control"], "no-store");
  assert.deepStrictEqual(res.payload, {
    ok: false,
    error: "Method not allowed.",
  });

  await withEnv(
    {
      CONGRESS_LIST_PASSWORD: undefined,
      RESEND_API_KEY: undefined,
    },
    async () => {
      const missing = await call(recipients, { method: "POST", body: {} });
      assert.strictEqual(missing.code, 503);
      assert.match(missing.payload.error, /CONGRESS_LIST_PASSWORD, RESEND_API_KEY/);
    },
  );

  await withEnv(
    {
      CONGRESS_LIST_PASSWORD: "list-password",
      RESEND_API_KEY: "mock-resend-key",
      CONGRESS_EMAIL_TO: "seed@example.com",
    },
    async () => {
      const originalTimeout = global.setTimeout;
      global.setTimeout = (fn) => {
        fn();
        return 0;
      };
      try {
        const wrong = await call(recipients, {
          method: "POST",
          body: { password: "wrong", action: "list" },
        });
        assert.strictEqual(wrong.code, 401);
        assert.strictEqual(wrong.headers["Cache-Control"], "no-store");
      } finally {
        global.setTimeout = originalTimeout;
      }

      const state = {
        contacts: [
          {
            id: "hidden",
            email: "owner@example.com",
            unsubscribed: false,
          },
          { id: "visible-b", email: "b@example.com", unsubscribed: false },
          { id: "visible-a", email: "a@example.com", unsubscribed: false },
          { id: "unsubscribed", email: "old@example.com", unsubscribed: true },
        ],
      };
      const calls = [];
      const originalFetch = global.fetch;
      global.fetch = resendMock(state, calls);
      try {
        const listed = await call(recipients, {
          method: "POST",
          body: { password: "list-password", action: "list" },
        });
        assert.strictEqual(listed.code, 200);
        assert.deepStrictEqual(listed.payload, {
          ok: true,
          recipients: ["a@example.com", "b@example.com"],
        });
        assert.strictEqual(listed.headers["Cache-Control"], "no-store");

        const invalid = await call(recipients, {
          method: "POST",
          body: {
            password: "list-password",
            action: "add",
            email: "not-an-email",
          },
        });
        assert.strictEqual(invalid.code, 400);

        const added = await call(recipients, {
          method: "POST",
          body: {
            password: "list-password",
            action: "add",
            email: " C@Example.com ",
          },
        });
        assert.strictEqual(added.code, 200);
        assert.deepStrictEqual(added.payload.recipients, [
          "a@example.com",
          "b@example.com",
          "c@example.com",
        ]);

        const hidden = await call(recipients, {
          method: "POST",
          body: {
            password: "list-password",
            action: "remove",
            email: "owner@example.com",
          },
        });
        assert.strictEqual(hidden.code, 404);

        const removed = await call(recipients, {
          method: "POST",
          body: {
            password: "list-password",
            action: "remove",
            email: "b@example.com",
          },
        });
        assert.strictEqual(removed.code, 200);
        assert.deepStrictEqual(removed.payload.recipients, [
          "a@example.com",
          "c@example.com",
        ]);
        assert.ok(
          calls.some(
            (entry) =>
              entry.method === "DELETE" &&
              entry.path === "/audiences/audience-id/contacts/visible-b",
          ),
        );
      } finally {
        global.fetch = originalFetch;
      }

      const oneVisible = {
        contacts: [
          {
            id: "hidden",
            email: "owner@example.com",
            unsubscribed: false,
          },
          { id: "only", email: "only@example.com", unsubscribed: false },
        ],
      };
      const originalFetchForLast = global.fetch;
      global.fetch = resendMock(oneVisible, []);
      try {
        const last = await call(recipients, {
          method: "POST",
          body: {
            password: "list-password",
            action: "remove",
            email: "only@example.com",
          },
        });
        assert.strictEqual(last.code, 400);
        assert.match(last.payload.error, /last recipient/);
      } finally {
        global.fetch = originalFetchForLast;
      }

      const originalFetchForError = global.fetch;
      global.fetch = async () =>
        fetchResponse({ message: "mock Resend failure" }, 500);
      try {
        const failed = await call(recipients, {
          method: "POST",
          body: { password: "list-password", action: "list" },
        });
        assert.strictEqual(failed.code, 502);
        assert.strictEqual(failed.headers["Cache-Control"], "no-store");
        assert.deepStrictEqual(Object.keys(failed.payload).sort(), [
          "detail",
          "error",
          "ok",
        ]);
        assert.match(failed.payload.detail, /mock Resend failure/);
      } finally {
        global.fetch = originalFetchForError;
      }
    },
  );

  const fallback = await recipients.helpers.resolveRecipients("", [
    "fallback@example.com",
  ]);
  assert.deepStrictEqual(fallback, {
    list: ["fallback@example.com"],
    source: "env",
    error: "RESEND_API_KEY missing",
  });
}

async function runSmokeApiRoutes() {
  await testFeedbackSubmission();
  await testFeedbackExport();
  await testFeedbackStatus();
  await testRecipients();
  console.log("smoke-api-routes: all mocked route checks passed");
}

module.exports = { runSmokeApiRoutes };

if (require.main === module) {
  runSmokeApiRoutes().catch((error) => {
    console.error("smoke-api-routes FAILED:", error.message);
    process.exit(1);
  });
}
