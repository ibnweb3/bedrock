import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bedrock.hashing import hash_author_id  # noqa: E402

SALT = "a" * 40
OTHER_SALT = "b" * 40


class HashAuthorIdTests(unittest.TestCase):
    def test_deterministic(self):
        self.assertEqual(hash_author_id("A123", SALT), hash_author_id("A123", SALT))

    def test_different_ids_differ(self):
        self.assertNotEqual(hash_author_id("A123", SALT), hash_author_id("A124", SALT))

    def test_salt_changes_output(self):
        self.assertNotEqual(hash_author_id("A123", SALT), hash_author_id("A123", OTHER_SALT))

    def test_raw_id_not_in_output(self):
        self.assertNotIn("A123", hash_author_id("A123", SALT))

    def test_short_salt_rejected(self):
        with self.assertRaises(ValueError):
            hash_author_id("A123", "short")

    def test_empty_id_rejected(self):
        with self.assertRaises(ValueError):
            hash_author_id("", SALT)


if __name__ == "__main__":
    unittest.main()
