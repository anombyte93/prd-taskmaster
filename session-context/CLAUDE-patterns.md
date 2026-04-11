## 17:23 AWST 11/04/2026

1. **Phase files as deferred loading** — each phase is a separate .md that gets Read only when needed, reducing context cost at skill invocation
2. **Handoff prompt may reference phantom files** — always verify file existence before depending on handoff-prompt references
3. **Repo vs live divergence** — the repo and live skill can drift; always check both before assuming which has the latest code
