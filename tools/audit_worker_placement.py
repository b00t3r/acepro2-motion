"""Execute native map construction and descriptor encoding for worker placement."""
import json
import struct
from livephoto_harness import Harness
from unicorn.arm64_const import *
from build_background_prototype import ROOT,OUT,WORKER_BASE,WORKER_END


def native_regions():
    h=Harness();h.uc.mem_map(0x1339f000,0x1000)
    h.stops[0xc3a8ec]='first_regions_constructed'
    h.run(0xc3a7c0)
    return [dict(zip(('virtual','physical','size','attributes'),
        struct.unpack('<4Q',bytes(h.uc.mem_read(0x1339f7e8+32*i,32))))) for i in range(3)]


def descriptor_bits(attributes):
    h=Harness();sp=h.uc.reg_read(UC_ARM64_REG_SP)
    h.uc.mem_map(0x13e57000,0x1000)
    h.uc.mem_write(sp+0x68,struct.pack('<Q',attributes))
    h.uc.mem_write(sp+0x58,struct.pack('<Q',1))
    for reg,val in ((UC_ARM64_REG_X3,attributes),(UC_ARM64_REG_X7,1),
                    (UC_ARM64_REG_X6,0),(UC_ARM64_REG_X23,0x13e57000),(UC_ARM64_REG_X22,0)):
        h.uc.reg_write(reg,val)
    h.stops[0x12269d0]='attributes_encoded'
    h.run(0x122695c)
    d=int.from_bytes(h.uc.mem_read(sp+0x58,8),'little')
    return {'descriptor':hex(d),'access_permission_bits':(d>>6)&3,
            'privileged_execute_never':bool(d&(1<<53)),
            'execute_never':bool(d&(1<<54))}


def main():
    regions=native_regions()
    region=regions[1]
    assert region['virtual']<=WORKER_BASE<WORKER_END+8<=region['virtual']+region['size']
    assert WORKER_END+8<=regions[2]['virtual']
    report={'native_regions':regions,'worker_range':[hex(WORKER_BASE),hex(WORKER_END)],
        'root_slot':hex(WORKER_END),'native_descriptor_bits':descriptor_bits(region['attributes']),
        'same_native_map_entry_as_working_startup_payload':True,
        'placement':'Alignment gap after explicit text-end symbol 0x2552008 and before data-start symbol 0x2553000',
        'hardware_memory_mapping_tested':False,
        'limitations':'Native map construction/encoding emulated; runtime page tables are not read from hardware.'}
    (ROOT/'analysis/background-save/placement.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
