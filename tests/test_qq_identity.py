from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.qq_identity import load_qq_identity, normalize_qq_identity, save_qq_identity


class QqIdentityTests(unittest.TestCase):
    def test_missing_identity_uses_defaults_and_can_migrate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            identity = load_qq_identity(
                root,
                default_bot_qq_id=123456,
                default_owner_qq_id=654321,
                create_if_missing=True,
            )
            self.assertEqual(
                identity,
                {"bot_qq_id": 123456, "owner_qq_id": 654321},
            )
            self.assertEqual(
                json.loads((root / "data" / "qq_identity.json").read_text("utf-8")),
                identity,
            )

    def test_save_is_atomic_and_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            expected = {"bot_qq_id": 12345678, "owner_qq_id": 87654321}
            self.assertEqual(save_qq_identity(root, expected), expected)
            self.assertEqual(load_qq_identity(root), expected)
            self.assertFalse((root / "data" / "qq_identity.tmp").exists())

    def test_rejects_invalid_qq_ids(self) -> None:
        for invalid in ("", "1234", "abc123", "012345", "1" * 13):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                normalize_qq_identity(
                    {"bot_qq_id": invalid, "owner_qq_id": 123456}
                )


if __name__ == "__main__":
    unittest.main()
