const crypto = require('node:crypto');
const fs = require('node:fs');

const expected = 'b9e3b8fce688656f928dd826ec84a81493131ec973c62822f9a01d6241007cbb';
const paths = [
  '/app/apps/backend/dist/libraries/nestjs-libraries/src/integrations/social/instagram.standalone.provider.js',
  '/app/apps/orchestrator/dist/libraries/nestjs-libraries/src/integrations/social/instagram.standalone.provider.js',
];
for (const path of paths) {
  const original = fs.readFileSync(path, 'utf8');
  const digest = crypto.createHash('sha256').update(original).digest('hex');
  if (digest !== expected) throw new Error(`Unsupported Postiz provider at ${path}: ${digest}`);
  const oldLine = 'this.refreshCron = true;';
  if (!original.includes(oldLine)) throw new Error(`Missing refreshCron at ${path}`);
  const patched = original.replace(oldLine, 'this.refreshCron = !process.env.INSTAGRAM_UNIFIED_CONFIG_ID;')
    + '\nrequire("/app/buscadin-unified-instagram.js").install(exports.InstagramStandaloneProvider, instagramProvider);\n';
  fs.writeFileSync(path, patched);
}
