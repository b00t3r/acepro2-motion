"""Run the native sensor table writer with a mocked I2C write boundary.

The table address, row count and 78-byte row size come from the native
OV50H40 initializer and 0x14b6c20 writer. The sentinel 0x26 means skip.
No sensor hardware, additional setup branches or image data are executed.
"""
import json
import struct
from unicorn.arm64_const import (UC_ARM64_REG_X0, UC_ARM64_REG_X1,
    UC_ARM64_REG_X2, UC_ARM64_REG_X3, UC_ARM64_REG_X4, UC_ARM64_REG_X5)
from livephoto_harness import BASE, CONTEXT, Harness, ROOT, image

TABLE, ROW_SIZE, ROWS = 0x3cf13e8, 78, 653


def probe(mode):
    if mode not in (3,16,33,36,53): raise ValueError('Unsupported comparison mode')
    h=Harness((ROOT/'builds/offline-highres-memory/main_threadx.bin').read_bytes())
    writes=[]
    def i2c(uc):
        ptr, size=uc.reg_read(UC_ARM64_REG_X1),uc.reg_read(UC_ARM64_REG_X2)
        if size<3 or size>4000: raise ValueError('Unexpected sensor write size')
        payload=bytes(uc.mem_read(ptr,size))
        addr=int.from_bytes(payload[:2],'big')
        writes.extend([(addr+i,b) for i,b in enumerate(payload[2:])])
        return 0
    h.mocks={0x14b62e0:i2c}
    for reg,val in ((UC_ARM64_REG_X0,0),(UC_ARM64_REG_X1,mode),
                    (UC_ARM64_REG_X2,TABLE),(UC_ARM64_REG_X3,ROWS),
                    (UC_ARM64_REG_X4,CONTEXT+0x1000),(UC_ARM64_REG_X5,4000)):
        h.uc.reg_write(reg,val)
    h.run(0x14b6c20,max_instructions=1000000)
    d=image();off=TABLE-BASE
    expected=[(struct.unpack_from('<H',d,off+i*ROW_SIZE)[0],d[off+i*ROW_SIZE+2+mode])
              for i in range(ROWS) if d[off+i*ROW_SIZE+2+mode]!=0x26]
    if writes!=expected: raise ValueError('Native writer and table differ')
    return dict(mode=mode,write_count=len(writes),status=h.uc.reg_read(UC_ARM64_REG_X0),
                sequence=[dict(address=hex(a),value=v) for a,v in writes],
                i2c_mocked=True,hardware_tested=False)


def main():
    results=[probe(n) for n in (3,16,33,36,53)]
    out=ROOT/'analysis/motion-resolution-audit/sensor-register-sequences.json'
    out.write_text(json.dumps(results,indent=2)+'\n')
    print(json.dumps([dict(mode=r['mode'],write_count=r['write_count'],status=r['status']) for r in results],indent=2))


if __name__=='__main__':main()
