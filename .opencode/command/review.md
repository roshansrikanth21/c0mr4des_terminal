---
description: Evening review - trades, honest read, gate, capital test
---

Run the `desk-review` skill.

```powershell
.\.venv\Scripts\python.exe scripts\desk.py review
```

If the API is not reachable, add `--ssh` (host/key come from `desk.local.json`).

Order: today -> trades -> honest read -> gate -> capital test -> experiments -> one
next action. Quote the API numbers; do not reconstruct anything from memory. Read-only.
