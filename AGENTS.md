# Working in this repo

Two agents work this repo at the same time, in the same folder: Claude Code and OpenCode. The owner is Roshan.

**Before any edit, read `MAILBOX.md` and run `git status` and `git pull --ff-only`.** There is no direct agent chat; the mailbox is the channel.

1. **Claim first.** Append your name, the time and the paths to the `MAILBOX.md` log. If the other agent claims a path, leave a note instead of editing it.
2. **Stage explicit paths only.** Never `git add -A` or `git commit -a`. The tree may hold the other agent's unfinished work.
3. **Never rewrite history.** No `--amend`, `rebase` or `reset --hard`.
4. **Small commits, tests green, pushed to `lean-core`,** then log the commit hash and release your claim. Never push to `main`.
5. **Owner decisions need the owner's words.** Before recording an "owner decision", quote the exact message in `MAILBOX.md`. If the owner disputes a recorded decision, the owner wins.
6. **Don't change a live strategy rule without the owner's explicit yes.** That covers entries, exits, gates and which strategies are on. The go/no-go paper record is only valid if the rules hold still; log any approved change with its date.
7. **Deploy one at a time.** Check the mailbox first, and log the deployed commit. `LIVE_TRADING` stays false.
8. **No secrets** in commits, the mailbox or chat.
