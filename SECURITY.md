# Security Policy

## Supported Scope

This repository is actively maintained on the `main` branch.

## Reporting a Vulnerability

Please do not open public issues for security-sensitive reports.

Report privately via GitHub Security Advisories (preferred) or contact the maintainer directly if advisory tooling is unavailable.

Include:

- Affected file(s) and component(s)
- Reproduction steps
- Impact assessment
- Proposed mitigation, if known

## Secrets and Sensitive Data

This repository must not contain:

- API keys, tokens, or passwords
- Private certificates/keys
- Local personal data exports
- Hardcoded machine-specific secrets

Before opening a PR:

1. Run a quick grep scan for common secret strings.
2. Confirm no personal data or local absolute paths were introduced.
3. Verify external process calls do not use `shell=True` with user input.

## Operational Notes

- The app executes external binaries (`ffmpeg`, `ffprobe`); ensure trusted binaries are used.
- Keep dependencies up to date and pin versions in `requirements.txt` as needed.
