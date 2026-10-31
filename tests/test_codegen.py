"""normalize_code: undo model escape-doubling in generated Python."""

import unittest

from core.schemas.remediation import GeneratedPatch, normalize_code


class NormalizeCodeTests(unittest.TestCase):
    def test_valid_code_passes_through(self) -> None:
        code = "def f():\n    return 1\n"
        self.assertEqual(normalize_code(code), code)

    def test_intentional_string_escape_passes_through(self) -> None:
        code = 'def f():\n    return "a\\n"\n'
        self.assertEqual(normalize_code(code), code)

    def test_doubled_escapes_decoded(self) -> None:
        blob = "def f():\\n    return 1\\n"
        self.assertEqual(normalize_code(blob), "def f():\n    return 1\n")

    def test_still_broken_code_returned_as_is(self) -> None:
        blob = "def broken(:\\n    nope\\n"
        self.assertEqual(normalize_code(blob), blob)

    def test_non_ascii_blob_returned_as_is(self) -> None:
        blob = "x = 'caf\xe9'\\n oops(:"
        self.assertEqual(normalize_code(blob), blob)

    def test_non_string_returned_as_is(self) -> None:
        self.assertIsNone(normalize_code(None))  # type: ignore[arg-type]

    def test_generated_patch_validator_unescapes(self) -> None:
        patch = GeneratedPatch(
            patch_code="x = 1\\n",
            test_code="def test_x():\\n    assert True\\n",
        )
        self.assertEqual(patch.patch_code, "x = 1\n")
        self.assertEqual(patch.test_code, "def test_x():\n    assert True\n")

    def test_generated_patch_validator_keeps_valid_code(self) -> None:
        patch = GeneratedPatch(
            patch_code="x = 1\n",
            test_code='def test_x():\n    assert "a\\n" == "a" + chr(10)\n',
        )
        self.assertEqual(patch.patch_code, "x = 1\n")
        self.assertIn('"a\\n"', patch.test_code)


if __name__ == "__main__":
    unittest.main()
