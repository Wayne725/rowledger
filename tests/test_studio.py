import base64
import hashlib
import http.client
import io
import json
import sqlite3
import tempfile
import threading
import unittest
import zipfile
from concurrent.futures import ThreadPoolExecutor
from importlib.resources import files
from pathlib import Path

from rowledger.studio_server import make_server
from rowledger.studio_store import ConflictError, StudioStore


class StudioStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = StudioStore(Path(self.temp.name) / "workspace")
        examples = files("rowledger").joinpath("examples")
        self.orders = examples.joinpath("orders.csv").read_bytes()
        self.payments = examples.joinpath("payments.csv").read_bytes()
        self.batch = self.store.create("October review", "orders.csv", self.orders, "payments.csv", self.payments)["batch"]

    def document(self, decisions=None):
        return {"schema_version": 1, "run_id": self.batch["snapshot"], "decisions": decisions if decisions is not None else [
            {"order_row_id": "orders:8", "payment_row_id": "payments:7", "reviewer": "Lin", "reason": "Verified reference typo."}]}

    def test_restart_and_duplicate_import_preserve_batch_and_decisions(self):
        self.store.save_review(self.batch["id"], 0, self.document(), "Lin", "Checked transfer reference.")
        reopened = StudioStore(self.store.directory)
        duplicate = reopened.create("Another name", "orders.csv", self.orders, "payments.csv", self.payments)
        self.assertTrue(duplicate["reused"])
        self.assertEqual(duplicate["batch"]["id"], self.batch["id"])
        self.assertEqual(duplicate["batch"]["title"], "October review")
        self.assertEqual(duplicate["batch"]["summary"]["matched_pairs"], 6)
        self.assertEqual(reopened.get(self.batch["id"])["revision"], 1)

    def test_changed_bytes_and_rules_create_new_snapshots_without_carrying_review(self):
        self.store.save_review(self.batch["id"], 0, self.document(), "Lin", "Checked reference.")
        changed_bytes = self.orders.replace(b"00041,", b"00041 ,", 1)
        self.assertNotEqual(changed_bytes, self.orders)
        changed = self.store.create("Changed", "orders.csv", changed_bytes, "payments.csv", self.payments)
        self.assertNotEqual(changed["batch"]["snapshot"], self.batch["snapshot"])
        self.assertEqual(changed["batch"]["decisions"], [])
        mapped = self.store.create("New rules", "orders.csv", self.orders, "payments.csv", self.payments, {"trim_keys": False})
        with self.assertRaisesRegex(ValueError, "Stale review"):
            self.store.save_review(mapped["batch"]["id"], 0, self.document(), "Lin", "Attempted old review.")

    def test_review_rejects_stale_revision_and_invalid_pair_without_writing(self):
        self.store.save_review(self.batch["id"], 0, self.document(), "Lin", "Checked reference.")
        with self.assertRaises(ConflictError):
            self.store.save_review(self.batch["id"], 0, self.document([]), "Lin", "Old screen.")
        bad = self.document([{**self.document()["decisions"][0], "payment_row_id": "payments:9"}])
        with self.assertRaises(ValueError):
            self.store.save_review(self.batch["id"], 1, bad, "Lin", "Wrong amount.")
        current = self.store.get(self.batch["id"])
        self.assertEqual(current["revision"], 1)
        self.assertEqual(len(current["events"]), 2)

    def test_only_one_concurrent_revision_update_is_committed(self):
        def update(actor):
            try:
                self.store.save_review(self.batch["id"], 0, self.document(), actor, "Concurrent confirmation.")
                return "saved"
            except ConflictError:
                return "conflict"
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(update, ("Lin", "Hsu")))
        self.assertCountEqual(results, ["saved", "conflict"])
        self.assertEqual(len(self.store.get(self.batch["id"])["events"]), 2)

    def test_close_requires_acknowledgement_freezes_review_and_reopen_allows_undo(self):
        self.store.save_review(self.batch["id"], 0, self.document(), "Lin", "Checked reference.")
        with self.assertRaisesRegex(ValueError, "acknowledge"):
            self.store.set_state(self.batch["id"], 1, "closed", "Lin", "Remaining issues deferred.")
        closed = self.store.set_state(self.batch["id"], 1, "closed", "Lin", "Remaining issues deferred.", True)
        self.assertEqual(closed["summary"]["needs_attention"], 14)
        with self.assertRaises(ConflictError):
            self.store.save_review(self.batch["id"], 2, self.document([]), "Lin", "Undo while closed.")
        self.store.set_state(self.batch["id"], 2, "open", "Lin", "Additional evidence received.")
        undone = self.store.save_review(self.batch["id"], 3, self.document([]), "Lin", "Withdraw incorrect confirmation.")
        self.assertEqual(undone["summary"]["matched_pairs"], 5)
        self.assertEqual(undone["summary"]["needs_attention"], 16)
        self.assertEqual(len(self.store.get(self.batch["id"])["events"]), 5)

    def test_export_retains_exact_sources_reviews_history_and_checksums(self):
        self.store.save_review(self.batch["id"], 0, self.document(), "Lin", "Checked reference.")
        with self.assertRaises(ConflictError):
            self.store.export(self.batch["id"], 0)
        with zipfile.ZipFile(io.BytesIO(self.store.export(self.batch["id"], 1))) as archive:
            self.assertEqual(archive.read("inputs/orders/orders.csv"), self.orders)
            self.assertEqual(archive.read("inputs/payments/payments.csv"), self.payments)
            result = json.loads(archive.read("results.json"))
            self.assertEqual(len(result["rows"]), 26)
            self.assertEqual(result["summary"]["matched_pairs"], 6)
            history = json.loads(archive.read("workspace.json"))["events"]
            self.assertEqual(history[1]["detail"]["before"], [])
            self.assertEqual(history[1]["detail"]["after"], self.document()["decisions"])
            manifest = json.loads(archive.read("manifest.json"))
            self.assertEqual(set(manifest["sha256"]), set(archive.namelist()) - {"manifest.json"})
            for name, digest in manifest["sha256"].items():
                self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(), digest)

    def test_rejected_imports_leave_no_batch_or_event(self):
        for name in ("../orders.csv", "C:orders.csv", "folder\\orders.csv", "orders\n.csv"):
            with self.assertRaises(ValueError):
                self.store.create("Bad", name, self.orders, "payments.csv", self.payments)
        with self.assertRaises(ValueError):
            self.store.create("Bad", "orders.csv", b"wrong,columns\n1,2\n", "payments.csv", self.payments)
        self.assertEqual(len(self.store.list_batches()), 1)

    def test_pagination_conserves_rows_and_filters_do_not_change_data(self):
        content = b"order_id,amount,currency\n" + b"".join(f"{index:05},1,USD\n".encode() for index in range(61))
        batch = self.store.create("Many rows", "orders.csv", content, "payments.csv", content)["batch"]
        pages = [self.store.get(batch["id"], page=page) for page in (1, 2, 3)]
        ids = [row["row_id"] for page in pages for row in page["rows"]]
        self.assertEqual(len(ids), 122)
        self.assertEqual(len(set(ids)), 122)
        self.assertEqual(self.store.get(batch["id"], status="attention")["total"], 0)
        self.assertEqual(self.store.get(batch["id"], side="orders")["total"], 61)
        self.assertEqual(self.store.get(batch["id"], query="00001")["total"], 2)
        self.assertEqual(self.store.get(batch["id"])["revision"], 0)

    def test_sources_are_immutable_after_review_and_export(self):
        self.store.save_review(self.batch["id"], 0, self.document(), "Lin", "Checked reference.")
        self.store.export(self.batch["id"], 1)
        with sqlite3.connect(self.store.database) as connection:
            row = connection.execute("SELECT orders, payments FROM batches WHERE id = ?", (self.batch["id"],)).fetchone()
        self.assertEqual(tuple(row), (self.orders, self.payments))
        self.assertEqual(self.store.database.stat().st_mode & 0o777, 0o600)


class StudioServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.server = make_server(self.temp.name, 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.cleanup)

    def cleanup(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, method, path, payload=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        body = json.dumps(payload).encode() if payload is not None else None
        fields = {"X-RowLedger-Token": self.server.session_token, "Content-Type": "application/json"}
        fields.update(headers or {})
        connection.request(method, path, body=body, headers=fields)
        response = connection.getresponse()
        status, content, response_headers = response.status, response.read(), dict(response.getheaders())
        connection.close()
        return status, content, response_headers

    def test_session_host_and_origin_protect_api(self):
        self.assertEqual(self.request("GET", "/api/batches", headers={"X-RowLedger-Token": ""})[0], 403)
        self.assertEqual(self.request("GET", "/api/batches", headers={"Origin": "http://foreign.example"})[0], 403)
        self.assertEqual(self.request("GET", "/api/batches", headers={"Host": "foreign.example"})[0], 403)
        status, content, headers = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(self.server.session_token.encode(), content)
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertNotIn("Access-Control-Allow-Origin", headers)
        self.assertEqual(self.request("GET", "/../studio.sqlite3")[0], 404)

    def test_real_http_import_review_export_round_trip(self):
        examples = files("rowledger").joinpath("examples")
        payload = {"title": "HTTP review", "rules": {}, **{
            side: {"name": f"{side}.csv", "content": base64.b64encode(examples.joinpath(f"{side}.csv").read_bytes()).decode()}
            for side in ("orders", "payments")}}
        status, content, _ = self.request("POST", "/api/batches", payload)
        self.assertEqual(status, 201)
        batch = json.loads(content)["batch"]
        review = {"revision": 0, "actor": "Lin", "note": "Confirmed reference typo.", "document": {
            "schema_version": 1, "run_id": batch["snapshot"], "decisions": [{"order_row_id": "orders:8", "payment_row_id": "payments:7", "reviewer": "Lin", "reason": "Confirmed reference typo."}]}}
        self.assertEqual(self.request("POST", f"/api/batches/{batch['id']}/review", review)[0], 200)
        self.assertEqual(self.request("POST", f"/api/batches/{batch['id']}/review", review)[0], 409)
        status, content, _ = self.request("GET", f"/api/batches/{batch['id']}/export?revision=1")
        self.assertEqual(status, 200)
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            self.assertEqual(json.loads(archive.read("results.json"))["summary"]["matched_pairs"], 6)

    def test_demo_is_explicit_synthetic_and_duplicate_import_reuses_batch(self):
        status, body, _ = self.request("POST", "/api/demo", {})
        self.assertEqual(status, 201)
        batch = json.loads(body)["batch"]
        self.assertEqual(batch["summary"]["rows"], 26)
        self.assertEqual(batch["summary"]["matched_pairs"], 5)
        status, body, _ = self.request("POST", "/api/demo", {})
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)["reused"])
        self.assertEqual(json.loads(body)["batch"]["id"], batch["id"])
        self.assertEqual(len(self.server.studio_store.list_batches()), 1)

    def test_malformed_requests_do_not_write_data(self):
        self.assertEqual(self.request("POST", "/api/batches", ["not an object"])[0], 400)
        self.assertEqual(self.request("GET", "/api/batches/not-found")[0], 404)
        self.assertEqual(json.loads(self.request("GET", "/api/batches")[1])["batches"], [])


if __name__ == "__main__":
    unittest.main()
