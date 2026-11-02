# Security policy

## Scope

Motion Planning Playground is a local, educational tool. `mpplay serve` binds to
`127.0.0.1` by default and is **not** designed to be exposed to untrusted networks: the
API runs CPU-intensive planning requests without authentication, and plugins
(`--plugin`) execute arbitrary Python code by design. Only load plugins you trust.

If you deploy the server for a class or a demo, put it behind a reverse proxy with
authentication and rate limiting, and run it in an isolated environment.

## Supported versions

Security fixes are made for the latest released version.

## Reporting a vulnerability

Please do not open a public issue for security problems. Report them privately through
[GitHub security advisories](https://github.com/evitamin01/motion-planning-playground/security/advisories/new).
You can expect an acknowledgement within a week. We will keep you informed while we work
on a fix and credit you in the release notes unless you prefer otherwise.
