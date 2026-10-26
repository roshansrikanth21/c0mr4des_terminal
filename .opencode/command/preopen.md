---
description: Pre-open check - is the desk fit to trade today?
---

Run the `desk-preopen` skill.

```powershell
.\.venv\Scripts\python.exe scripts\desk.py preopen
```

If the API is not reachable, retry with `--ssh` (host/key come from `desk.local.json`).

Report only: verdict (clear / clear with warnings / blocked), the lines that matter,
and the one next action. Do not change settings, restart anything or place orders.
