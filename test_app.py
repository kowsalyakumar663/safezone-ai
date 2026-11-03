"""Basic local smoke tests for the SafeZone AI Flask API."""
import unittest
import app as safezone_app


class SafeZoneApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = safezone_app.app.test_client()

    def test_health(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["ok"])

    def test_dashboard_has_counts(self):
        response = self.client.get("/api/dashboard")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("overall_risk", data)
        self.assertIn("critical", data["zone_counts"])

    def test_risks_list(self):
        response = self.client.get("/api/risks")
        self.assertEqual(response.status_code, 200)
        self.assertGreater(response.get_json()["count"], 0)

    def test_risk_filter(self):
        response = self.client.get("/api/risks?level=critical")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(all(item["level"] == "critical" for item in response.get_json()["items"]))

    def test_invalid_risk_filter(self):
        response = self.client.get("/api/risks?level=unknown")
        self.assertEqual(response.status_code, 400)

    def test_meta(self):
        response = self.client.get("/api/meta")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["backend"], "Python Flask")


if __name__ == "__main__":
    unittest.main()
