# Isolated company crawler

The admin uses `RemoteCompanyCrawler` and never launches a local browser. The
browser-free application image is Dockerfile target `app` (the default). The
browser service is target `crawler`; both use the same locked Python dependencies.
There is no local fallback if the service is unavailable.

Only source name, bounded known IDs and crawl limits cross the RPC boundary.
Requests cannot supply URLs or commands. Returned jobs are size limited,
validated against a strict schema and checked for source/URL/ID consistency.
Compressed responses and redirects are rejected. Persistence, curation, audit,
publication policy and deduplication remain in the admin.

## VPS deployment

1. Install the tracked security profiles in `/etc/buscadin-crawler/seccomp.json`
   and `/etc/apparmor.d/buscadin-crawler`; load the latter with `apparmor_parser -r`.
2. Create `buscadin-crawler-private` as a Docker overlay with `--attachable --opt encrypted`.
3. Set `BUSCADIN_CRAWLER_IMAGE` to a versioned browser image and run
   `docker compose -f deploy/crawler.compose.yaml up -d`.
4. Confirm healthy startup and the logged sandbox evidence before attaching the
   admin Swarm service to that network and deploying the browser-free app image.
5. Restrict the network to those two peers. The RPC has no published port or
   bearer credential: admission is limited to this private encrypted network and
   the endpoint exposes only the bounded crawl operation. There is no arbitrary
   URL, script, file or browser-control interface.

The crawler has no database URL, password, worker token, mounted Docker secrets,
host home, volumes or Docker socket. Startup refuses application credentials.
It runs UID 10001 with read-only rootfs, tmpfs scratch storage, all capabilities
removed, no-new-privileges, private IPC, memory/CPU/PID limits and dedicated
AppArmor/seccomp profiles. Chromium always uses `chromium_sandbox=True`.

The startup probe verifies extra PID namespaces and an extra seccomp filter on a
Chromium child with no effective capabilities. It fails closed. The host's
AppArmor user-namespace restriction, WireGuard, proxy and Listmonk do not require
configuration changes.

Use `scripts/check_browser_runtime.py` inside the restricted crawler container for
an offline repeat of the sandbox probe. A collection requested in the admin still
uses the existing bounded, deduplicating persistence flow. Do not roll back the
admin to an image that launches Chromium with its database secrets; roll back to
a browser-free RPC client image if a source or browser update fails.
