import unittest

from src.editorial import apply_editorial_state, sort_for_public_feed


class EditorialTests(unittest.TestCase):
    def test_apply_editorial_state_sets_defaults(self):
        cards = [{"id": "a", "score_total": 50.0}, {"id": "b", "score_total": 70.0}]
        applied = apply_editorial_state(cards, {})

        self.assertEqual(applied[0]["status"], "published")
        self.assertFalse(applied[0]["is_pinned"])
        self.assertEqual(applied[0]["pin_rank"], 1000)

    def test_sort_prioritizes_pinned_then_score(self):
        cards = [
            {"id": "a", "is_pinned": False, "pin_rank": 1000, "score_total": 90},
            {"id": "b", "is_pinned": True, "pin_rank": 10, "score_total": 20},
            {"id": "c", "is_pinned": True, "pin_rank": 5, "score_total": 10},
        ]

        sorted_cards = sort_for_public_feed(cards)
        self.assertEqual([c["id"] for c in sorted_cards], ["c", "b", "a"])


if __name__ == "__main__":
    unittest.main()
