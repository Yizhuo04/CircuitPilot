# Security and responsible testing

This development release supports low-voltage educational reference layouts.
Do not use it for mains, high-voltage, medical, automotive, or other critical circuits.
No currently bundled board or footprint is physically verified. Plans always retain
`ready_to_build: false`; photographs never establish continuity or electrical safety.

Authentication uses salted scrypt password hashes, opaque revocable sessions, and
HttpOnly SameSite=Strict cookies. Cookie-authenticated writes require an allowed
Origin. User resources are checked against project ownership, including images,
annotations, plans, verification jobs, exports, and pilot measurements. Photos are
decoded/re-encoded, metadata is stripped, and request/image sizes are bounded.

For deployment, require HTTPS, secure cookies, PostgreSQL migrations, a persistent
upload volume shared by backend and worker, and scheduled retention maintenance.
Production configuration rejects insecure cookies, plain-HTTP origins, SQLite,
and automatic schema creation. Add upstream rate/request limits; the in-process
authentication limiter is supplementary and is not shared across replicas.

Only operators can configure a local detector model directory. User uploads cannot
select model weights. PyTorch weight files must be trusted; provenance/hash checks
do not make arbitrary serialized weights safe. Review model and dependency licenses
before commercial use. Do not accept external weight files as uploaded user data.

No email verification, password reset, institutional SSO, or account recovery is
implemented. Resolve those account lifecycle needs before a public paid service.
This repository is public; uploaded photos, `.env`, datasets, and weights are ignored.
Keep operational logs free of credentials and signed upload URLs.

Report security issues privately to the repository owner using GitHub's private
vulnerability reporting when available. Do not place credentials or user photos in
public issues. This document records implemented boundaries and release limits;
it is not a certification of electrical or information security.
