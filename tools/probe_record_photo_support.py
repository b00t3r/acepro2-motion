"""Execute photo-during-recording support calculation with controlled inputs.

The three camera services are mocked. This does not enable UI or capture.
"""
import json
import struct
from unicorn.arm64_const import UC_ARM64_REG_X0,UC_ARM64_REG_X1,UC_ARM64_REG_X2
from livephoto_harness import Harness,ROOT


def probe(mode,config_a,config_b,other_guard=0,state_guard=0):
    h=Harness();h.uc.mem_map(0x124b0000,0x1000)
    h.uc.mem_write(0x124b0384,struct.pack('<I',state_guard))
    def config(uc):
        if (uc.reg_read(UC_ARM64_REG_X0),uc.reg_read(UC_ARM64_REG_X2)) != (0x18,8):
            raise ValueError('Unexpected configuration query')
        uc.mem_write(uc.reg_read(UC_ARM64_REG_X1),struct.pack('<II',config_a,config_b))
        return 0
    h.mocks={0x363a00:lambda uc:mode,0x2e4380:config,0x2902e0:lambda uc:other_guard}
    h.run(0x37d8a0)
    return dict(controlled_mode=mode,controlled_config=[config_a,config_b],
      controlled_other_guard=other_guard,controlled_state_guard=state_guard,
      returned=h.uc.reg_read(UC_ARM64_REG_X0)&0xffffffff,
      mocks=['mode lookup','configuration read','other guard'],hardware_executed=False)


def audit():
    return dict(cases=[probe(0,a,b) for a,b in ((0,0),(1,0),(2,0),(2,4),(2,5),(2,12),(18,0))],
      context='Callers at 0x37dbc8 and 0x3eeba8 use this result for photo during recording.',
      profile_mapping='Native lookup at 0x361278 reads record spec 0x18 and compares its two words to descriptor offsets 4 and 8. The 8K/24 descriptor matching the hardware log has spec [0,0]; the 4K HDR/24 snapshot descriptor has [2,0].',
      limitations=['Probe inputs are controlled; the record spec itself was inferred from the descriptor matching each hardware log, not logged directly.',
        'Support calculation does not establish sensor, raw buffer, UI, capture or picture processing works.',
        'No firmware or camera changes.'])


if __name__=='__main__':
    r=audit()
    (ROOT/'analysis/direct-8k-hardware/record-photo-support.json').write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps(r,indent=2))
