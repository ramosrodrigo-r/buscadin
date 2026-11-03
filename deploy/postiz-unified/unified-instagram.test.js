const assert = require('node:assert/strict');
const test = require('node:test');
const { install } = require('./unified-instagram');

const keys = ['INSTAGRAM_UNIFIED_APP_ID', 'INSTAGRAM_UNIFIED_APP_SECRET',
  'INSTAGRAM_UNIFIED_CONFIG_ID', 'INSTAGRAM_UNIFIED_ACCOUNT_ID', 'FRONTEND_URL'];
const previous = Object.fromEntries(keys.map((key) => [key, process.env[key]]));

function setup() {
  process.env.INSTAGRAM_UNIFIED_APP_ID = '12345';
  process.env.INSTAGRAM_UNIFIED_APP_SECRET = 'test-secret';
  process.env.INSTAGRAM_UNIFIED_CONFIG_ID = 'config-1';
  process.env.FRONTEND_URL = 'https://rodrigodesktop.tail88c0f5.ts.net';
  delete process.env.INSTAGRAM_UNIFIED_ACCOUNT_ID;
  class Provider {}
  const calls = [];
  const shared = Object.fromEntries(['post', 'postPending', 'comment', 'analytics', 'postAnalytics']
    .map((name) => [name, (...args) => { calls.push([name, args]); return name; }]));
  install(Provider, shared);
  return { provider: new Provider(), calls };
}

test.after(() => {
  for (const key of keys) {
    if (previous[key] === undefined) delete process.env[key];
    else process.env[key] = previous[key];
  }
});

test('uses config_id and the standalone callback without legacy scope', async () => {
  const { provider } = setup();
  const { url, state } = await provider.generateAuthUrl();
  const parsed = new URL(url);
  assert.equal(parsed.origin, 'https://www.facebook.com');
  assert.equal(parsed.searchParams.get('config_id'), 'config-1');
  assert.equal(parsed.searchParams.get('scope'), null);
  assert.equal(parsed.searchParams.get('response_type'), 'code');
  assert.equal(parsed.searchParams.get('redirect_uri'),
    'https://rodrigodesktop.tail88c0f5.ts.net/integrations/social/instagram-standalone');
  assert.equal(parsed.searchParams.get('state'), state);
});

test('exchanges code and selects the sole assigned Instagram account', async () => {
  const { provider, calls } = setup();
  const oldFetch = global.fetch;
  global.fetch = async (input, options) => {
    const url = new URL(input);
    if (url.pathname.endsWith('/oauth/access_token')) {
      assert.equal(url.searchParams.get('client_secret'), 'test-secret');
      assert.equal(url.searchParams.get('code'), 'test-code');
      return new Response(JSON.stringify({ access_token: 'meta-token', expires_in: 0 }), { status: 200 });
    }
    assert.equal(url.pathname, '/v26.0/me/assigned_instagram_accounts');
    assert.equal(options.headers.Authorization, 'Bearer meta-token');
    return new Response(JSON.stringify({ data: [{ id: 'ig-123', username: 'buscadin' }] }), { status: 200 });
  };
  try {
    const details = await provider.authenticate({ code: 'test-code' });
    assert.equal(details.id, 'ig-123');
    assert.equal(details.accessToken, 'meta-token');
    assert.ok(details.expiresIn > 0);
    assert.equal(provider.post('ig-123', 'meta-token', [], {}), 'post');
    assert.equal(calls[0][1].at(-1), 'graph.facebook.com');
  } finally {
    global.fetch = oldFetch;
  }
});

test('requires explicit account choice when the token can see multiple accounts', async () => {
  const { provider } = setup();
  const oldFetch = global.fetch;
  global.fetch = async (input) => {
    const url = new URL(input);
    return new Response(JSON.stringify(url.pathname.endsWith('/oauth/access_token')
      ? { access_token: 'meta-token' }
      : { data: [{ id: 'a', username: 'a' }, { id: 'b', username: 'b' }] }), { status: 200 });
  };
  try {
    await assert.rejects(provider.authenticate({ code: 'test-code' }), /Select one assigned/);
    process.env.INSTAGRAM_UNIFIED_ACCOUNT_ID = 'b';
    assert.equal((await provider.authenticate({ code: 'test-code' })).id, 'b');
  } finally {
    global.fetch = oldFetch;
  }
});
