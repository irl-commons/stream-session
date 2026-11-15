# stream-session

A small open format that lets every device in a live show agree on which show
it is, who is in it, who decides right now, and what each person lets the
others see.

A live stream rarely runs on one device anymore. You start on the PC at
home, walk out with the phone, and end the night on a backpack box. A friend
joins and your two streams become one show. A guest hops on from their phone
for ten minutes. A mod on another continent hits BRB when a stranger walks
into the shot.

Today each of those pieces keeps its own idea of what is going on. The phone
doesn't know the box took over. A remote app still sends orders to the
device that stopped streaming five minutes ago. Sharing a feed with a friend
means sharing a stream key and hoping nobody sees more than they should.
And when two devices both think they're in charge, nothing decides which
one is right.

stream-session gives all of them one shared record per show, a counter that
goes up every time the device in charge changes, and a few rules everybody
follows. It works with **no server at all**. If you want automatic takeover
or devices in different places, anyone can run a small coordination server,
and nothing else changes.

**Status: v0, a draft.** Nothing here has run on real devices yet; the parts
that need two people's gear in one show are marked. MIT licensed.
Started by the OpenStreamBox Initiative, and open to anyone who builds IRL
streaming tools.

**New here?** [Join a session](docs/getting-started.md) in about ten minutes,
then read the [worked examples](docs/examples.md) and the [FAQ](docs/faq.md).
What changed is in the [changelog](docs/CHANGELOG.md). Questions and doubts
go to [Discussions](https://github.com/openstreambox/stream-session/discussions).
How this fits with the other open standards for IRL streaming:
[openstreambox.org/open-standards.html](https://openstreambox.org/open-standards.html).

## A day in a collab

Kim and Ari stream together on Kim's channel.

1. **Kim goes live from home.** The app next to OBS starts a show: a random
   show id, epoch 1, the PC in charge. Kim's phone and backpack box are
   already paired, so they join as members.
2. **Kim heads out.** Kim taps "Move to phone". The PC offers the show to the
   phone, the phone says it's ready once its own stream is healthy, the PC
   lets go. Epoch 2, the phone in charge. No server was involved.
3. **Ari joins.** Kim's phone shows a QR code. Ari scans it, and Ari's box
   and phone join the show as a co-streamer's devices. Kim's invite lets Ari send a feed through Kim's
   shared ingest. Ari chooses what Kim's side may do with that feed (put it
   on air, hide it) and how much it sees: everything the show needs to run,
   location off. To Kim's mods, Ari shares only "up or down, camera or not,
   and the worst problem".
4. **Something goes wrong.** A mod sees a bystander in Ari's shot and hides
   it. Hiding always works, from anyone allowed, even from a device that's
   a little out of date. Only Ari can show it again.
5. **The box loses signal.** Kim's phone hears nothing from the box for 25
   seconds and asks: "Kim's backpack hasn't answered for 25 s. It may still
   be streaming. Stream from this phone instead?" Kim taps yes. When the box
   comes back, it sees the higher epoch and steps down by itself. Anything
   it hid while cut off stays hidden.
6. **Ari leaves.** Ari's feed closes, the show changes its key, and Ari's
   devices stop getting updates. What Ari already saw can't be taken back,
   and the apps say so.

## How it fits with stream-status and NOALBS

[stream-status](https://github.com/openstreambox/stream-status) answers
"what's wrong with this stream, where, and is it still live?" It's a snapshot
of findings that each device publishes. stream-session doesn't repeat any of
it. It answers the questions around it: which show do these snapshots belong
to, who is in charge, and who may see which snapshot. Each device keeps
publishing stream-status, tagged with the show id. When an owner shares with
another owner, the shared part is a stream-status snapshot, cut down to the
level that owner chose.

[NOALBS](https://github.com/NOALBS/nginx-obs-automatic-low-bitrate-switching)
([docs](https://docs.noalbs.com)) is the open-source tool many IRL streamers
run to switch OBS scenes when the bitrate drops. It reads the stats of the
common ingest servers and is the closest thing the IRL scene has to a shared
contract today. stream-session is meant to sit next to it, not replace it:
NOALBS switches scenes from what arrives at the receiver; stream-session
says which show those feeds belong to and who decides what goes on air. A
switcher like NOALBS could be one of the mixer's members.

## What's here

| Path | What it is |
| --- | --- |
| [`docs/`](docs/getting-started.md) | A ten-minute guide, worked examples, an FAQ and the changelog |
| [`spec/v0.md`](spec/v0.md) | The format: ids, the session record, leases and epochs, handover and takeover, hides, owners and grants, sharing levels, the optional server |
| [`schema/stream-session.v0.schema.json`](schema/stream-session.v0.schema.json) | JSON Schema (2020-12) for every message |
| [`fixtures/`](fixtures/README.md) | Valid messages, invalid ones with one mistake each, and sequences: handover, takeover, split brain, guests, revoking |
| [`tools/stream_session.py`](tools/stream_session.py) | Validator and sequence checker. Python 3.10+, standard library only |
| [`tests/`](tests/test_stream_session.py) | Tests for the tool |
| [`SECURITY.md`](SECURITY.md) | How to report a security problem |

## Try it

```sh
python3 tools/stream_session.py validate my-record.json
python3 tools/stream_session.py sequence my-trace.json
python3 tools/stream_session.py test               # every fixture
python3 -m unittest discover -s tests
```

[Join a session](docs/getting-started.md) walks through a first show step by step.

`validate` checks one message: the schema, the rules the schema can't
express, and a scan for anything that must never appear (stream keys,
tokens, IP addresses, location outside a projection). `sequence` plays a
trace of messages between devices and checks that everyone followed the
rules: nobody took over without a handover, a tap or a witness; nobody kept
giving orders after seeing a newer epoch; no hide got lost; nobody saw more
than they were granted.

## The rules in one screen

- **Ids are random.** Never a serial number, an account, a handle or an
  address. A device gets a new member id in each show, so nobody can follow
  it from show to show.
- **One record, one coordinator.** The device in charge sends the whole
  record every few seconds. A missed message costs nothing.
- **Epochs fence old orders.** Every change of coordinator raises the epoch.
  Orders from an older epoch are refused, except hides.
- **No takeover without a yes.** Without a server, a device takes over only
  after the streamer taps yes, and only after 25 seconds of silence.
- **Hiding always wins.** Privacy, BRB and taking a feed off air apply from
  anyone allowed, in any epoch. Showing more again needs the current
  coordinator.
- **Both sides consent.** The host lets a guest in; the guest lets the host
  put their feed on air. Rights are short-lived and renewed while you stay.
- **You choose what others see.** Minimal, crew or production, per show and
  per person. Location is off until you turn it on.
- **Secrets never travel.** No stream key, token or password appears in any
  message, at any level.

## What still needs a real test

The spec lists ten bench tests (section 19). The ones that need two people's
devices in one show: a guest joining by QR code and being removed, a collab
on one shared ingest with different sharing levels, hiding across owners,
and a coordination server between two owners on different mobile networks.
Until those have run, v0 stays a draft.

## Prior art

Borrowed on purpose, and credited in the spec: stream-status and NOALBS;
Raft's terms and stepping down; Chubby's lock-delay and fencing; etcd and
NATS leases; NMOS IS-04 and IS-07 heartbeats; OAuth scopes, Biscuit and
macaroons for narrowable rights; LiveKit's short-lived grants; IRLToolkit's
two-sided ingest sharing; W3C Trace Context for the id shape.

## License

[MIT](LICENSE).
