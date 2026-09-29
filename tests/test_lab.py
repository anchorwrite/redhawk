import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from redhawk.__main__ import request
from redhawk.cases import CASES, assess
from redhawk.domain import classify
from redhawk.server import make_server


class LabTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.key = "test-key-" + "x" * 32
        cls.db = Path(cls.temp.name) / "lab.sqlite3"
        cls.server = make_server("127.0.0.1", 0, cls.db, cls.key)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.temp.cleanup()

    def api(self, path, body=None):
        return request(self.base + path, body, self.key)

    def payload(self, case, event_id):
        data = classify({"event_id": event_id, **CASES[case]["input"]})
        return {**data, "source": "reference", "queue": CASES[case]["expected"]["queue"]}

    def test_authentication(self):
        self.assertEqual(request(self.base + "/health")[0], 200)
        self.assertEqual(request(self.base + "/events/private")[0], 401)
        self.assertEqual(request(self.base + "/tickets", {}, "wrong")[0], 401)

    def test_normalize_and_classify_real_http(self):
        for case in ("standard", "urgent", "ambiguous"):
            status, normalized = self.api("/normalize", {"event_id": case, **CASES[case]["input"]})
            self.assertEqual(status, 200)
            status, result = self.api("/classify", normalized)
            self.assertEqual(status, 200)
            expected = CASES[case]["expected"]
            for field in ("customer_email", "message", "category", "priority"):
                self.assertEqual(result[field], expected[field])
            self.assertEqual(result["needs_review"], expected["queue"] == "review")

    def test_invalid_is_observed_not_silently_lost(self):
        self.assertTrue(assess({"ticket": None, "events": []}, "invalid", "reference"))
        status, _ = self.api("/normalize", {"event_id": "bad", **CASES["invalid"]["input"]})
        self.assertEqual(status, 422)
        _, snapshot = self.api("/events/bad")
        self.assertEqual(assess(snapshot, "invalid", "reference"), [])

    def test_wrong_types_and_json_arrays_are_rejected(self):
        self.assertEqual(self.api("/normalize", [1, 2])[0], 422)
        self.assertEqual(self.api("/normalize", {"event_id": "a", **CASES["standard"]["input"], "fail_once": "false"})[0], 422)
        self.assertEqual(self.api("/tickets", {**self.payload("standard", "types"), "queue": []})[0], 422)

    def test_retry_and_duplicate_survive_new_store(self):
        from redhawk.store import Store
        body = self.payload("retry", "retry-test")
        self.assertEqual(self.api("/tickets", body)[0], 503)
        self.assertIsNone(self.api("/events/retry-test")[1]["ticket"])
        # A new connection/store still sees the fault marker and succeeds.
        self.assertEqual(Store(self.db).create_ticket(body)[0], 201)
        self.assertEqual(self.api("/tickets", body)[0], 200)
        snapshot = self.api("/events/retry-test")[1]
        self.assertEqual(assess(snapshot, "retry", "reference"), [])

    def test_concurrent_deliveries_create_one_ticket(self):
        body = self.payload("duplicate", "concurrent")
        with ThreadPoolExecutor(max_workers=6) as pool:
            statuses = list(pool.map(lambda _: self.api("/tickets", body)[0], range(6)))
        self.assertEqual(statuses.count(201), 1)
        self.assertEqual(statuses.count(200), 5)
        self.assertEqual(assess(self.api("/events/concurrent")[1], "duplicate", "reference"), [])

    def test_changed_duplicate_conflicts(self):
        body = self.payload("standard", "conflict")
        self.assertEqual(self.api("/tickets", body)[0], 201)
        self.assertEqual(self.api("/tickets", {**body, "message": "Changed"})[0], 409)
        self.assertEqual(self.api("/events/conflict")[1]["ticket"]["message"], body["message"])

    def test_checker_catches_wrong_routing(self):
        body = {**self.payload("urgent", "wrong-route"), "queue": "standard"}
        self.assertEqual(self.api("/tickets", body)[0], 201)
        failures = assess(self.api("/events/wrong-route")[1], "urgent", "reference")
        self.assertTrue(any("queue" in failure for failure in failures))

    def test_cli_reference_demo_passes_all_cases(self):
        result = subprocess.run(
            [sys.executable, "-m", "redhawk", "demo", "--base-url", self.base],
            cwd=Path(__file__).resolve().parents[1],
            env={**os.environ, "LAB_API_KEY": self.key},
            capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.count("PASS "), 6)

    def test_cli_init_does_not_overwrite_existing_key(self):
        with tempfile.TemporaryDirectory() as folder:
            env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])}
            command = [sys.executable, "-m", "redhawk", "init"]
            first = subprocess.run(command, cwd=folder, env=env, capture_output=True, timeout=10)
            self.assertEqual(first.returncode, 0)
            original = (Path(folder) / ".env").read_bytes()
            second = subprocess.run(command, cwd=folder, env=env, capture_output=True, timeout=10)
            self.assertEqual(second.returncode, 1)
            self.assertEqual((Path(folder) / ".env").read_bytes(), original)

    def test_cli_server_stops_cleanly_on_sigterm(self):
        with tempfile.TemporaryDirectory() as folder:
            log_path = Path(folder) / "server.log"
            with log_path.open("w") as log:
                process = subprocess.Popen(
                    [sys.executable, "-m", "redhawk", "serve", "--port", "0",
                     "--db", str(Path(folder) / "shutdown.sqlite3")],
                    cwd=Path(__file__).resolve().parents[1],
                    env={**os.environ, "LAB_API_KEY": self.key}, stdout=log, stderr=log,
                )
                try:
                    deadline = time.monotonic() + 5
                    while "Lab API:" not in log_path.read_text() and time.monotonic() < deadline:
                        if process.poll() is not None:
                            break
                        time.sleep(0.05)
                    self.assertIn("Lab API:", log_path.read_text())
                    # Allow signal handler registration immediately after the readiness log.
                    time.sleep(0.1)
                    process.terminate()
                    self.assertEqual(process.wait(timeout=5), 0, log_path.read_text())
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.wait(timeout=5)

    def test_sample_files_match_checker_inputs(self):
        root = Path(__file__).resolve().parents[1]
        for case, details in CASES.items():
            payload = json.loads((root / "samples" / f"{case}.json").read_text())
            payload.pop("event_id")
            self.assertEqual(payload, details["input"])

    def test_workflow_graph_and_credentials(self):
        path = Path(__file__).resolve().parents[1] / "workflows/n8n/support-intake.json"
        workflow = json.loads(path.read_text())
        names = {node["name"] for node in workflow["nodes"]}
        self.assertFalse(workflow["active"])
        for node in workflow["nodes"]:
            self.assertNotIn("credentials", node)
        for source, connections in workflow["connections"].items():
            self.assertIn(source, names)
            for branch in connections["main"]:
                for connection in branch:
                    self.assertIn(connection["node"], names)
        self.assertEqual(len(workflow["connections"]["Needs review?"]["main"]), 2)


if __name__ == "__main__":
    unittest.main()
