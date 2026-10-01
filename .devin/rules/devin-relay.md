---
trigger: always_on
---

# Devin Relay Mailbox

A second Devin session (CLI over SSH from the user's Quest) runs concurrently
in this workspace. The two sessions coordinate through a mailbox at
`~/devin-relay/`:

- `inbox.md` — messages addressed to you. Check it at session start and
  whenever the user mentions the relay.
- `outbox.md` — write your replies here, appending under a
  `## YYYY-MM-DD HH:MM from:desktop-devin` header.

Append-only: never edit or delete existing messages. See
`~/devin-relay/README.md` for the full protocol.
