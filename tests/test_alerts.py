import unittest
from server.alerts import evaluate_quick_alert
from server.models import QuickAlertEvaluateRequest, QuickAlertSensitiveAreaModel


class QuickAlertEvaluationTests(unittest.TestCase):
    def test_critical_alert_triggered_within_12_hours(self):
        req = QuickAlertEvaluateRequest(
            spill_lat=2.3812,
            spill_lon=101.9124,
            oil_confidence=95.0,
            area_km2=25.0,
            predicted_impact_hours=6.0,
            sensitive_areas=[
                QuickAlertSensitiveAreaModel(name="Cape Rachado Beach", type="beach", lat=2.5033, lon=101.7467)
            ]
        )
        res = evaluate_quick_alert(req)
        self.assertTrue(res["alert"])
        self.assertEqual(res["severity"], "Critical")
        self.assertEqual(res["severity_rank"], 4)
        self.assertEqual(res["severity_color"], "#FF4438")
        self.assertIsNotNone(res["nearest_sensitive_area"])

    def test_medium_alert_triggered_by_area_and_time(self):
        req = QuickAlertEvaluateRequest(
            spill_lat=2.4500,
            spill_lon=101.8300,
            oil_confidence=80.0,
            area_km2=5.0,
            predicted_impact_hours=36.0,
            sensitive_areas=[]
        )
        res = evaluate_quick_alert(req)
        self.assertTrue(res["alert"])
        self.assertEqual(res["severity"], "Medium")

    def test_low_alert_for_offshore_low_confidence(self):
        req = QuickAlertEvaluateRequest(
            spill_lat=55.1000,
            spill_lon=3.2000,
            oil_confidence=60.0,
            area_km2=3.0,
            is_offshore=True,
            sensitive_areas=[]
        )
        res = evaluate_quick_alert(req)
        self.assertTrue(res["alert"])
        self.assertEqual(res["severity"], "Low")

    def test_no_alert_when_below_all_triggers(self):
        req = QuickAlertEvaluateRequest(
            spill_lat=10.0,
            spill_lon=10.0,
            oil_confidence=30.0,
            area_km2=0.5,
            is_offshore=True,
            sensitive_areas=[]
        )
        res = evaluate_quick_alert(req)
        self.assertFalse(res["alert"])
        self.assertEqual(res["severity"], "None")


if __name__ == "__main__":
    unittest.main()
