# Fixtures

`python3 tools/stream_session.py test` runs all of them.

| Folder | Each file | Passes when |
| --- | --- | --- |
| `valid/` | `description`, `message` | the message validates |
| `invalid/` | `description`, `error`, `message` | validation finds exactly one problem, containing `error` |
| `sequences/` | `description`, the cast, `expect`, `steps` | the trace follows the rules (`"expect": "ok"`), or breaks one with an error containing `expect.error` |

All ids are made up. "Kim" hosts, "Ari" co-streams, "Jo" is a guest and "Mo"
helps as a mod.

## Sequences

The cast lists `owners` (alias → id and role), `members` (alias → member id,
owner alias, kind) and `feeds` (alias → feed id). Sequences that use a
coordination server also give its `lookup` key and `witness` timings.

Each step happens at `t`, in milliseconds on one shared clock (every
device's clock runs at the same rate; none is compared with another's
time of day):

- `{ "t", "from", "to", "msg" }`: a member sends a message. `to` is a list of
  member aliases, or `"all"` for every member except the sender and those who
  left. A partition is simply a list that leaves someone out.
- `{ "t", "at", "tap": "take_over", "scope" }`: the streamer says yes on that
  device.
- `{ "t", "at", "expect": { … } }`: that member's view must match. Keys:
  `scope` (default `show`), `epoch`, `holder`, `leads`, `standby`,
  `coordinator_unknown`, `conflict`, `hides`, `applied`, `refused`,
  `moved_to`, `told_unknown`.

`note` fields explain a step for people; the checker ignores them.

Sequences with a `bench` field (`"two-owner"`, `"partition"`) are the paper
form of a test that still has to run on real devices (spec section 19).
