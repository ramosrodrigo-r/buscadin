'use strict';

const crypto = require('node:crypto');

const GRAPH_VERSION = 'v26.0';
const GRAPH = `https://graph.facebook.com/${GRAPH_VERSION}`;

function config() {
  const appId = process.env.INSTAGRAM_UNIFIED_APP_ID;
  const appSecret = process.env.INSTAGRAM_UNIFIED_APP_SECRET;
  const configId = process.env.INSTAGRAM_UNIFIED_CONFIG_ID;
  const frontend = new URL(process.env.FRONTEND_URL || '');
  if (!appId || !appSecret || !configId || frontend.protocol !== 'https:') {
    throw new Error('Instagram Unified login is missing its Meta app credentials or HTTPS frontend');
  }
  return { appId, appSecret, configId,
    redirect: new URL('/integrations/social/instagram-standalone', frontend).toString() };
}

async function graph(path, token) {
  const response = await fetch(`${GRAPH}${path}`, { headers: { Authorization: `Bearer ${token}` },
    redirect: 'error', signal: AbortSignal.timeout(10000) });
  if (!response.ok) throw new Error(`Meta Graph returned HTTP ${response.status}`);
  const value = await response.json();
  if (!value || typeof value !== 'object' || value.error) {
    throw new Error('Meta Graph returned an invalid response');
  }
  return value;
}

async function detailsForToken(token, expiresIn) {
  const accountId = process.env.INSTAGRAM_UNIFIED_ACCOUNT_ID || '';
  let next = `/me/assigned_instagram_accounts?fields=id,username&limit=100`;
  const accounts = [];
  const visited = new Set();
  while (next) {
    if (visited.has(next) || visited.size >= 5) throw new Error('Meta pagination did not finish');
    visited.add(next);
    const page = await graph(next, token);
    if (!Array.isArray(page.data)) throw new Error('Meta did not return assigned Instagram accounts');
    accounts.push(...page.data);
    const more = page.paging?.next;
    if (more) {
      const url = new URL(more);
      if (url.hostname !== 'graph.facebook.com' || !url.pathname.startsWith(`/${GRAPH_VERSION}/`)) {
        throw new Error('Meta returned an unexpected pagination URL');
      }
      next = url.pathname.slice(`/${GRAPH_VERSION}`.length) + url.search;
    } else {
      next = '';
    }
    if (accounts.length > 100) throw new Error('Too many assigned Instagram accounts');
  }
  const selected = accountId ? accounts.find((row) => row.id === accountId)
    : accounts.length === 1 ? accounts[0] : null;
  if (!selected || typeof selected.id !== 'string' || !selected.id) {
    throw new Error('Select one assigned Instagram account in Meta or configure its ID');
  }
  const seconds = Number(expiresIn);
  return {
    id: selected.id,
    name: selected.username || selected.id,
    username: selected.username || '',
    picture: '',
    accessToken: token,
    refreshToken: token,
    expiresIn: Number.isFinite(seconds) && seconds > 0 ? seconds : 10 * 365 * 24 * 60 * 60,
  };
}

function install(Provider, shared) {
  if (!process.env.INSTAGRAM_UNIFIED_CONFIG_ID) return;
  Provider.prototype.generateAuthUrl = async function () {
    const { appId, configId, redirect } = config();
    const state = crypto.randomBytes(24).toString('base64url');
    const url = new URL(`https://www.facebook.com/${GRAPH_VERSION}/dialog/oauth`);
    for (const [key, value] of Object.entries({
      client_id: appId,
      config_id: configId,
      redirect_uri: redirect,
      response_type: 'code',
      override_default_response_type: 'true',
      prompt: 'login',
      state,
    })) url.searchParams.set(key, value);
    return { url: url.toString(), codeVerifier: crypto.randomBytes(16).toString('base64url'), state };
  };
  Provider.prototype.authenticate = async function ({ code }) {
    const { appId, appSecret, redirect } = config();
    if (!code || typeof code !== 'string') throw new Error('Missing Meta authorization code');
    const url = new URL(`${GRAPH}/oauth/access_token`);
    for (const [key, value] of Object.entries({ client_id: appId, client_secret: appSecret,
      redirect_uri: redirect, code })) url.searchParams.set(key, value);
    const response = await fetch(url, { redirect: 'error', signal: AbortSignal.timeout(10000) });
    if (!response.ok) throw new Error(`Meta code exchange returned HTTP ${response.status}`);
    const result = await response.json();
    if (typeof result.access_token !== 'string' || !result.access_token) {
      throw new Error('Meta code exchange returned no token');
    }
    return detailsForToken(result.access_token, result.expires_in);
  };
  Provider.prototype.refreshToken = async function (token) {
    return detailsForToken(token);
  };
  // Unified login issues a Meta Graph token; the legacy standalone path uses graph.instagram.com.
  Provider.prototype.post = function (id, accessToken, postDetails, integration) {
    return shared.post(id, accessToken, postDetails, integration, 'graph.facebook.com');
  };
  Provider.prototype.postPending = function (id, accessToken, postDetails, integration) {
    return shared.postPending(id, accessToken, postDetails, integration, 'graph.facebook.com');
  };
  Provider.prototype.comment = function (id, postId, lastCommentId, accessToken, postDetails, integration) {
    return shared.comment(id, postId, lastCommentId, accessToken, postDetails, integration, 'graph.facebook.com');
  };
  Provider.prototype.analytics = function (id, accessToken, date) {
    return shared.analytics(id, accessToken, date, 'graph.facebook.com');
  };
  Provider.prototype.postAnalytics = function (integrationId, accessToken, postId, date) {
    return shared.postAnalytics(integrationId, accessToken, postId, date, 'graph.facebook.com');
  };
}

module.exports = { install };
