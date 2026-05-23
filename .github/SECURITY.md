# Security Policy

## Supported versions

| Version | Supported |
|---|---|
| Latest (`main`) | ✅ |
| Older releases | ❌ (please upgrade) |

## Reporting a vulnerability

**Do not open a public GitHub Issue for security vulnerabilities.**

Please report security issues privately:

1. Go to the [Security Advisories](https://github.com/vishwa0198/agentsdk/security/advisories/new)
   page and click **"Report a vulnerability"**.
2. Describe the issue, steps to reproduce, and potential impact.
3. We will acknowledge your report within **48 hours** and aim to release a
   fix within **14 days** for critical issues.

## Scope

The following are **in scope**:

- Authentication/authorisation bypass in the Web UI backend
- JWT secret handling or token forgery
- Remote code execution via the `run_python` or MCP tool integrations
- Prompt injection that leads to data exfiltration
- Dependency vulnerabilities with a working exploit

The following are **out of scope**:

- Vulnerabilities in LLM model outputs (not our responsibility)
- Rate limiting bypass in development / local-only deployments
- Bugs that require physical access to the server

## Hardening tips for self-hosted deployments

- Set `SECRET_KEY` to a strong random value (`python -c "import secrets; print(secrets.token_hex(32))"`).
- Set `ALLOWED_ORIGINS` to your exact domain — never use `*` in production.
- Put the backend behind a reverse proxy with TLS.
- Restrict `/var/run/docker.sock` access if running in Docker.
