import csv
import tempfile
import unittest
from pathlib import Path

from lead_scraper import (
    Candidate,
    Extraction,
    build_leads,
    build_queries,
    canonicalize_url,
    first_location,
    source_for,
    write_outputs,
)


class LeadScraperTests(unittest.TestCase):
    def test_build_queries_covers_web_x_linkedin(self):
        queries = build_queries(["looking for"])
        self.assertEqual(len(queries), 3)
        hints = {hint for _, _, hint in queries}
        self.assertEqual(hints, {"web", "x", "linkedin"})
        combined = " ".join(q for q, _, _ in queries)
        self.assertIn("Riyadh", combined)
        self.assertIn("الرياض", combined)

    def test_location_detection_prefers_city(self):
        self.assertEqual(first_location("Looking in Riyadh, Saudi Arabia"), "Riyadh")
        self.assertEqual(first_location("مطلوب مورد في جدة"), "Jeddah")
        self.assertEqual(first_location("الدمام"), "Dammam")

    def test_url_normalization(self):
        url = canonicalize_url("https://twitter.com/acme/status/123?utm_source=x")
        self.assertEqual(url, "https://x.com/acme/status/123")
        self.assertEqual(source_for(url), "X")

    def test_build_lead_from_search_snippet(self):
        candidate = Candidate(
            title="Acme on X: Looking for a vendor in Riyadh",
            url="https://x.com/acme/status/123",
            snippet="Looking for a vendor in Riyadh for an urgent office project.",
            query='site:x.com "looking for" Riyadh',
            query_phrase="looking for",
            source_hint="x",
        )
        leads = build_leads([candidate], {}, minimum_score=6)
        self.assertEqual(len(leads), 1)
        self.assertEqual(leads[0].matched_location, "Riyadh")
        self.assertEqual(leads[0].source, "X")

    def test_location_is_required(self):
        candidate = Candidate(
            title="Need urgently a vendor",
            url="https://example.com/post/1",
            snippet="Need urgently a vendor for an office project.",
            query='"need urgently" Riyadh',
            query_phrase="need urgently",
            source_hint="web",
        )
        leads = build_leads([candidate], {}, minimum_score=1)
        self.assertEqual(leads, [])

    def test_csv_contract_is_exact(self):
        candidate = Candidate(
            title="محمد on X: أبحث عن مورد في جدة",
            url="https://x.com/example/status/456",
            snippet="أبحث عن مورد في جدة بشكل عاجل",
            query='site:x.com "أبحث عن مورد" جدة',
            query_phrase="أبحث عن مورد",
            source_hint="x",
        )
        extraction = Extraction(text="", date="2026-09-05")
        leads = build_leads([candidate], {candidate.url: extraction}, minimum_score=6)
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "leads.csv"
            json_path = Path(tmp) / "leads.json"
            write_outputs(leads, csv_path, json_path)
            with csv_path.open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.reader(handle))
            self.assertEqual(rows[0], ["Name", "Post Content", "Date", "Link"])
            self.assertEqual(len(rows), 2)


if __name__ == "__main__":
    unittest.main()
