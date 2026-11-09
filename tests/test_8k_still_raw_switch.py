import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from audit_8k_still_raw_switch import audit


class RawSwitchTests(unittest.TestCase):
    def test_recorded_and_template_settings(self):
        result=audit()
        templates={x['index']:x for x in result['templates']}
        self.assertEqual(templates[7]['still_raw_enabled'],0)
        self.assertEqual(templates[7]['raw_size'],[0,0])
        self.assertEqual(templates[15]['still_raw_enabled'],1)
        self.assertEqual(templates[15]['raw_size'],[4096,3072])
        self.assertEqual(len(result['observed_8k']['events']),4)
        self.assertEqual(len(result['observed_4k']['events']),4)


if __name__=='__main__':
    unittest.main()
