# 2026-10-29 Calendar and customer editor

- Shared month presentation for purchases, parts closing, vehicle inventory and dispatch. Domain requests and records remain separate.
- Dispatch schedule/history combined; monthly actual count excludes VOID and retains historical RETURN dispatches. Month-bounded query batches adjustments.
- Customer autocomplete groups same-name records without merging identities. Editor rejects duplicate registration, preserves request idempotency and cancels stale suggestions.
- Existing customer permissions retained. User authorized grants to the four other active administrators; apply through audited grant function during deployment. Workers unchanged.

Validation: 48 server tests passed before final customer editor guard; final customer privacy suite 7 passed (includes delegated administrator assignment and duplicate rejection). Actual isolated Chrome browser script passed calendar navigation, monthly totals, 390px viewport, leap month, no purchase/value requests from parts, grouped duplicate choices and selection. No Galaxy device verification. No Android/native changes or APK required.

Deployment: commit in managed worktree, SQLite consistent backup + media copy outside Git, preserve environment/keys/queues; fast-forward operating branch, restart identified 8765 server. Apply authorized grants transactionally with audit. Check existing business-row and media hashes. Never copy test DB.
Rollback: revert this code commit on operating branch and restart. Keep current DB/media; do not restore an old DB over subsequent office transactions. Permission reversal, if requested, uses audited revoke, not history deletion.
