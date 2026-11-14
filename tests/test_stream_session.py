"""Tests for tools/stream_session.py. Run: python3 -m unittest discover -s tests"""
from __future__ import annotations

import contextlib
import copy
import io
import json
import os
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import stream_session as ss  # noqa: E402


def load(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def quiet(fn, *args):
    with contextlib.redirect_stdout(io.StringIO()) as out:
        result = fn(*args)
    return result, out.getvalue()


class Fixtures(unittest.TestCase):
    def test_every_fixture(self):
        status, out = quiet(ss.run_tests)
        self.assertEqual(status, 0, out)

    def test_each_invalid_fixture_has_one_error(self):
        for path in sorted((ROOT / "fixtures" / "invalid").glob("*.json")):
            with self.subTest(path.name):
                fx = json.loads(path.read_text(encoding="utf-8"))
                errors = ss.validate(fx["message"])
                self.assertEqual(len(errors), 1, errors)
                self.assertIn(fx["error"], errors[0])

    def test_sequences_mark_their_bench_needs(self):
        marked = [p.name for p in (ROOT / "fixtures" / "sequences").glob("*.json")
                  if "bench" in json.loads(p.read_text(encoding="utf-8"))]
        self.assertGreaterEqual(len(marked), 3)


class SchemaEvaluator(unittest.TestCase):
    def test_matches_jsonschema_when_installed(self):
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema not installed")
        validator = jsonschema.Draft202012Validator(ss.schema())
        jsonschema.Draft202012Validator.check_schema(ss.schema())
        messages = []
        for folder in ("valid", "invalid"):
            for path in sorted((ROOT / "fixtures" / folder).glob("*.json")):
                messages.append((path.name, json.loads(path.read_text(encoding="utf-8"))["message"]))
        for path in sorted((ROOT / "fixtures" / "sequences").glob("*.json")):
            for index, step in enumerate(json.loads(path.read_text(encoding="utf-8"))["steps"]):
                if "msg" in step:
                    messages.append((f"{path.name}#{index}", step["msg"]))
        for name, message in messages:
            with self.subTest(name):
                theirs = bool(list(validator.iter_errors(message)))
                ours = bool(ss.schema_errors(message))
                self.assertEqual(theirs, ours)

    def test_booleans_are_not_integers(self):
        message = load("fixtures/valid/01-solo-record.json")["message"]
        message["version"] = True
        self.assertTrue(any("not of type integer" in e for e in ss.schema_errors(message)))

    def test_unknown_type_is_rejected(self):
        self.assertTrue(ss.schema_errors({"format": "stream-session", "v": 0, "type": "gossip"}))

    def test_unsupported_keyword_is_loud(self):
        with self.assertRaises(ValueError):
            list(ss.schema_iter("x", {"format": "email"}))


class Privacy(unittest.TestCase):
    def test_times_and_ids_are_not_addresses(self):
        clean = {"since": "2026-11-15T14:02:10.120Z", "id": "a1a1b2b2c3c3d4d4", "url": "wss://coord.example/s/ab"}
        self.assertEqual(ss.privacy_errors(clean), [])

    def test_addresses_are_found(self):
        for value in ("10.0.0.1", "2001:db8::1", "fe80::1", "2001:0db8:0000:0000:0000:ff00:0042:8329"):
            with self.subTest(value):
                self.assertTrue(ss.privacy_errors({"label": value}))

    def test_keys_and_tokens_are_found(self):
        for value in ("srt://relay.example:5000?streamid=abc", "live_123456789_AbCdEfGhIjKlMn",
                      "oauth:abcdefghijklmnopqrst", "eyJhbGciOiJIUzI1.eyJzdWIiOiIx"):
            with self.subTest(value):
                self.assertTrue(ss.privacy_errors({"label": value}))

    def test_ciphertext_is_not_scanned(self):
        self.assertEqual(ss.privacy_errors({"ct": "sst0_aaaaaaaaaaaaaaaaaaaa", "nonce": "x", "proof": "y"}), [])

    def test_location_setting_is_not_location(self):
        grant = load("fixtures/valid/09-share-grant.json")["message"]
        self.assertEqual(ss.privacy_errors(grant), [])
        grant["x_demo_gps"] = "on"
        self.assertTrue(any("location outside" in e for e in ss.privacy_errors(grant)))

    def test_location_only_in_a_projection(self):
        record = load("fixtures/valid/01-solo-record.json")["message"]
        record["owners"][0]["x_demo_lat"] = 52.5
        self.assertTrue(any("location outside" in e for e in ss.privacy_errors(record)))


class SequenceRules(unittest.TestCase):
    def test_removing_the_tap_breaks_the_takeover(self):
        fx = load("fixtures/sequences/03-takeover-after-tap.json")
        fx["steps"] = [s for s in fx["steps"] if "tap" not in s]
        self.assertIn("without the streamer's tap", ss.run_sequence(fx))

    def test_a_wrong_expectation_is_reported(self):
        fx = load("fixtures/sequences/09-split-brain-hide-wins.json")
        last = [s for s in fx["steps"] if "expect" in s][-1]
        last["expect"]["hides"] = ["brb"]
        self.assertIn("expected companion.hides", ss.run_sequence(fx))

    def test_stale_show_more_from_permitted_member_is_refused(self):
        fx = load("fixtures/sequences/09-split-brain-hide-wins.json")
        self.assertIsNone(ss.run_sequence(fx))
        seq = ss.Sequence(fx)
        seq.run(fx["steps"])
        self.assertIn("brb_off:stale", seq.views["phone"].refused)
        self.assertIn("brb_off", seq.views["phone"].applied)

    def test_revoking_a_parent_revokes_its_children(self):
        fx = load("fixtures/sequences/23-collab-levels-and-hides.json")
        seq = ss.Sequence(fx)
        seq.run(fx["steps"])
        child = seq.grants["e7e7d8d8c9c9b0b0"]
        self.assertIsNotNone(child["revoked_t"])

    def test_time_must_not_go_backwards(self):
        fx = load("fixtures/sequences/02-handover-stalls.json")
        fx["steps"][2]["t"] = 0
        self.assertIn("time goes backwards", ss.run_sequence(fx))

    def test_invalid_message_inside_a_sequence(self):
        fx = load("fixtures/sequences/02-handover-stalls.json")
        fx["steps"][0]["msg"]["x_demo_password"] = "x"
        self.assertIn("invalid message", ss.run_sequence(fx))

    def test_expired_grant_stops_projections(self):
        fx = load("fixtures/sequences/15-guest-joins-and-is-removed.json")
        steps = [s for s in fx["steps"] if s.get("msg", {}).get("type") != "revoke"][:7]
        late = copy.deepcopy(steps[6])
        late["t"] = 60200 + 600001
        fx["steps"] = steps + [late]
        self.assertIn("expired grant", ss.run_sequence(fx))


class CommandLine(unittest.TestCase):
    def test_validate_exit_codes(self):
        good = str(ROOT / "fixtures" / "valid" / "01-solo-record.json")
        bad = str(ROOT / "fixtures" / "invalid" / "01-secret-field.json")
        self.assertEqual(quiet(ss.main, ["x", "validate", good])[0], 0)
        self.assertEqual(quiet(ss.main, ["x", "validate", bad])[0], 1)

    def test_sequence_exit_codes(self):
        good = str(ROOT / "fixtures" / "sequences" / "01-handover-pc-phone-box.json")
        bad = str(ROOT / "fixtures" / "sequences" / "05-takeover-without-tap.json")
        self.assertEqual(quiet(ss.main, ["x", "sequence", good])[0], 0)
        self.assertEqual(quiet(ss.main, ["x", "sequence", bad])[0], 1)

    def test_unreadable_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "broken.json")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("{")
            self.assertEqual(quiet(ss.main, ["x", "validate", path])[0], 1)

    def test_usage(self):
        self.assertEqual(quiet(ss.main, ["x"])[0], 2)


class StreamStatusInterop(unittest.TestCase):
    """Shared snapshots must stay valid stream-status. Set STREAM_STATUS_DIR to a checkout."""

    def test_embedded_snapshots_are_valid_stream_status(self):
        where = os.environ.get("STREAM_STATUS_DIR")
        if not where:
            self.skipTest("STREAM_STATUS_DIR not set")
        try:
            import jsonschema  # noqa: F401  (the stream-status tool needs it)
        except ImportError:
            self.skipTest("jsonschema not installed")
        sys.path.insert(0, str(pathlib.Path(where) / "tools"))
        import stream_status

        def walk(node):
            if isinstance(node, dict):
                if node.get("format") == "stream-status":
                    yield node
                for value in node.values():
                    yield from walk(value)
            elif isinstance(node, list):
                for value in node:
                    yield from walk(value)

        count = 0
        for path in sorted((ROOT / "fixtures").rglob("*.json")):
            for snapshot in walk(json.loads(path.read_text(encoding="utf-8"))):
                count += 1
                with self.subTest(path.name):
                    self.assertEqual(stream_status.validate(snapshot), [])
        self.assertGreater(count, 0)


if __name__ == "__main__":
    unittest.main()
