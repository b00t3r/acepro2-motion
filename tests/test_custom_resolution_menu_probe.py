import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from probe_custom_resolution_menu import EXISTING_VALUES, probe


class CustomResolutionMenuProbeTests(unittest.TestCase):
    def test_native_menu_accepts_seventh_entry_and_preserves_existing_slots(self):
        six, seven = probe(6), probe(7)
        self.assertEqual((seven['native_label_capacity'], seven['native_value_capacity']), (10, 10))
        self.assertEqual((seven['native_label_count'], seven['native_value_count']), (7, 7))
        self.assertEqual(seven['label_pointers'][:6], six['label_pointers'][:6])
        self.assertEqual(seven['menu_values'][:6], list(EXISTING_VALUES))
        self.assertEqual(seven['label_pointers'][6], seven['expected_label_pointers'][6])
        self.assertEqual(seven['menu_values'][6], 6)
        self.assertEqual(seven['custom_label'], 'C 20 MP')

    def test_guard_rejects_reusing_an_existing_menu_value(self):
        with self.assertRaises(ValueError):
            probe(custom_value=EXISTING_VALUES[0])


if __name__ == '__main__':
    unittest.main()
