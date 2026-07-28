#!/usr/bin/env bash
# One-time setup for the weekly email + feedback channel.
#
#   1. Fill in the empty values in .env.local (see its comments).
#   2. Run: bash scripts/setup-env.sh
#
# Pushes every value to the Vercel project (production), sets the GitHub
# Actions secret, triggers a redeploy, and prints the test-send command.
set -euo pipefail
cd "$(dirname "$0")/.."

[ -f .env.local ] || { echo ".env.local is missing"; exit 1; }
set -a
# shellcheck disable=SC1091
source .env.local
set +a

if [ ! -d .vercel ]; then
  echo "Linking the Vercel project..."
  vercel link --yes
fi

VARS=(RESEND_API_KEY CRON_SECRET CONGRESS_EMAIL_FROM CONGRESS_EMAIL_TO \
      CONGRESS_EMAIL_TEST_TO CONGRESS_TEST_SECRET CONGRESS_LIST_PASSWORD \
      UPSTASH_REDIS_REST_URL UPSTASH_REDIS_REST_TOKEN FEEDBACK_ADMIN_SECRET)
for v in "${VARS[@]}"; do
  val="${!v:-}"
  if [ -z "$val" ]; then
    echo "SKIP $v (empty in .env.local)"
    continue
  fi
  vercel env rm "$v" production --yes >/dev/null 2>&1 || true
  printf '%s' "$val" | vercel env add "$v" production >/dev/null
  echo "set $v"
done

if [ -n "${FEEDBACK_ADMIN_SECRET:-}" ]; then
  gh secret set FEEDBACK_ADMIN_SECRET \
    --repo your-github-user/your-repo \
    --body "$FEEDBACK_ADMIN_SECRET"
  echo "set GitHub secret FEEDBACK_ADMIN_SECRET"
fi

# Env changes only apply to new deployments.
git commit --allow-empty -m "Redeploy for env vars" && git push

echo ""
echo "Done. Wait about a minute for the deploy, then send yourself the test email:"
echo "  curl -s \"https://your-deployment.vercel.app/api/email?testEmail=1&key=${CONGRESS_TEST_SECRET:-<CONGRESS_TEST_SECRET>}\""
