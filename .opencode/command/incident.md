---
description: Desk incident - gather facts and name the safe fix
---

Run the `desk-incident` skill with remote facts:

```powershell
.\.venv\Scripts\python.exe scripts\desk.py incident --ssh
```

Read the facts, match the symptom, and follow TRIAGE in order. A restart is an action:
state it and get the owner's yes unless he already said "fix it". Restart at most once;
if it is still broken, read the log instead of restarting again.
