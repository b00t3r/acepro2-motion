import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from probe_sensor_register_sequence import probe


class SensorRegisterSequenceTests(unittest.TestCase):
    def test_mode16_and_known_full_sensor_sequences(self):
        fast,still,slow=(probe(n) for n in (16,33,53))
        self.assertEqual([r['write_count'] for r in (fast,still,slow)],[652]*3)
        self.assertTrue(all(r['i2c_mocked'] and r['status']==0 for r in (fast,still,slow)))
        for other in (still,slow):
            pairs=list(zip(fast['sequence'],other['sequence']))
            self.assertTrue(all(a['address']==b['address'] for a,b in pairs))
            self.assertEqual([a['address'] for a,b in pairs if a['value']!=b['value']],
                             ['0x380e','0x380f','0x3811'])


if __name__=='__main__':unittest.main()
