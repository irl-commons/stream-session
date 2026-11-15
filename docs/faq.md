# FAQ

## Does anyone use this yet?

No. stream-session is a v0 draft, and nothing in it has run on real devices
yet. Feedback now is the most useful kind: it's cheap to change things
before anyone depends on them.

## Do I need a server?

No. A show with no server works: a planned handover takes four messages
between two devices, and a takeover after silence happens when the streamer
taps yes. A coordination server only adds two things: automatic takeover,
and passing messages between devices that can't reach each other (for
example on two different mobile networks). Anyone can run one, and it
can't read the show.

## Why doesn't a device take over by itself when the other one goes quiet?

Because it can't tell what happened. A backpack box that lost the phone's
Wi-Fi may still be streaming on its own modems. If the phone took over by
itself, viewers could get two streams at once. So without a server, only
the streamer decides, after 25 seconds of silence.

## Why can anyone hide, even with an old picture of the show?

Because hiding is always safe, and it's often urgent: a stranger walks into
the shot, or the streamer needs a break. Showing more is the risky
direction, so that needs the current coordinator. After a split, every hide
from both sides stays until someone ends it in the current epoch.

## How is this different from stream-status?

[stream-status](https://github.com/irl-commons/stream-status) says what's
wrong with a stream and whether it's still live. stream-session says which
show those snapshots belong to, who is in charge, and who may see what. A
device in a show keeps sending stream-status and tags each snapshot with the
show's `session_id`. stream-session defines no findings of its own.

## Where do pairing and encryption come from?

From the channel you already have between your own devices: your app's
pairing, a paired WebSocket, a remote-control link. This spec doesn't
replace that. It only adds sealing for messages that a third party, such as
a coordination server, passes on.

## Why do ids change for every show?

So nobody can follow a device or a person from show to show. A device gets
a new member id for each show. Only the owner's own devices see the stable
id of a device (its stream-status `source.id`).

## Can a stream key or a password end up in a message?

It must not. No message carries stream keys, tokens, passwords, IP
addresses or serial numbers. The validator rejects fields named like
secrets and values that look like keys, tokens, URLs with credentials, or
IP and email addresses. A guest's ingest credential travels through the
ingest's own API, never in a stream-session message.

## Who decides what a co-streamer or a mod sees?

The person whose things they are. Each owner picks a level for each other
person, per show: `none`, `minimal`, `crew` or `production`. Location is
off at every level until the owner turns it on. Apps should preselect
`minimal` and location off, and ask before sharing anything.

## What still needs a real test?

The spec lists ten tests (section 19). Four of them need two people's
devices in one show: a guest joining by QR code and being removed, a collab
on one shared ingest, hiding across owners, and a coordination server
between two people on different mobile networks. Until those have run, v0
stays a draft.

## How does this fit with NOALBS?

NOALBS switches OBS scenes from what arrives at the receiver.
stream-session says which show those feeds belong to and who decides what
goes on air. A switcher like NOALBS could be one of the show's members.

## Why did the schema's `$id` change?

The first v0 draft used `https://github.com/openstreambox/stream-session/schema/stream-session.v0.schema.json`
as its `$id`. That was a name, not an address you could open, and it tied the
format to one GitHub organisation. Since the move to IRL Commons the `$id` is
`https://irlcommons.org/schemas/stream-session/v0.json`, an address on
irlcommons.org that will serve the schema file. If you pinned the old identifier during its one day, replace it; the
schema is otherwise the same.

## What happens when v1 comes?

Until v1, fields can still change between drafts. Each change gets a line in
the [changelog](CHANGELOG.md) and updated fixtures. From v1 on, changes are
additive only, and the rules for unknown values keep older devices safe.

## Where do I ask, or say what's missing?

In [Discussions](https://github.com/irl-commons/stream-session/discussions).
If you'd rather not post in public, write to hello@irlcommons.org or ask
[on Discord](https://discord.gg/3B9b9n9N6).
