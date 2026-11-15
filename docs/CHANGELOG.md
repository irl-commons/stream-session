# Changelog

All changes to the format, the schema and the fixtures. Until v1, a v0
draft can change field names. Each such change is listed here.

## Unreleased

- Docs for implementers: [Join a session](getting-started.md),
  [worked examples](examples.md) with a trace that CI checks, and an
  [FAQ](faq.md). No change to the format.
- The README names the OpenStreamBox Initiative, which started the format.
- Spec 10.9: the last two rows of "Who coordinates what" say "that owner"
  instead of "me". Same meaning.

## v0 draft 1 (November 2026)

- First draft: show ids, the session record, owner state, leases and
  epochs, planned handover, takeover with and without a coordination
  server, orders and "hiding always wins", owners, invites and grants,
  sharing levels and projections, sealing, and the ten bench tests the
  draft still needs.
- `tools/stream_session.py`: validator and sequence checker, standard
  library only, with valid, invalid and sequence fixtures.
- CI on Python 3.10 and 3.14, and a check that shared snapshots are valid
  [stream-status](https://github.com/openstreambox/stream-status).
