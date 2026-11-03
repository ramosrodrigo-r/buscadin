FROM ghcr.io/gitroomhq/postiz-app@sha256:1e376ff2cb781022d528f171719cf174cf693a985a30cb40eefb13eae3ddda13

COPY unified-instagram.js /app/buscadin-unified-instagram.js
COPY patch-provider.js /tmp/buscadin-patch-provider.js
RUN node /tmp/buscadin-patch-provider.js && rm /tmp/buscadin-patch-provider.js
