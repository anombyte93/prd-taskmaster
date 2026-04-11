## 17:23 AWST 11/04/2026

1. **TaskMaster not detected** — `_detect_taskmaster_method()` only checked for `taskmaster` binary, but actual binary is `task-master-ai`. Fixed by checking both names.
2. **chezmoi apply fails** — Railway token template references bitwarden item that can't be resolved. Does not affect skill files. Workaround: copy files directly, add to chezmoi separately.
