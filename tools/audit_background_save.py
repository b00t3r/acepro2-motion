"""Read-only native task ABI audit. No background firmware is built or staged."""
import json
import struct
from pathlib import Path
from livephoto_harness import Harness, CONTEXT
from unicorn.arm64_const import (UC_ARM64_REG_X0,UC_ARM64_REG_X1,UC_ARM64_REG_X2,
    UC_ARM64_REG_X3,UC_ARM64_REG_X4,UC_ARM64_REG_X5,UC_ARM64_REG_X6,UC_ARM64_REG_X7)

ROOT=Path(__file__).resolve().parents[1]


def task_create_contract(priority=80):
    h=Harness();name=CONTEXT+0x1000;entry=0x50240;stack=CONTEXT+0x2000
    h.uc.mem_write(name,b'Offline motion worker\0')
    h.uc.mem_write(CONTEXT+0x8b0,struct.pack('<QIIIIQQQI',name,0,1,priority,0,
                                          CONTEXT+0x1800,entry,stack,0x10000))
    h.uc.reg_write(UC_ARM64_REG_X0,CONTEXT)
    regs=(UC_ARM64_REG_X0,UC_ARM64_REG_X1,UC_ARM64_REG_X2,UC_ARM64_REG_X3,
          UC_ARM64_REG_X4,UC_ARM64_REG_X5,UC_ARM64_REG_X6,UC_ARM64_REG_X7)
    observed=[]
    def create(uc):
        observed.append({'callee':'native_task_create','args':[uc.reg_read(r) for r in regs]})
        return 0
    def affinity(uc):
        observed.append({'callee':'native_task_affinity','task':uc.reg_read(regs[0]),'mask':uc.reg_read(regs[1])})
        return 0
    def resume(uc):
        observed.append({'callee':'native_task_resume','task':uc.reg_read(regs[0])})
        return 0
    h.mocks={0x1248ac0:create,0x1248f40:affinity,0x1248ca0:resume}
    h.run(0x25ec00)
    return {'status':h.uc.reg_read(UC_ARM64_REG_X0),'calls':observed,
            'task_state':int.from_bytes(h.uc.mem_read(CONTEXT+0x8b8,4),'little'),
            'hardware_executed':False,'scheduler_executed':False}


def main():
    report={'native_task_contract':task_create_contract(),
        'existing_motion_payload_bytes':3078,
        'remaining_contiguous_bytes_before_colour_stub':0x50e80-(0x50240+3078),
        'queue_core':'tools/motion_queue_core.c',
        'queue_capacity_including_active_job':2,
        'integration_status':'Offline queue core only; no worker hooked or firmware candidate produced',
        'pending':['Prove executable space for worker and storage barriers; zero-filled asset data is not assumed free',
                   'Initialize worker and queue safely using native task and memory APIs',
                   'Pass captured timestamp explicitly into save instead of rereading globals',
                   'Trace and guard gallery/delete/format, UDisk and power-off storage transitions',
                   'Test actual packaged worker, error cleanup and scheduler interactions before staging']}
    out=ROOT/'analysis/background-save';out.mkdir(exist_ok=True)
    (out/'audit.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
