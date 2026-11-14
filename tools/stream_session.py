#!/usr/bin/env python3
"""stream-session v0: validator and sequence checker.

Usage:
  stream_session.py validate FILE...    check messages (JSON files)
  stream_session.py sequence FILE...    run sequence fixtures
  stream_session.py test                run every fixture

Python 3.10+, standard library only. The schema is checked by a small
built-in JSON Schema 2020-12 evaluator that covers the keywords the
stream-session schema uses; the tests compare it with the `jsonschema`
package when that is installed.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys
from typing import Any, Iterator

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "schema" / "stream-session.v0.schema.json"
FIXTURES = ROOT / "fixtures"

LEVELS = ["none", "minimal", "crew", "production"]
LOCATION_MODES = ["off", "area", "live"]
HIDE_ACTIONS = {"brb_on", "off_air", "privacy_on", "cancel_countdown"}
SHOW_ACTIONS = {"brb_on", "brb_off", "off_air", "on_air", "cancel_countdown", "go_live", "end"}
OWNER_ACTIONS = {"privacy_on", "privacy_off", "move_feed", "end_feed"}
RELEASES = {"brb_off": "brb", "on_air": "off_air", "privacy_off": "privacy"}
HIDE_KIND = {"brb_on": "brb", "off_air": "off_air", "privacy_on": "privacy"}


# --------------------------------------------------------------------------
# Loading

def load_json(path: pathlib.Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


_SCHEMA: dict | None = None


def schema() -> dict:
    global _SCHEMA
    if _SCHEMA is None:
        _SCHEMA = load_json(SCHEMA_PATH)
    return _SCHEMA


# --------------------------------------------------------------------------
# A small JSON Schema 2020-12 evaluator (the keywords this schema uses)

def _type_ok(value: Any, name: str) -> bool:
    if name == "object":
        return isinstance(value, dict)
    if name == "array":
        return isinstance(value, list)
    if name == "string":
        return isinstance(value, str)
    if name == "boolean":
        return isinstance(value, bool)
    if name == "null":
        return value is None
    if name == "integer":
        if isinstance(value, bool):
            return False
        return isinstance(value, int) or (isinstance(value, float) and value.is_integer())
    if name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    raise ValueError(f"unsupported type {name}")


def _equal(a: Any, b: Any) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    return a == b


def _resolve(ref: str) -> dict:
    if not ref.startswith("#/"):
        raise ValueError(f"only local $ref supported: {ref}")
    node: Any = schema()
    for part in ref[2:].split("/"):
        node = node[part]
    return node


SUPPORTED = {
    "$schema", "$id", "$ref", "title", "description", "$defs", "type", "const",
    "enum", "required", "properties", "patternProperties", "additionalProperties",
    "items", "minItems", "maxItems", "uniqueItems", "minLength", "maxLength",
    "pattern", "minimum", "maximum", "exclusiveMinimum", "allOf", "anyOf",
    "oneOf", "not", "if", "then", "else",
}


def schema_iter(value: Any, node: Any, path: str = "") -> Iterator[str]:
    """Yield one message per violation, prefixed with the instance path."""
    if node is True:
        return
    if node is False:
        yield f"{path or '(root)'}: not allowed"
        return
    unknown = set(node) - SUPPORTED
    if unknown:
        raise ValueError(f"unsupported schema keywords {sorted(unknown)}")
    where = path or "(root)"
    if "$ref" in node:
        yield from schema_iter(value, _resolve(node["$ref"]), path)
    if "type" in node:
        names = node["type"] if isinstance(node["type"], list) else [node["type"]]
        if not any(_type_ok(value, n) for n in names):
            yield f"{where}: {json.dumps(value)[:60]} is not of type {'/'.join(names)}"
            return
    if "const" in node and not _equal(value, node["const"]):
        yield f"{where}: {json.dumps(value)[:60]} is not {json.dumps(node['const'])}"
    if "enum" in node and not any(_equal(value, e) for e in node["enum"]):
        yield f"{where}: {json.dumps(value)[:60]} is not one of {node['enum']}"
    if isinstance(value, str):
        if "minLength" in node and len(value) < node["minLength"]:
            yield f"{where}: shorter than {node['minLength']}"
        if "maxLength" in node and len(value) > node["maxLength"]:
            yield f"{where}: longer than {node['maxLength']}"
        if "pattern" in node and not re.search(node["pattern"], value):
            yield f"{where}: {json.dumps(value)[:60]} does not match {node['pattern']}"
    if _type_ok(value, "number"):
        if "minimum" in node and value < node["minimum"]:
            yield f"{where}: {value} is less than {node['minimum']}"
        if "maximum" in node and value > node["maximum"]:
            yield f"{where}: {value} is more than {node['maximum']}"
        if "exclusiveMinimum" in node and value <= node["exclusiveMinimum"]:
            yield f"{where}: {value} is not more than {node['exclusiveMinimum']}"
    if isinstance(value, list):
        if "minItems" in node and len(value) < node["minItems"]:
            yield f"{where}: fewer than {node['minItems']} items"
        if "maxItems" in node and len(value) > node["maxItems"]:
            yield f"{where}: more than {node['maxItems']} items"
        if node.get("uniqueItems"):
            seen = []
            for item in value:
                if any(_equal(item, s) for s in seen):
                    yield f"{where}: has non-unique items"
                    break
                seen.append(item)
        if "items" in node:
            for index, item in enumerate(value):
                yield from schema_iter(item, node["items"], f"{path}/{index}")
    if isinstance(value, dict):
        for name in node.get("required", []):
            if name not in value:
                yield f"{where}: '{name}' is a required property"
        props = node.get("properties", {})
        patterns = node.get("patternProperties", {})
        for key, item in value.items():
            matched = False
            if key in props:
                matched = True
                yield from schema_iter(item, props[key], f"{path}/{key}")
            for pattern, sub in patterns.items():
                if re.search(pattern, key):
                    matched = True
                    yield from schema_iter(item, sub, f"{path}/{key}")
            if not matched and "additionalProperties" in node:
                extra = node["additionalProperties"]
                if extra is False:
                    yield f"{where}: additional property '{key}' is not allowed"
                else:
                    yield from schema_iter(item, extra, f"{path}/{key}")
    for sub in node.get("allOf", []):
        yield from schema_iter(value, sub, path)
    if "anyOf" in node:
        if not any(not list(schema_iter(value, sub, path)) for sub in node["anyOf"]):
            yield f"{where}: matches none of the allowed shapes"
    if "oneOf" in node:
        passing = sum(1 for sub in node["oneOf"] if not list(schema_iter(value, sub, path)))
        if passing != 1:
            yield f"{where}: must match exactly one allowed shape ({passing} matched)"
    if "not" in node and not list(schema_iter(value, node["not"], path)):
        yield f"{where}: matches a shape that is not allowed"
    if "if" in node:
        if not list(schema_iter(value, node["if"], path)):
            if "then" in node:
                yield from schema_iter(value, node["then"], path)
        elif "else" in node:
            yield from schema_iter(value, node["else"], path)


def schema_errors(message: Any) -> list[str]:
    return [f"schema: {e}" for e in schema_iter(message, schema())]


# --------------------------------------------------------------------------
# Privacy scan: secrets, network addresses and location outside a projection

SECRET_KEY = re.compile(
    r"(?i)(^|_)(stream_?key|passphrase|passwd|password|secret|token|access_token|"
    r"refresh_token|api_?key|pin|puk|credentials?|cookie|authorization|bearer)$"
)
SECRET_VALUE = [
    (re.compile(r"(?i)\brtmps?://"), "an RTMP URL"),
    (re.compile(r"(?i)\bsrt://"), "an SRT URL"),
    (re.compile(r"(?i)(passphrase|streamid|stream_key|key)="), "a credential parameter"),
    (re.compile(r"\blive_[0-9]{3,}_[A-Za-z0-9]{10,}"), "a platform stream key"),
    (re.compile(r"\bsst0_[A-Za-z0-9_-]{16,}"), "an invite token"),
    (re.compile(r"(?i)\boauth:[a-z0-9]{16,}"), "an OAuth token"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ"), "a JSON Web Token"),
    (re.compile(r"(?<![0-9.])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![0-9.])"), "an IPv4 address"),
    (re.compile(r"(?i)(?<![0-9a-z:])(?:[0-9a-f]{1,4}:){7}[0-9a-f]{1,4}(?![0-9a-z:])"), "an IPv6 address"),
    (re.compile(r"(?i)(?<![0-9a-z:])[0-9a-f]{1,4}(?::[0-9a-f]{1,4})*::(?:[0-9a-f]{1,4}(?::[0-9a-f]{1,4})*)?(?![0-9a-z:])"), "an IPv6 address"),
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "an email address"),
]
LOCATION_KEY = re.compile(
    r"(?i)(^|_)(lat|lng|lon|latitude|longitude|gps|geo|coords?|location|position|cell_?id)$"
)
LOCATION_SETTING_KEYS = {"location", "shares_location"}
OPAQUE_FIELDS = {"ct", "nonce", "proof"}


def privacy_errors(node: Any, path: str = "", kind: str | None = None, inside: bool = False) -> list[str]:
    """Secrets never; network addresses never; location only in a projection's location."""
    errors: list[str] = []
    if isinstance(node, dict):
        if kind is None and isinstance(node.get("type"), str):
            kind = node["type"]
        for key, value in node.items():
            here = f"{path}/{key}"
            if SECRET_KEY.search(key):
                errors.append(f"privacy: {here}: a field named like a secret ('{key}') is never allowed")
            located = inside or (here == "/location" and kind == "projection")
            setting = key in LOCATION_SETTING_KEYS and value in LOCATION_MODES
            if LOCATION_KEY.search(key) and not located and not setting:
                errors.append(f"privacy: {here}: location outside a projection's location field")
            if key in OPAQUE_FIELDS:
                continue
            errors.extend(privacy_errors(value, here, kind, located))
    elif isinstance(node, list):
        for index, item in enumerate(node):
            errors.extend(privacy_errors(item, f"{path}/{index}", kind, inside))
    elif isinstance(node, str):
        for pattern, what in SECRET_VALUE:
            if pattern.search(node):
                errors.append(f"privacy: {path}: looks like {what}")
    return errors


# --------------------------------------------------------------------------
# Checks the schema can't express

def _dupes(items: list, key: str) -> list[str]:
    seen, dupes = set(), []
    for item in items:
        if item[key] in seen:
            dupes.append(item[key])
        seen.add(item[key])
    return dupes


def _rank(order: list[str], value: str) -> int:
    return order.index(value)


def check_record(m: dict) -> list[str]:
    errors = []
    for field, key in (("owners", "owner"), ("members", "member"), ("feeds", "feed"), ("ingests", "ingest")):
        for dupe in _dupes(m.get(field, []), key):
            errors.append(f"record: duplicate {key} {dupe}")
    owners = {o["owner"]: o for o in m["owners"]}
    members = {x["member"]: x for x in m["members"]}
    ingests = {i["ingest"]: i for i in m.get("ingests", [])}
    feeds = {f["feed"]: f for f in m["feeds"]}
    hosts = [o for o in m["owners"] if o["role"] == "host"]
    if len(hosts) != 1:
        errors.append(f"record: a show has exactly one host owner, found {len(hosts)}")
    host = hosts[0]["owner"] if hosts else None
    for x in m["members"]:
        if x["owner"] is None:
            if x["kind"] != "server":
                errors.append(f"record: member {x['member']} has no owner but isn't a server")
            if x["caps"]:
                errors.append(f"record: server {x['member']} run by nobody in the show can't hold show rights")
        elif x["owner"] not in owners:
            errors.append(f"record: member {x['member']} names unknown owner {x['owner']}")
        elif owners[x["owner"]]["state"] != "joined" and x["state"] == "joined":
            errors.append(f"record: member {x['member']} is joined but its owner has {owners[x['owner']]['state']}")
        if "serves" in x and x["kind"] != "server":
            errors.append(f"record: only a server member serves as witness or relay ({x['member']})")
        if x["owner"] is not None and x["owner"] != host and x.get("grant") is None and x["state"] == "joined":
            errors.append(f"record: member {x['member']} of another owner joined without a grant")
    holder = members.get(m["lease"]["holder"])
    if holder is None:
        errors.append("record: lease holder is not a member")
    else:
        if holder["state"] != "joined":
            errors.append("record: lease holder is not joined")
        if "show.mix" not in holder["caps"]:
            errors.append("record: lease holder lacks show.mix")
    for f in m["feeds"]:
        if f["owner"] not in owners:
            errors.append(f"record: feed {f['feed']} names unknown owner")
            continue
        if f["state"] == "closed":
            if f["on_air"]:
                errors.append(f"record: closed feed {f['feed']} is on air")
            if f["carrier"] is not None:
                errors.append(f"record: closed feed {f['feed']} still names a carrier")
        if owners[f["owner"]]["state"] != "joined" and f["state"] == "open":
            errors.append(f"record: feed {f['feed']} is open but its owner has {owners[f['owner']]['state']}")
        if f["carrier"] is not None:
            carrier = members.get(f["carrier"])
            if carrier is None:
                errors.append(f"record: feed {f['feed']} carrier is not a member")
            elif carrier["owner"] != f["owner"]:
                errors.append(f"record: feed {f['feed']} is carried by another owner's device")
            elif carrier["state"] != "joined":
                errors.append(f"record: feed {f['feed']} carrier has left")
        if "ingest" in f and f["ingest"] not in ingests:
            errors.append(f"record: feed {f['feed']} names an ingest the record doesn't list")
        if f["on_air"] and m["output"]["state"] == "not_live":
            errors.append(f"record: feed {f['feed']} is on air while the show is not live")
    for i in m.get("ingests", []):
        if i["owner"] not in owners:
            errors.append(f"record: ingest {i['ingest']} names unknown owner")
        for fid in i.get("feeds", []):
            if fid not in feeds:
                errors.append(f"record: ingest {i['ingest']} lists unknown feed {fid}")
            elif not i["shared"] and feeds[fid]["owner"] != i["owner"]:
                errors.append(f"record: ingest {i['ingest']} is not shared but carries another owner's feed")
    for index, h in enumerate(m.get("hides", [])):
        if h["by"] not in members:
            errors.append(f"record: hides/{index} by unknown member")
        if "feed" in h and h["feed"] not in feeds:
            errors.append(f"record: hides/{index} names unknown feed")
        if h["kind"] == "off_air" and h.get("feed") in feeds and feeds[h["feed"]]["on_air"]:
            errors.append(f"record: feed {h['feed']} is taken off air and on air at once")
        if h["kind"] == "brb" and m["output"]["showing"] == "program":
            errors.append("record: BRB is on but the output says it shows the program")
    return errors


def check_owner_state(m: dict) -> list[str]:
    errors = []
    if m["lease"]["scope"] != f"owner:{m['owner']}":
        errors.append("owner_state: lease scope must be this owner's scope")
    devices = {d["member"] for d in m["devices"]}
    for dupe in _dupes(m["devices"], "member"):
        errors.append(f"owner_state: duplicate device {dupe}")
    for dupe in _dupes(m["feeds"], "feed"):
        errors.append(f"owner_state: duplicate feed {dupe}")
    if m["lease"]["holder"] not in devices:
        errors.append("owner_state: lease holder is not one of the owner's devices")
    for f in m["feeds"]:
        if f["carrier"] is not None and f["carrier"] not in devices:
            errors.append(f"owner_state: feed {f['feed']} carrier is not the owner's device")
        if f["state"] == "closed" and f["carrier"] is not None:
            errors.append(f"owner_state: closed feed {f['feed']} still names a carrier")
    return errors


def check_offer(where: str, o: dict) -> list[str]:
    errors = []
    if o["level"] == "none" and o["location"] != "off":
        errors.append(f"{where}: level none can't share location")
    if o.get("ingests") and "ingest.use" not in o["caps"]:
        errors.append(f"{where}: names ingests without ingest.use")
    return errors


def check_projection(m: dict) -> list[str]:
    errors = []
    if m["from"] == m["to"]:
        errors.append("projection: an owner doesn't project to itself")
    for dupe in _dupes(m["feeds"], "feed"):
        errors.append(f"projection: duplicate feed {dupe}")
    if "location" in m:
        mode = m["location"]["mode"]
        if m["shares_location"] == "off":
            errors.append("projection: carries a location while shares_location is off")
        elif _rank(LOCATION_MODES, mode) > _rank(LOCATION_MODES, m["shares_location"]):
            errors.append(f"projection: location mode {mode} is more than shares_location allows")
    for fi, feed in enumerate(m["feeds"]):
        for si, snap in enumerate(feed.get("status", [])):
            where = f"projection: feeds/{fi}/status/{si}"
            if snap.get("session_id") != m["session"]:
                errors.append(f"{where}: session_id must be this session")
            if m["level"] == "crew" and snap.get("checked"):
                errors.append(f"{where}: crew level carries findings only, checked must be empty")
            for find in snap.get("findings", []) + snap.get("checked", []):
                if isinstance(find, dict) and "label" in find.get("subject", {}):
                    errors.append(f"{where}: subject labels never cross owners")
                    break
    return errors


def check_order(m: dict) -> list[str]:
    errors = []
    action = m["action"]
    if action in SHOW_ACTIONS and m["scope"] != "show":
        errors.append(f"order: {action} is decided by the show, scope must be show")
    if action in OWNER_ACTIONS and not m["scope"].startswith("owner:"):
        errors.append(f"order: {action} is decided by the feed's owner, scope must be owner:<id>")
    return errors


def semantic_errors(m: dict) -> list[str]:
    kind = m["type"]
    if kind == "record":
        return check_record(m)
    if kind == "owner_state":
        return check_owner_state(m)
    if kind == "invite":
        return check_offer("invite", m["offers"])
    if kind == "grant":
        errors = check_offer("grant", m)
        if m["issuer"] == m["holder"]:
            errors.append("grant: issuer and holder are the same owner")
        return errors
    if kind == "projection":
        return check_projection(m)
    if kind == "order":
        return check_order(m)
    if kind in ("transfer", "handed") and m["from"] == m["to"]:
        return [f"{kind}: from and to are the same member"]
    return []


def validate(message: Any) -> list[str]:
    errors = schema_errors(message)
    if errors:
        return errors
    return privacy_errors(message) + semantic_errors(message)


# --------------------------------------------------------------------------
# Sequence checker: a reference model of members following the rules

class SequenceError(Exception):
    pass


class View:
    def __init__(self) -> None:
        self.epoch: dict[str, int] = {}
        self.holder: dict[str, str] = {}
        self.rx_t: dict[str, int] = {}
        self.lease: dict[str, dict] = {}
        self.leads: dict[str, int] = {}
        self.standby: dict[str, bool] = {}
        self.conflict: dict[str, bool] = {}
        self.handed: dict[str, int] = {}
        self.version: dict[str, int] = {}
        self.min_version: dict[str, int] = {}
        self.must_include: dict[str, set] = {}
        self.hides: set = set()
        self.sticky: set = set()
        self.applied: list[str] = []
        self.refused: list[str] = []
        self.taps: list[tuple[str, int]] = []
        self.moved_to: dict[str, str] = {}
        self.told_unknown = False
        self.left = False


class Sequence:
    def __init__(self, fixture: dict) -> None:
        self._owners_raw = fixture["owners"]
        self.session = fixture["session"]
        self.lookup = fixture.get("lookup")
        self.witness_cfg = fixture.get("witness", {"valid_for_ms": 15000, "lock_delay_ms": 10000})
        self.owner_alias = {k: v["id"] for k, v in fixture["owners"].items()}
        self.owner_of_id = {v: k for k, v in self.owner_alias.items()}
        self.members = fixture["members"]
        self.member_id = {k: v["id"] for k, v in self.members.items()}
        self.alias = {v: k for k, v in self.member_id.items()}
        self.feed_id = fixture.get("feeds", {})
        self.feed_alias = {v: k for k, v in self.feed_id.items()}
        self.views = {k: View() for k in self.members}
        self.holders: dict[tuple[str, int], tuple[str, str]] = {}
        self.pending: dict[tuple[str, int], dict] = {}
        self.claims: dict[tuple[str, int], set] = {}
        self.granted: dict[tuple[str, int], str] = {}
        self.witness: dict[str, dict] = {}
        self.grants: dict[str, dict] = {}
        self.invites: dict[str, dict] = {}
        self.joins: dict[str, list] = {}
        self.removed_owners: set = set()
        self.left_members: set = set()
        self.rotation_needed_above: int | None = None
        self.key_gen = 0
        self.latest_record: dict | None = None
        self.auto_failover: dict[str, bool] = {}
        self.sources: dict[str, str] = {}
        self.released: set = set()
        self.joined: set = set()

    # -- helpers ----------------------------------------------------------
    def owner(self, alias: str) -> str | None:
        owner = self.members[alias].get("owner")
        return self.owner_alias[owner] if owner else None

    def host(self) -> str:
        for alias, owner in self.owner_alias.items():
            if self.fixture_owner_role(alias) == "host":
                return owner
        raise SequenceError("fixture has no host owner")

    def fixture_owner_role(self, alias: str) -> str:
        return self._owners_raw[alias]["role"]

    def grant_live(self, g: dict, t: int) -> bool:
        """Live: not revoked, renewed within its ttl, and so is every parent."""
        while g is not None:
            if g["revoked_t"] is not None or t - g["renewed_t"] > g["ttl_ms"]:
                return False
            g = self.grants.get(g["parent"]) if g["parent"] else None
        return True

    def root_issuer(self, g: dict) -> str:
        while g["parent"]:
            g = self.grants[g["parent"]]
        return g["issuer"]

    def live_caps(self, about: str, holder: str, t: int) -> set:
        """Caps the holder has over `about`'s things, through direct or passed-on grants."""
        caps: set = set()
        for g in self.grants.values():
            if g["holder"] == holder and self.root_issuer(g) == about and self.grant_live(g, t):
                caps |= set(g["caps"])
        return caps

    def active_grant(self, about: str, holder: str, cap: str | None, t: int) -> bool:
        if cap is None:
            return any(g["holder"] == holder and self.root_issuer(g) == about and self.grant_live(g, t)
                       for g in self.grants.values())
        return cap in self.live_caps(about, holder, t)

    def caps_of(self, member_id: str) -> set:
        if not self.latest_record:
            return set()
        for x in self.latest_record["members"]:
            if x["member"] == member_id and x["state"] == "joined":
                return set(x["caps"])
        return set()

    def feed_owner(self, feed_id: str) -> str | None:
        if self.latest_record:
            for f in self.latest_record["feeds"]:
                if f["feed"] == feed_id:
                    return f["owner"]
        return None

    def recipients(self, step: dict, sender: str) -> list[str]:
        to = step.get("to", "all")
        if to == "all":
            return [a for a in self.members if a != sender and not self.views[a].left]
        return list(to)

    def label(self, action: str, feed: str | None) -> str:
        return action if feed is None else f"{action}:{self.feed_alias.get(feed, feed)}"

    # -- leases -----------------------------------------------------------
    def lease_message(self, t: int, sender: str, m: dict, recipients: list[str]) -> None:
        lease = m["lease"]
        scope, epoch = lease["scope"], lease["epoch"]
        sid = self.member_id[sender]
        view = self.views[sender]
        if lease["holder"] != sid:
            raise SequenceError("lease holder is not the sender")
        if m["type"] == "owner_state" and scope != f"owner:{self.owner(sender)}":
            raise SequenceError("owner_state for another owner's scope")
        if view.epoch.get(scope, 0) > epoch:
            raise SequenceError(f"kept coordinating {scope} after seeing a higher epoch")
        if view.handed.get(scope) == epoch:
            raise SequenceError(f"kept coordinating {scope} after handing it over")
        key = (scope, epoch)
        if view.leads.get(scope) != epoch:
            self.justify(t, sender, lease)
            existing = self.holders.get(key)
            if existing and existing[0] != sid:
                if not (existing[1] == "manual" and lease["claimed"] == "manual"):
                    raise SequenceError(f"two holders for {scope} epoch {epoch}")
            else:
                self.holders[key] = (sid, lease["claimed"])
            view.leads[scope] = epoch
            view.standby[scope] = False
            view.min_version[scope] = 0
            view.must_include.setdefault(scope, set())
        if m["version"] < view.version.get(scope, 0) and view.epoch.get(scope) == epoch:
            raise SequenceError("version went backwards within an epoch")
        if m["version"] < view.min_version.get(scope, 0):
            raise SequenceError("applied a decision without raising the version")
        view.epoch[scope], view.holder[scope], view.lease[scope] = epoch, sid, lease
        view.version[scope] = m["version"]
        view.rx_t[scope] = t
        if m["type"] == "record":
            self.check_record_rules(t, sender, m, recipients)
        else:
            self.check_owner_rules(sender, m)
        for r in recipients:
            self.deliver_lease(t, r, m)

    def justify(self, t: int, sender: str, lease: dict) -> None:
        scope, epoch, claimed = lease["scope"], lease["epoch"], lease["claimed"]
        sid = self.member_id[sender]
        view = self.views[sender]
        known = view.epoch.get(scope, 0)
        if claimed == "start":
            if epoch != 1 or any(k[0] == scope for k in self.holders):
                raise SequenceError("start claimed for a scope that already started")
            return
        if epoch != known + 1:
            raise SequenceError(f"claimed epoch {epoch} but last saw {known}: skipped an epoch")
        if claimed == "transfer":
            p = self.pending.get((scope, epoch))
            if not p or p["to"] != sid or not p["handed"]:
                raise SequenceError("transfer epoch without a completed handover")
        elif claimed == "manual":
            old = view.lease.get(scope)
            taps = [tt for s, tt in view.taps if s == scope]
            if not taps:
                raise SequenceError("manual claim without the streamer's tap")
            if old is None or scope not in view.rx_t:
                raise SequenceError("manual claim with no lease to take over")
            wait = old["valid_for_ms"] + old["lock_delay_ms"]
            if max(taps) - view.rx_t[scope] < wait:
                raise SequenceError("tap accepted before the lease and lock-delay ran out")
        elif claimed == "witness":
            if self.granted.get((scope, epoch)) != sid:
                raise SequenceError("witness epoch without a granted claim")

    def deliver_lease(self, t: int, r: str, m: dict) -> None:
        if self.views[r].left:
            raise SequenceError(f"{m['type']} sent to a member that left")
        if m["type"] == "record" and self.owner(r) in self.removed_owners:
            raise SequenceError("record sent to a removed member")
        if m["type"] == "owner_state" and self.owner(r) != m["owner"]:
            raise SequenceError("owner_state sent outside its owner")
        view = self.views[r]
        lease = m["lease"]
        scope, epoch, holder = lease["scope"], lease["epoch"], lease["holder"]
        mine = view.epoch.get(scope, 0)
        if m["type"] == "record":
            stale_hides = {(h["kind"], h.get("feed")) for h in m.get("hides", [])}
        else:
            stale_hides = {("privacy", f["feed"]) for f in m["feeds"] if f["privacy"] == "on"}
        if epoch > mine:
            if view.leads.get(scope) is not None and view.leads[scope] < epoch:
                del view.leads[scope]
                view.standby[scope] = True
            view.epoch[scope], view.holder[scope], view.lease[scope] = epoch, holder, lease
            view.rx_t[scope] = t
            view.conflict[scope] = False
            self.adopt(view, scope, m, stale_hides)
        elif epoch == mine:
            if holder != view.holder.get(scope):
                view.conflict[scope] = True
                if view.leads.get(scope) != epoch:
                    view.holder[scope] = max(holder, view.holder.get(scope, ""))
            if holder == view.holder.get(scope):
                view.rx_t[scope] = t
                view.lease[scope] = lease
            self.adopt(view, scope, m, stale_hides)
        else:
            view.refused.append(f"stale:{m['type']}:{epoch}")
            if view.leads.get(scope) is not None:
                view.must_include.setdefault(scope, set()).update(stale_hides)
            else:
                view.sticky.update(stale_hides)
                view.hides.update(stale_hides)

    def adopt(self, view: View, scope: str, m: dict, hides: set) -> None:
        if m["type"] != "record" or view.leads.get(scope) is not None:
            return
        epoch = m["lease"]["epoch"]
        keep = set()
        for h in view.sticky:
            if h in hides or (scope, epoch, h) not in self.released:
                keep.add(h)
        view.sticky = {h for h in keep if h not in hides}
        view.hides = set(hides) | view.sticky

    def check_record_rules(self, t: int, sender: str, m: dict, recipients: list[str]) -> None:
        view = self.views[sender]
        hides = {(h["kind"], h.get("feed")) for h in m.get("hides", [])}
        missing = view.must_include.get("show", set()) - hides
        missing = {h for h in missing if h[0] != "privacy"}
        if missing:
            kind, feed = sorted(missing, key=str)[0]
            raise SequenceError(f"dropped a hide ({self.label(kind, feed)}) without a show-more order")
        view.hides = hides
        if self.rotation_needed_above is not None:
            if m["key_gen"] <= self.rotation_needed_above:
                raise SequenceError("kept the old session key after a member was removed or left")
            self.rotation_needed_above = None
        if m["key_gen"] < self.key_gen:
            raise SequenceError("session key generation went backwards")
        self.key_gen = m["key_gen"]
        host = self.host()
        owners = {o["owner"]: o for o in m["owners"]}
        for oid in self.removed_owners:
            if oid in owners and owners[oid]["state"] == "joined":
                raise SequenceError("a removed owner is still listed as joined")
        for x in m["members"]:
            if x["state"] == "joined" and self.alias.get(x["member"]) in self.left_members:
                raise SequenceError("a member that left is still listed as joined")
            if x["state"] == "joined" and x["owner"] not in (None, host) and x["member"] not in self.joined:
                raise SequenceError("another owner's device is listed without having joined")
            if x["state"] == "joined" and x["owner"] not in (None, host) and x["caps"]:
                if not set(x["caps"]) <= self.live_caps(host, x["owner"], t):
                    raise SequenceError("a member has show rights no live grant gives")
        for f in m["feeds"]:
            if f["owner"] in self.removed_owners and f["state"] == "open":
                raise SequenceError("a removed owner's feed is still open")
            if f["carrier"] and self.alias.get(f["carrier"]) in self.left_members:
                raise SequenceError("a feed is still carried by a member that left")
            if f["on_air"] and f["owner"] != host:
                if not self.active_grant(f["owner"], host, "feed.on_air", t):
                    raise SequenceError("another owner's feed is on air without that owner's consent")
        self.latest_record = m

    def check_owner_rules(self, sender: str, m: dict) -> None:
        view = self.views[sender]
        scope = m["lease"]["scope"]
        private = {f["feed"] for f in m["feeds"] if f["privacy"] == "on"}
        for kind, feed in view.must_include.get(scope, set()):
            if kind == "privacy" and feed not in private:
                raise SequenceError(f"dropped a hide ({self.label(kind, feed)}) without a show-more order")
        self.auto_failover[m["owner"]] = m["auto_failover"]
        for d in m["devices"]:
            before = self.sources.get(d["member"])
            if before is not None and before != d["source"]:
                raise SequenceError("a device's identity changed between shows or joins")
            self.sources[d["member"]] = d["source"]

    # -- transfer and witness --------------------------------------------
    def transfer(self, t: int, sender: str, m: dict) -> None:
        view = self.views[sender]
        scope = m["scope"]
        if view.leads.get(scope) is None or self.member_id[sender] != m["from"]:
            raise SequenceError("transfer from a device that doesn't hold the lease")
        if m["epoch"] != view.leads[scope] + 1:
            raise SequenceError("transfer must name the next epoch")
        self.pending[(scope, m["epoch"])] = {"from": m["from"], "to": m["to"], "ready": False, "handed": False, "t": t}

    def ready(self, sender: str, m: dict) -> None:
        p = self.pending.get((m["scope"], m["epoch"]))
        if not p or p["to"] != self.member_id[sender] or m["member"] != p["to"]:
            raise SequenceError("ready without a matching transfer")
        p["ready"] = True

    def handed(self, sender: str, m: dict) -> None:
        p = self.pending.get((m["scope"], m["epoch"]))
        if not p or p["from"] != self.member_id[sender] or p["to"] != m["to"]:
            raise SequenceError("handed without a matching transfer")
        if not p["ready"]:
            raise SequenceError("handed before the new device was ready")
        p["handed"] = True
        view = self.views[sender]
        view.handed[m["scope"]] = view.leads.pop(m["scope"])
        view.standby[m["scope"]] = True

    def claim(self, t: int, sender: str, m: dict) -> None:
        view = self.views[sender]
        scope = m["scope"]
        tapped = any(s == scope for s, _ in view.taps)
        owner_scope_owner = self.host() if scope == "show" else scope.split(":", 1)[1]
        if not tapped and not self.auto_failover.get(owner_scope_owner, False):
            raise SequenceError("automatic claim while automatic failover is off")
        if m["lookup"] != self.lookup:
            raise SequenceError("claim with the wrong lookup key")
        self.claims.setdefault((scope, m["epoch"]), set()).add(m["member"])

    def claim_result(self, t: int, sender: str, m: dict) -> None:
        if "witness" not in self.members[sender].get("serves", []):
            raise SequenceError("claim_result from a member that isn't a witness")
        if m["result"] != "granted":
            return
        scope, epoch = m["scope"], m["epoch"]
        if m["holder"] not in self.claims.get((scope, epoch), set()):
            raise SequenceError("witness granted a claim nobody made")
        if (scope, epoch) in self.granted:
            raise SequenceError(f"two holders for {scope} epoch {epoch}")
        w = self.witness.get(scope)
        if w is not None:
            if epoch != w["epoch"] + 1:
                raise SequenceError("witness granted a non-consecutive epoch")
            wait = self.witness_cfg["valid_for_ms"] + self.witness_cfg["lock_delay_ms"]
            if t - w["renewed_t"] < wait:
                raise SequenceError("witness granted the lease before it and the lock-delay ran out")
        self.granted[(scope, epoch)] = m["holder"]
        self.witness[scope] = {"epoch": epoch, "holder": m["holder"], "renewed_t": t}

    def sealed(self, t: int, sender: str, m: dict, recipients: list[str]) -> None:
        for r in recipients:
            if self.owner(r) in self.removed_owners or self.views[r].left:
                raise SequenceError("sealed message sent to a removed member")
        if self.rotation_needed_above is not None and m["key_gen"] <= self.rotation_needed_above:
            raise SequenceError("sealed with the old session key after a member was removed or left")
        sid = self.member_id[sender]
        scope, epoch = m["scope"], m["epoch"]
        w = self.witness.get(scope)
        if self.views[sender].leads.get(scope) == epoch:
            if w is None or (w["epoch"] < epoch):
                self.witness[scope] = {"epoch": epoch, "holder": sid, "renewed_t": t}
            elif w["epoch"] == epoch and w["holder"] == sid:
                w["renewed_t"] = t

    # -- orders -----------------------------------------------------------
    def order(self, t: int, sender: str, m: dict, recipients: list[str]) -> None:
        sid = self.member_id[sender]
        if m["by"] != sid:
            raise SequenceError("order names someone else as its sender")
        action, feed, scope = m["action"], m.get("feed"), m["scope"]
        tag = self.label(action, feed)
        for r in recipients:
            view = self.views[r]
            if view.leads.get(scope) is None:
                if action in HIDE_KIND and self.permitted(t, sender, m):
                    kind = HIDE_KIND[action]
                    view.sticky.add((kind, feed if kind != "brb" else None))
                    view.hides.add((kind, feed if kind != "brb" else None))
                    view.applied.append(tag)
                else:
                    view.refused.append(f"{tag}:not_coordinator")
                continue
            if not self.permitted(t, sender, m):
                view.refused.append(f"{tag}:not_permitted")
                continue
            if action in HIDE_ACTIONS:
                view.applied.append(tag)
                if action in HIDE_KIND:
                    kind = HIDE_KIND[action]
                    view.must_include.setdefault(scope, set()).add((kind, feed if kind != "brb" else None))
                view.min_version[scope] = view.version.get(scope, 0) + 1
                continue
            if m["epoch"] != view.leads[scope] or m["against"] != view.version.get(scope):
                view.refused.append(f"{tag}:stale")
                continue
            view.applied.append(tag)
            if action in RELEASES:
                kind = RELEASES[action]
                h = (kind, feed if kind != "brb" else None)
                view.must_include.get(scope, set()).discard(h)
                self.released.add((scope, view.leads[scope], h))
            view.min_version[scope] = view.version.get(scope, 0) + 1

    def permitted(self, t: int, sender: str, m: dict) -> bool:
        sid = self.member_id[sender]
        sender_owner = self.owner(sender)
        action, feed, scope = m["action"], m.get("feed"), m["scope"]
        caps = self.caps_of(sid)
        if scope.startswith("owner:"):
            scope_owner = scope.split(":", 1)[1]
            if sender_owner == scope_owner:
                return True
            if action == "privacy_on":
                return self.active_grant(scope_owner, sender_owner, "feed.hide", t)
            return False
        if action in ("brb_on", "cancel_countdown"):
            return bool(caps & {"show.hide", "show.mix"})
        if action == "off_air":
            return bool(caps & {"show.hide", "show.mix"}) or self.feed_owner(feed) == sender_owner
        return "show.mix" in caps

    # -- grants -----------------------------------------------------------
    def invite(self, t: int, sender: str, m: dict) -> None:
        if self.owner(sender) != m["issuer"]:
            raise SequenceError("invite issued by someone else's device")
        self.invites[m["invite"]] = {**m, "t": t, "used": 0}

    def join(self, t: int, sender: str, m: dict) -> None:
        inv = self.invites.get(m["invite"])
        if inv is None:
            raise SequenceError("join for an unknown invite")
        if self.member_id[sender] != m["member"] or self.owner(sender) != m["owner"]:
            raise SequenceError("join names another device or owner")
        if t - inv["t"] > inv["ttl_ms"]:
            raise SequenceError("invite used after it expired")
        inv["used"] += 1
        if inv["used"] > inv["uses"]:
            raise SequenceError("invite used more times than allowed")
        earlier = self.joins.setdefault(m["invite"], [])
        if earlier and earlier[0] != m["owner"]:
            raise SequenceError("invite reused by another owner")
        earlier.append(m["owner"])
        self.joined.add(m["member"])
        self.views[sender].left = False
        self.left_members.discard(sender)

    def grant(self, t: int, sender: str, m: dict) -> None:
        if self.owner(sender) != m["issuer"]:
            raise SequenceError("grant issued by someone else's device")
        if m["invite"] is not None:
            inv = self.invites.get(m["invite"])
            if inv is None or inv["issuer"] != m["issuer"]:
                raise SequenceError("grant for an invite its issuer never made")
            if m["holder"] not in self.joins.get(m["invite"], []):
                raise SequenceError("grant for an invite nobody redeemed")
            offer = inv["offers"]
            if not self.within(m, {**offer, "ttl_ms": m["ttl_ms"]}):
                raise SequenceError("grant gives more than its invite offered")
        if m["parent"] is not None:
            parent = self.grants.get(m["parent"])
            if parent is None or not self.grant_live(parent, t):
                raise SequenceError("grant under a parent that is not live")
            if parent["holder"] != m["issuer"] or "grant.attenuate" not in parent["caps"]:
                raise SequenceError("grant passed on without grant.attenuate")
            if not self.within(m, parent):
                raise SequenceError("grant widens its parent")
        old = self.grants.get(m["grant"])
        if old is not None:
            if old["revoked_t"] is not None:
                raise SequenceError("a revoked grant can't be renewed")
            if m["renewal"] <= old["renewal"]:
                raise SequenceError("grant renewal counter didn't go up")
            if not self.within(m, old):
                raise SequenceError("renewal widens the grant")
        self.grants[m["grant"]] = {**m, "renewed_t": t, "revoked_t": None}

    def within(self, child: dict, parent: dict) -> bool:
        return (
            set(child["caps"]) <= set(parent["caps"])
            and LEVELS.index(child["level"]) <= LEVELS.index(parent["level"])
            and LOCATION_MODES.index(child["location"]) <= LOCATION_MODES.index(parent["location"])
            and set(child.get("ingests", [])) <= set(parent.get("ingests", []))
            and child["ttl_ms"] <= parent["ttl_ms"]
        )

    def revoke(self, t: int, sender: str, m: dict) -> None:
        g = self.grants.get(m["grant"])
        if g is None:
            raise SequenceError("revoke of an unknown grant")
        if self.owner(sender) != g["issuer"] and not (m["reason"] == "left" and self.owner(sender) == g["holder"]):
            raise SequenceError("revoked by someone who neither issued nor holds it")
        todo = [m["grant"]]
        while todo:
            gid = todo.pop()
            grant = self.grants[gid]
            if grant["revoked_t"] is None:
                grant["revoked_t"] = t
                todo.extend(k for k, v in self.grants.items() if v["parent"] == gid)
        host = self.host()
        for oid in {v["holder"] for v in self.grants.values()}:
            if oid != host and not self.active_grant(host, oid, "show.view", t):
                had = any(v["issuer"] == host and v["holder"] == oid and "show.view" in v["caps"] for v in self.grants.values())
                if had and oid not in self.removed_owners:
                    self.removed_owners.add(oid)
                    self.rotation_needed_above = self.key_gen

    def leave(self, t: int, sender: str, m: dict) -> None:
        if self.member_id[sender] != m["member"]:
            raise SequenceError("leave for another device")
        self.views[sender].left = True
        self.left_members.add(sender)
        self.rotation_needed_above = self.key_gen

    def projection(self, t: int, sender: str, m: dict, recipients: list[str]) -> None:
        if self.owner(sender) != m["from"]:
            raise SequenceError("projection sent by another owner's device")
        g = self.grants.get(m["grant"])
        if g is None or g["issuer"] != m["from"] or g["holder"] != m["to"]:
            raise SequenceError("projection without a matching grant")
        if g["revoked_t"] is not None:
            raise SequenceError("projection under a revoked grant")
        if t - g["renewed_t"] > g["ttl_ms"]:
            raise SequenceError("projection under an expired grant")
        if LEVELS.index(m["level"]) > LEVELS.index(g["level"]):
            raise SequenceError("projection above its grant's level")
        if LOCATION_MODES.index(m["shares_location"]) > LOCATION_MODES.index(g["location"]):
            raise SequenceError("projection shares location its grant doesn't allow")
        for r in recipients:
            if self.owner(r) != m["to"]:
                raise SequenceError("projection delivered outside its grant")

    # -- running -----------------------------------------------------------
    def run(self, steps: list[dict]) -> None:
        last_t = -1
        for index, step in enumerate(steps):
            t = step["t"]
            if t < last_t:
                raise SequenceError(f"step {index}: time goes backwards")
            last_t = t
            try:
                self.step(t, step)
            except SequenceError as error:
                raise SequenceError(f"step {index}: {error}") from None

    def step(self, t: int, step: dict) -> None:
        if "tap" in step:
            self.views[step["at"]].taps.append((step.get("scope", "show"), t))
            return
        if "expect" in step:
            self.expect(t, step["at"], step["expect"])
            return
        sender = step["from"]
        m = step["msg"]
        errors = validate(m)
        if errors:
            raise SequenceError("invalid message: " + "; ".join(errors[:3]))
        if m.get("session", self.session) != self.session:
            raise SequenceError("message for another session")
        if self.views[sender].left and m["type"] != "join":
            raise SequenceError("a member that left keeps sending")
        recipients = self.recipients(step, sender)
        kind = m["type"]
        if kind in ("record", "owner_state"):
            self.lease_message(t, sender, m, recipients)
        elif kind == "transfer":
            self.transfer(t, sender, m)
        elif kind == "ready":
            self.ready(sender, m)
        elif kind == "handed":
            self.handed(sender, m)
        elif kind == "moved":
            if self.views[sender].handed.get(m["scope"]) != m["epoch"] - 1:
                raise SequenceError("moved without having handed over")
            for r in recipients:
                self.views[r].moved_to[m["scope"]] = m["holder"]
        elif kind == "claim":
            self.claim(t, sender, m)
        elif kind == "claim_result":
            self.claim_result(t, sender, m)
        elif kind == "sealed":
            self.sealed(t, sender, m, recipients)
        elif kind == "order":
            self.order(t, sender, m, recipients)
        elif kind == "invite":
            self.invite(t, sender, m)
        elif kind == "join":
            self.join(t, sender, m)
        elif kind == "grant":
            self.grant(t, sender, m)
        elif kind == "revoke":
            self.revoke(t, sender, m)
        elif kind == "leave":
            self.leave(t, sender, m)
        elif kind == "projection":
            self.projection(t, sender, m, recipients)
        elif kind == "unknown_member":
            for r in recipients:
                self.views[r].told_unknown = True
        elif kind == "hello":
            self.views[sender].told_unknown = False

    def expect(self, t: int, at: str, want: dict) -> None:
        view = self.views[at]
        scope = want.get("scope", "show")
        got: dict[str, Any] = {
            "epoch": view.epoch.get(scope),
            "holder": self.alias.get(view.holder.get(scope)),
            "leads": view.leads.get(scope) is not None,
            "standby": view.standby.get(scope, False),
            "conflict": view.conflict.get(scope, False),
            "hides": sorted(self.label(k, f) for k, f in view.hides),
            "applied": view.applied,
            "refused": view.refused,
            "moved_to": self.alias.get(view.moved_to.get(scope)),
            "told_unknown": view.told_unknown,
        }
        lease = view.lease.get(scope)
        if lease is None or scope not in view.rx_t:
            got["coordinator_unknown"] = True
        else:
            got["coordinator_unknown"] = view.leads.get(scope) is None and t - view.rx_t[scope] > lease["valid_for_ms"]
        for key, value in want.items():
            if key == "scope":
                continue
            if key not in got:
                raise SequenceError(f"unknown expectation '{key}'")
            actual = got[key]
            if key == "hides":
                value = sorted(value)
            if actual != value:
                raise SequenceError(f"expected {at}.{key} = {value!r}, got {actual!r}")


def run_sequence(fixture: dict) -> str | None:
    """Return None if the sequence follows the rules, else the first error."""
    seq = Sequence(fixture)
    try:
        seq.run(fixture["steps"])
    except SequenceError as error:
        return str(error)
    return None


# --------------------------------------------------------------------------
# Fixtures

def run_tests(verbose: bool = False) -> int:
    failures = 0
    count = 0
    for path in sorted((FIXTURES / "valid").glob("*.json")):
        count += 1
        fx = load_json(path)
        errors = validate(fx["message"])
        if errors:
            failures += 1
            print(f"FAIL {path.relative_to(ROOT)}: {errors}")
    for path in sorted((FIXTURES / "invalid").glob("*.json")):
        count += 1
        fx = load_json(path)
        errors = validate(fx["message"])
        if not any(fx["error"] in e for e in errors):
            failures += 1
            print(f"FAIL {path.relative_to(ROOT)}: wanted '{fx['error']}', got {errors}")
        elif len(errors) != 1:
            failures += 1
            print(f"FAIL {path.relative_to(ROOT)}: wanted exactly one error, got {errors}")
    for path in sorted((FIXTURES / "sequences").glob("*.json")):
        count += 1
        fx = load_json(path)
        error = run_sequence(fx)
        want = fx["expect"]
        if want == "ok" and error is not None:
            failures += 1
            print(f"FAIL {path.relative_to(ROOT)}: {error}")
        elif want != "ok" and (error is None or want["error"] not in error):
            failures += 1
            print(f"FAIL {path.relative_to(ROOT)}: wanted '{want['error']}', got {error!r}")
    print(f"{count - failures}/{count} fixtures pass")
    return 1 if failures else 0


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] not in ("validate", "sequence", "test"):
        print(__doc__.strip())
        return 2
    if argv[1] == "test":
        return run_tests()
    status = 0
    for name in argv[2:]:
        try:
            data = load_json(pathlib.Path(name))
        except (OSError, json.JSONDecodeError) as error:
            print(f"{name}: can't read: {error}")
            status = 1
            continue
        if argv[1] == "validate":
            message = data.get("message", data) if isinstance(data, dict) else data
            errors = validate(message)
            print(f"{name}: " + ("ok" if not errors else "\n  ".join(["invalid"] + errors)))
        else:
            error = run_sequence(data)
            errors = [] if error is None else [error]
            print(f"{name}: " + ("follows the rules" if not errors else f"breaks a rule: {error}"))
        status = status or (1 if errors else 0)
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv))
