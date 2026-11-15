# Worked examples

Each example is a trace: messages between devices, in order, with checks of
what each device should believe at that point. The sequence checker plays
them:

```sh
python3 tools/stream_session.py sequence FILE.json
```

A trace with `"expect": "ok"` must follow every rule. A trace with an
`expect.error` breaks one rule on purpose, and the checker must find it.
Each step can carry a `note` for people. The examples below point to those
files and explain what happens and why.

All names and ids are made up. Kim hosts, Ari co-streams, Jo is a guest and
Mo is a mod.

## 1. BRB, then a handover

[`examples/solo-brb-handover.json`](examples/solo-brb-handover.json)

Kim goes live from the PC. A mod on the companion app hits BRB. Then Kim
moves the show to the phone. Three things to notice:

- The BRB is still in force after the move. The phone's first record keeps
  it, because a new coordinator never drops a hide.
- The output says `live`, showing `cover`, the whole time. Viewers see the
  BRB screen. Nobody went offline.
- After the move, the PC still has its old picture and sends an order to end
  BRB at epoch 1. The phone refuses it. Ending BRB shows more, and showing
  more needs the current epoch.

## 2. The backpack goes silent

Kim streams from the backpack box. Its battery dies.

- [`03-takeover-after-tap`](../fixtures/sequences/03-takeover-after-tap.json):
  the phone waits until the lease (15 s) and the lock-delay (10 s) have run
  out. After 25 s of silence it asks Kim: "The backpack has been silent for
  25 s. Go live from the phone?" Kim taps yes, and the phone claims epoch
  *n*+1 with `claimed: "manual"`. When the box comes back on another modem,
  it sees the higher epoch and steps down by itself.
- [`04-tap-too-early`](../fixtures/sequences/04-tap-too-early.json): the
  phone claims after only 15 s. The checker refuses it, because the
  lock-delay hadn't run out.
- [`05-takeover-without-tap`](../fixtures/sequences/05-takeover-without-tap.json):
  the phone claims without asking Kim. The checker refuses it.

Why so careful? The phone can't tell a dead box from a box that only lost
the phone's Wi-Fi and still streams on its own modems. Only the streamer
can decide that.

## 3. Automatic takeover, with a server

[`06-failover-with-server`](../fixtures/sequences/06-failover-with-server.json)

Kim turned on automatic failover and uses a coordination server. Each record
also reaches the server, sealed, so the server can't read it. When the box
goes silent, the phone asks the server for the next epoch. The server gives
it to exactly one device. No tap is needed, because the server makes sure
there is only one winner.

## 4. Two devices in charge at once

[`09-split-brain-hide-wins`](../fixtures/sequences/09-split-brain-hide-wins.json)

The box and the phone lose each other, but both stay online on cellular.
After 25 s, Kim lets the phone take over, so for a while both think they're
in charge. On the box's side, a mod puts BRB on. When the two sides meet
again:

- the BRB from the old side is kept, because hiding always wins;
- an order from the old side to end BRB is refused;
- Kim ends BRB on the current epoch, and that works.

And the other way round,
[`11-old-coordinator-keeps-going`](../fixtures/sequences/11-old-coordinator-keeps-going.json)
is a box that sees epoch 2 and keeps sending epoch-1 records. The checker
catches it.

## 5. A guest joins, and leaves

[`15-guest-joins-and-is-removed`](../fixtures/sequences/15-guest-joins-and-is-removed.json)

1. Kim's box shows a QR code. The secret token is only in the code. It never
   appears in a message.
2. Jo scans it. Jo's phone proves it has the token without sending it.
3. Kim's side lets Jo in. Jo chooses what Kim's show may do with Jo's feed,
   and how much it sees. Location stays off.
4. Jo's feed goes on air through a guest ingest. Jo never gets Kim's stream
   key.
5. Kim removes Jo. Jo's feed closes, and the show changes its key, so Jo
   can't read later records.

What must not happen:

- [`19-on-air-without-consent`](../fixtures/sequences/19-on-air-without-consent.json):
  Kim puts Jo on air, but Jo never agreed. Refused.
- [`16-removed-but-still-sent`](../fixtures/sequences/16-removed-but-still-sent.json):
  Kim's box keeps sending records to Jo after removing Jo. Refused.
- [`20-location-not-granted`](../fixtures/sequences/20-location-not-granted.json):
  Jo's app sends a place name although Jo left location off. Refused.

These steps need two people's devices to test for real. That test hasn't
run yet (spec section 19).

## 6. A collab with different sharing levels

[`23-collab-levels-and-hides`](../fixtures/sequences/23-collab-levels-and-hides.json)

Kim and Ari stream together on Kim's channel, on one shared ingest.

- Ari shares a lot with Kim (`production`, and the city as location). Kim
  shares less with Ari (`crew`).
- Kim passes "may hide Ari's feed" on to a mod, cut down to `minimal`.
- The mod sees a stranger in Ari's shot and hides it. Kim can't show it
  again. Only Ari can.
- Ari moves the feed from the box to the phone. The show sees the same feed
  with a new carrier.
- Ari withdraws the share. The mod's copy goes with it, and Kim's side takes
  Ari's feed off air.

This one also waits for a real test with two people's gear.
