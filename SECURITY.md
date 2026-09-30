# Security

Ascent is a single-user desktop app. Its Flask API has no login and relies on binding to
`127.0.0.1` plus a Host / Origin guard in `tracker.py`, so the interesting attack surface is a
web page in your browser reaching the local API, and untrusted web content steering Linda.

## Reporting a vulnerability

Please report privately through GitHub:
**Security → Report a vulnerability** on this repository. Don't open a public issue.

Include the affected file, the steps to reproduce, and what an attacker gains. I aim to
reply within a week.

## Design notes

- Requests with a non-loopback `Host`, a foreign `Origin` or a cross-site `Sec-Fetch-Site`
  are rejected before routing.
- Draft with Linda reads files only inside `ASCENT_PROJECTS_ROOT`, after resolving symlinks
  and `..`.
- Once a web search result (Tavily or Exa) is in Linda's context, tools that change your data
  are refused for the rest of that message; you confirm in a new message.
- API keys are read from environment variables and sent only to their own service.
