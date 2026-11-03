# Crawler runtime profiles

- `crawler-seccomp.json`: Playwright v1.64.1's Docker seccomp profile from
  https://github.com/microsoft/playwright/blob/v1.64.1/utils/docker/seccomp_profile.json
  plus an unconditional `chroot` syscall allow rule. The upstream rule only
  enables chroot when Docker grants CAP_SYS_CHROOT; this worker drops every
  capability. Chromium needs chroot inside its newly created user namespace.
  Allowing the syscall does not grant CAP_SYS_CHROOT in the parent namespace.
- `buscadin-crawler.apparmor`: Moby default container protections, with explicit
  `userns` permission and ABI 4.0 (`network unix` included explicitly). This
  profile applies only to the crawler and leaves the host's unprivileged-userns
  restriction and Docker's default profile in place.

The worker has no credentials, host volumes or Docker socket. It runs non-root,
with a read-only rootfs, all capabilities dropped, no-new-privileges, private IPC,
resource limits and a private encrypted overlay shared only with the admin.

Startup requires observable extra PID namespaces and an additional seccomp filter
in a Chromium child with zero effective capabilities. A successful launch alone
is not considered proof of the renderer sandbox. Sandbox failure prevents startup.
