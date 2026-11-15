# Join a session

This guide is for people who make an IRL streaming app, an encoder box, a
companion app or a hub. In about ten minutes you go through what a device
does in a stream-session show: start a show, follow the device in charge,
send a BRB, and hand the show to another device. At the end you check a
trace of your messages with the sequence checker.

You need Python 3.10 or newer. The tools use only the standard library. Your
own code can be in any language: every message is JSON.

This guide covers one streamer with their own devices. Shows with guests
and co-streamers use the same steps, plus invites and grants (spec
section 10).

## 1. Get the tools

```sh
git clone https://github.com/irl-commons/stream-session
cd stream-session
python3 tools/stream_session.py test
```

## 2. Learn four words

- A **show** is one stream, from Go live to Ended. Its id is the `session`.
- A **member** is one device in that show.
- The **coordinator** is the one member in charge. It sends the shared
  **record** of the show to everyone.
- The **epoch** is a counter. It goes up by one every time a different
  device takes charge.

## 3. Start a show

The first device to go live makes the show's id. Each device makes its own
member id when it joins. All ids are random, and none is taken from a
device name, an account or an address:

```python
import secrets
session = secrets.token_hex(16)   # the show: 32 hex characters
owner = secrets.token_hex(8)      # the streamer, in this show only
member = secrets.token_hex(8)     # this device, in this show only
feed = secrets.token_hex(8)       # this device's camera feed
```

Then it sends its first record at epoch 1, with `claimed: "start"`. See
[`examples/first-record.json`](examples/first-record.json): the PC is the
coordinator, the phone and a companion app are members, and the PC carries
the one feed.

```sh
python3 tools/stream_session.py validate docs/examples/first-record.json
```

The coordinator sends the **whole record** when something changes, and at
least every 5 seconds. Each send renews its lease. Raise `seq` for every
send, and raise `version` for every decision.

## 4. Follow the coordinator

If your device is a member, it does three things with each record:

1. **Replace your copy.** Never merge. A missed record costs nothing.
2. **Start a timer on your own clock.** The lease is good for
   `valid_for_ms` (15 seconds by default) after you received it. When it
   runs out, show "coordinator unknown". Never compare the sender's clock
   with yours.
3. **Check the epoch.** Adopt a higher epoch. Refuse records and orders
   from a lower one, except hides (step 5).

## 5. Send a BRB

Any member with `show.hide` may ask for BRB. It sends an `order` to the
coordinator, with the epoch and the `version` it last saw:

```json
{ "format": "stream-session", "v": 0, "type": "order",
  "session": "4bf92f3577b34da6a3ce929d0e0e4736",
  "scope": "show", "epoch": 1, "against": 1,
  "action": "brb_on", "by": "a4a4b5b5c6c6d7d7" }
```

Hides (`brb_on`, `off_air`, `privacy_on`, `cancel_countdown`) **always
apply**, from any epoch. Showing more (`brb_off`, `on_air`, `go_live`) only
applies if the order names the current epoch and version. So a device with
an old picture of the show can always hide, but it can never show more.

The coordinator's next record lists the hide in `hides`, and
`output.showing` becomes `cover`. The output stays `live`: viewers see the
BRB screen. Apps should say "live, showing BRB", never "offline".

## 6. Hand the show to another device

Kim walks out, and the phone should take over from the PC. It takes four
messages, and no server:

1. The PC sends `transfer` to the phone, for epoch 2.
2. The phone sends `ready` once its own stream is healthy.
3. The PC sends `handed` and stops giving orders.
4. The phone sends its first record at epoch 2, with `claimed: "transfer"`,
   and keeps every hide that was in force.

If `ready` never comes, nothing changes: the PC stays in charge. There is
no moment when nobody, or two devices, are in charge.

## 7. Tag your stream-status snapshots

If your device also sends [stream-status](https://github.com/irl-commons/stream-status)
snapshots, set their `session_id` to the show's `session`. A reader can
then group the snapshots of one show from several devices.

## 8. Check a whole trace

[`examples/solo-brb-handover.json`](examples/solo-brb-handover.json) puts
steps 3 to 6 together: the PC starts the show, the companion app sends BRB,
the show moves to the phone with the BRB kept, and an old order from the PC
to end BRB is refused.

```sh
python3 tools/stream_session.py sequence docs/examples/solo-brb-handover.json
```

You should see `follows the rules`. Record what your own devices send in
the same shape, and the checker tells you which rule a step breaks. Try it:
delete the `ready` step from the example, and the checker answers "handed
before the new device was ready".

## What this guide left out

- **When the coordinator goes silent.** Without a server, no device takes
  over by itself. After 25 seconds of silence, a device may ask the
  streamer, and only a yes lets it claim the next epoch (spec 8.2).
- **Other people.** Guests, co-streamers and mods join with invites and
  grants, and each person chooses how much the others see (spec 10 and 11).
- **The optional server**, for automatic takeover and devices in different
  places (spec 13).

The [worked examples](examples.md) walk through these with the fixtures.

## Next

- [Worked examples](examples.md)
- [FAQ](faq.md)
- [The full spec](../spec/v0.md)
- Questions or doubts: [Discussions](https://github.com/irl-commons/stream-session/discussions).
