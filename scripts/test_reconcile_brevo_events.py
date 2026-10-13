import unittest

from reconcile_brevo_events import plan_event_writes


class BrevoReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.ledger = {"<provider-test>": "careers@employer.example"}
        self.known = {"messageId": "<provider-test>", "email": "careers@employer.example",
                      "date": "2026-10-11 10:01:00"}

    def test_real_delivery_becomes_delivery_event(self):
        writes, counts = plan_event_writes([dict(self.known, event="delivered")], self.ledger)
        self.assertEqual(1, len(writes))
        self.assertEqual("delivered", writes[0]["p_event_type"])

    def test_hard_bounce_overrides_conflicting_delivered(self):
        writes, counts = plan_event_writes(
            [dict(self.known, event="delivered"),
             dict(self.known, event="hardbounces", reason="550 mailbox absent")], self.ledger
        )
        self.assertEqual(["hardBounce"], [w["p_event_type"] for w in writes])
        self.assertEqual(1, counts["bounce_or_complaint_message_ids"])

    def test_soft_bounce_is_not_permanently_suppressed(self):
        writes, counts = plan_event_writes(
            [dict(self.known, event="softbounces")], self.ledger
        )
        self.assertFalse(writes)
        self.assertEqual(1, counts["soft_bounces_for_manual_review"])

    def test_recipient_mismatch_fails_closed(self):
        writes, counts = plan_event_writes(
            [dict(self.known, event="hardbounces", email="other@example.com")], self.ledger
        )
        self.assertFalse(writes)
        self.assertEqual(1, counts["recipient_mismatch"])

    def test_stable_idempotency_keys(self):
        events = [dict(self.known, event="hardbounces", reason="550")]
        a, _ = plan_event_writes(events, self.ledger)
        b, _ = plan_event_writes(events, self.ledger)
        self.assertEqual(a, b)
        self.assertEqual(1, len(a))


if __name__ == "__main__":
    unittest.main()
