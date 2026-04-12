# Debrief: DVWA + Shade MCP Testing Setup

**Date**: 2026-04-09 08:16 AWST
**Parent Session**: prd-taskmaster-v2 (this repo)
**Handoff To**: atlas-shade

## What Was Done

1. Full /question research (FULL depth, 8 queries + perplexity_reason) on DVWA setup + Shade tool mapping
2. Pulled `vulnerables/web-dvwa:latest` Docker image
3. Launched DVWA container `dvwa-shade` on port 4280 (0.0.0.0 bound)
4. Auto-setup database via programmatic curl chain (login → extract CSRF token → POST setup)
5. Set security level to LOW via same CSRF token chain pattern
6. Mapped all 5 Shade MCP tools to appropriate DVWA vulnerability modules

## What Needs To Be Done

Test ALL 5 Shade MCP tools against DVWA in this order:

1. **shade-monitor** — Port scan + tech detect against DVWA (127.0.0.1:4280)
2. **shade-proxy** — Start mitmproxy, intercept DVWA traffic, replay/fuzz SQLi + XSS forms
3. **shade-collaborator** — Start listener, generate payload, inject via Command Injection module, confirm callback
4. **shade-metasploit** — Generate PHP payload, deliver via Command Injection or File Upload, catch shell
5. **shade-hive** — Demo multi-hop chain routing to DVWA

After confirming all tools work on LOW:
- Escalate to MEDIUM, re-test
- Escalate to HIGH, re-test

## Key Insight (IMPORTANT)

MySQL does NOT support OOB DNS lookups (no UTL_HTTP like Oracle, no xp_dirtree like MSSQL). shade-collaborator should target **Command Injection** (OS-level DNS/HTTP callbacks) NOT Blind SQLi for DVWA testing.

## DVWA State

- Container: `dvwa-shade` 
- URL: `http://127.0.0.1:4280`
- Credentials: admin / password
- Security Level: LOW
- DB: initialized and ready
- Cookie jar (may be stale by handoff): `/tmp/dvwa_cookies.txt`

## Research Findings (from /question)

- DVWA modules: brute, sqli, sqli_blind, xss_r, xss_s, xss_d, exec (command injection), fi (file inclusion), upload, csrf, captcha, weak_session_ids, csp
- URL pattern: `/vulnerabilities/<module>/`
- Security level set via POST to `/security.php` with `security=low&seclev_submit=Submit&user_token=TOKEN`
