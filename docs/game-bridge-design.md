# Game bridge: in-game chat answered by a Claude Code session

Status: proposed
Date: 2026-09-06

## Summary

Let the in-game factoribot chat window be answered by an interactive Claude
Code session instead of the daemon's own API-backed agent loop. The mod already
speaks a simple UDP protocol; the MCP server gains an inbox for that protocol
and two tools, one that long-polls the inbox and one that replies. The session
runs a loop that reads, answers with the existing planner tools, and replies.

This is the "long-poll plus self-notify" pattern from meristem's `feed.read`
applied to a UDP socket. No push transport, no bridge process, no second queue.

Motivation: the calculations already work in a Claude Code session with no
per-token bill. The only missing piece is the copy and paste between the game
and the session.

## Goals

- In-game questions reach the session and answers reach the game with no
  manual copying.
- The mod is unchanged. It sends `{id, query, player}` and drains replies.
- No model API key. The session's own subscription does the thinking.
- The daemon's `serve` command keeps working as a fallback for anyone who
  wants the API-backed bot.
- Messages are never silently lost. A question the session never answers is
  still visible and still gets a reply.

## Non-goals

- Reading the map, placing blueprints, or any new Lua. That is a separate
  feature with its own design.
- Serving more than one answering session per game at a time.
- Making the daemon's agent loop use Claude. Nothing here touches `agent.py`.
- Running unattended. The session has to be open and looping.

## Current state

```
Factorio mod  --UDP {id,query,player}-->  daemon (serve)  --> OpenAI agent loop
              <--UDP {id,text}----------              <-- tools.Toolbox
```

- `mod/control.lua` sends one datagram per question to the daemon port
  (mod setting, default 25001) and polls its own socket every 20 ticks for
  a reply carrying the same `id`. The reply replaces the "…thinking" line.
- "New" sends `{id, reset: true, player}` and expects no reply.
- `daemon/factoribot/server.py` binds the port, runs `run_agent` per packet
  in a thread, and replies to the packet's source address. Replies are capped
  at 60000 bytes to stay inside one datagram.
- `daemon/factoribot/mcp_server.py` exposes the read-only tools over stdio.
  Claude Code starts it from `.mcp.json`; Codex from `.codex/config.toml`.

## Proposed state

```
Factorio mod  --UDP-->  mcp_server inbox (thread, queue)  <--game_read (long-poll)--  Claude Code session
              <--UDP--  mcp_server reply                  <--game_reply-------------  (loop: read, plan, reply)
```

The MCP server owns the port when started with the bridge enabled. The
session is the consumer. The mod cannot tell the difference.

## Components

### Inbox (server side)

A small module, `daemon/factoribot/bridge.py`, holding:

- A UDP socket bound to `127.0.0.1:<port>` and a receiver thread.
- A bounded deque of received messages, each assigned a monotonically
  increasing `seq` on arrival. Fields: `seq`, `id` (the mod's request id),
  `player`, `kind` (`query` or `reset`), `text`, `received_at`, and the
  source address, which is kept server-side and never returned to the tool.
- A `threading.Condition` that the receiver notifies on arrival, so a
  long-poll wakes immediately instead of sleeping in intervals.
- A map from `id` to source address for replies, and a map from `player` to
  the most recent source address as a fallback.
- A janitor that answers any `query` older than a configurable stale
  threshold (default 5 minutes) with a short "no answer from the session"
  reply, so the in-game window never hangs on "…thinking". The message stays
  in the queue for the session to see; only the in-game placeholder is
  released.

Retention is by count, not by ack. The client holds the cursor; the server
keeps the last N messages (default 256) and drops the oldest. A cursor older
than the retained window returns the oldest retained message and a
`gap: true` flag rather than an error.

The inbox is off unless the server is started with `--game-port` or
`FACTORIBOT_GAME_PORT`. When off, the two tools return
`{"error": "bridge_disabled"}` with instructions. When the bind fails, for
example because the daemon or another session already owns the port, the
server still starts and the tools return `{"error": "port_in_use"}`. The
calculators must never depend on the bridge.

### Tools

Both tools live alongside the existing ones in `TOOL_SCHEMAS`, but they are
not read-only and not idempotent, so their MCP annotations differ. They are
also excluded from the daemon's own agent loop and CLI `tool` command: the
daemon must not be able to call them.

`game_read`

- Input: `cursor` (opaque string, optional), `wait` (seconds, optional,
  default 0), `limit` (optional, default 50).
- Output: `messages` (oldest first), `next_cursor`, `has_more`, `gap`.
- With `wait > 0` and nothing newer than `cursor`, the call blocks until a
  message arrives or `wait` elapses, then returns. The server caps `wait`
  at a configured maximum (default 25 seconds) and rejects larger values,
  the same rule as meristem's `MaxFeedWait`. The cap must stay under the
  MCP host's tool timeout; verify against Claude Code's `MCP_TOOL_TIMEOUT`
  before changing it.
- Delivery is at-least-once. The session must treat a repeated `id` as
  already handled.
- Runs in `asyncio.to_thread` like the planner call so the stdio transport
  is never blocked.

`game_reply`

- Input: `id`, `text`.
- Output: `ok`, or `unknown_id` when neither the id nor the player has a
  stored address.
- Sends `{id, text}` to the stored source address, truncating to the same
  60000-byte cap the daemon uses. The mod replaces the placeholder line.
- A second reply to the same id is allowed. The mod ignores it, because the
  pending entry is gone, so it is harmless. This makes retries safe.

There is deliberately no `game_ack` and no server-side "handled" state. The
cursor is the only progress marker, held by the session.

### Session loop

The session runs a recurring prompt, either through the `/loop` skill with
dynamic pacing or through `ScheduleWakeup` directly. Each iteration:

1. Call `game_read` with the last cursor and `wait` at the cap.
2. For each `query`, answer using the planner tools under the same rules as
   the skill: preserve every requested output, resolve names against game
   data, report limitations. Keep per-player context in the conversation.
3. Call `game_reply` for every `query`, including when the answer is "I
   can't model that" or a tool error. Never leave a question unreplied.
4. On `reset`, drop that player's conversational context.
5. Store the cursor and schedule the next wake.

Reply text is for a 560-pixel game panel. Short paragraphs, no markdown
tables, no code fences. The loop prompt states this.

The loop prompt lives in the repo as `skills/factoribot/references/bridge-loop.md`
so it can be pasted, and so the rules travel with the skill.

### Configuration

- `.mcp.json` gains `"env": {"FACTORIBOT_GAME_PORT": "25001"}` for the Claude
  Code entry. The Codex entry stays as it is, so Codex never binds the port.
- `make play` continues to start the daemon and the game. A new target,
  `make play-bridge`, starts the game with `--enable-lua-udp` but not the
  daemon, so the MCP server can own the port.
- Only one process can bind the port. If the daemon is running, the bridge
  reports `port_in_use` and the daemon answers instead. That is the intended
  fallback order.

## Protocol details

Incoming datagrams from the mod, unchanged:

```
{"id": 7, "query": "purple science, AM2", "player": 1}
{"id": 8, "reset": true, "player": 1}
```

Outgoing replies, unchanged:

```
{"id": 7, "text": "..."}
```

The reply must go to the datagram's source `(host, port)`, which is the
game's per-player UDP socket. Factorio only drains a reply on the socket that
sent the question, which is why the address is stored per id.

## Failure modes

| Situation | Behaviour |
|---|---|
| Session not running | Questions queue. Janitor replies after the stale threshold so the panel does not hang. Answered when the session returns if still in the window. |
| Session mid-answer when a second question arrives | Queued. Picked up on the next `game_read`. |
| Long-poll exceeds host timeout | Prevented by the server cap. If the host kills the call anyway, the next read resumes from the same cursor. |
| Server restarted | Queue and cursor are lost. The session's next read with the old cursor gets `gap: true` and an empty page. Acceptable; the mod's pending entries just get the janitor reply. |
| Two sessions both enable the bridge | Second bind fails, tools report `port_in_use`. No split delivery. |
| Reply larger than a datagram | Truncated at 60000 bytes with a marker, same as today. |
| Malformed datagram | Dropped and logged to stderr, never to stdout. |

## Security

- Localhost only. The socket binds `127.0.0.1` and Factorio's UDP is
  localhost-only.
- In-game text is data, not instructions. The server instructions already
  say this for blueprint labels; the loop prompt repeats it for chat. The
  session answers with planner tools only and does not edit files, run
  commands, or change configuration in response to in-game text.
- The bridge tools are not read-only. Their annotations say so, so a host
  that gates non-read-only tools will prompt. That is correct behaviour.
- No addresses, ports, or socket handles are exposed through tool results.

## Testing

Extend `daemon/tests/test_mcp.py` with a fake game: a UDP socket in the test
that plays the mod's role. Cases:

- Send a query, `game_read` returns it, `game_reply` lands on the fake
  socket with the same id.
- `game_read` with `wait` returns within milliseconds of a datagram arriving,
  not at the end of the wait.
- `game_read` with `wait` and no traffic returns an empty page at the cap.
- Cursor resume returns only newer messages. Cursor older than retention
  returns `gap: true`.
- `wait` above the cap is rejected.
- Queue overflow drops oldest and sets `gap` on the next read past it.
- Starting without the port leaves calculators working and bridge tools
  returning `bridge_disabled`.
- Binding an already-bound port reports `port_in_use` and the server still
  serves calculators.
- Janitor replies to a stale query exactly once.
- Reset datagram appears as `kind: reset` and has no address stored for
  reply.

All of this runs with no game and no model, like the existing MCP test.

## Rollout

1. Land `bridge.py`, the two tools, and the tests.
2. Add the env var to `.mcp.json` and the `play-bridge` target.
3. Write the loop prompt and try one in-game session against the README's
   six-output question.
4. Only then decide whether `serve` stays documented as the primary path or
   the fallback.

Estimated size: about 150 lines of server code including the janitor, 100
lines of tests, one Makefile target, one prompt file.

## Open questions

- Claude Code's MCP tool timeout default. The 25 second cap is chosen to be
  safe under the usual defaults; confirm before raising it.
- Whether the loop should batch several queued questions into one answer
  turn or reply to each separately. Separately is simpler and matches the
  one-placeholder-per-question UI.
- Whether the janitor's stale reply should tell the player to open the
  session, or stay generic. Generic is proposed.

## Alternatives considered

- **Anthropic API adapter in the daemon.** Smallest change, but bills per
  token on top of the subscription. Rejected for cost.
- **Claude Agent SDK in the daemon.** Same billing problem; the SDK is
  documented as API-key only.
- **`claude -p` per question from the daemon.** Uses subscription login, but
  every question pays CLI startup, loses conversational context unless
  session ids are threaded through, and gives the daemon a shell-out to
  supervise. Viable fallback if the interactive loop proves annoying.
- **A separate bridge process with SSE or websockets.** This is what Codex
  needed in meristem and it was the fragile part. Stdio MCP cannot receive
  push, so a bridge only moves the long-poll somewhere else.
