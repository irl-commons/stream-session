# Security

Please report security problems privately through GitHub: open the
**Security** tab of this repository and choose **Report a vulnerability**.
Don't open a public issue for them.

What counts here:

- anything in the format or its rules that would let someone take over a
  show without a handover, the streamer's tap or a witness;
- anything that would let a hide be undone by someone who may not show more,
  or by an old coordinator;
- anything that would let an owner, a mixer or a coordination server see more
  than the owner granted, or keep seeing after a removal;
- anything that would push secrets or private data (stream keys, tokens,
  addresses, names, location) into a message;
- the validator or sequence checker crashing, hanging or misbehaving on
  crafted input.

This repository holds a specification and a small tool. It runs no service.
