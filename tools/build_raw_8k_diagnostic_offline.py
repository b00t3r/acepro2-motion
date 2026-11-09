"""Build emulator-only diagnostic image; no flashable package or staging.

The in-memory patch enables existing sampled raw-event logging on large event
widths. Raw event availability, thread behavior and the event layout require
hardware validation; this is deliberately not a camera update.
"""
import json
import subprocess
from build_background_prototype import link_regions
from livephoto_geometry_patch import branch
from livephoto_harness import BASE,ROOT
from probe_guarded_fullsensor import HOOK as CONFIG_HOOK, ORIGINAL as CONFIG_ORIGINAL

SOURCE=ROOT/'builds/offline-highres-memory/main_threadx.bin'
OUT=ROOT/'builds/offline-8k-raw-diagnostic'
HOOK=0x276f5c
LOG_LEVEL=0x277038
STUB,END=0x2552c40,0x2552fe0
STATE=0x2552fe0


def build():
    OUT.mkdir(parents=True,exist_ok=True)
    paths=[]
    for name in ('raw_8k_diagnostic_hook.S','fullsensor_marker_hook.S','raw_8k_marker.c'):
        obj=OUT/(name+'.o')
        flags=['clang','-target','aarch64-none-elf','-Os','-ffreestanding','-fno-builtin',
          '-fno-stack-protector','-fno-unwind-tables','-fno-asynchronous-unwind-tables','-mno-outline-atomics']
        if name.endswith('.c'): flags+=['-mgeneral-regs-only','-fno-jump-tables']
        subprocess.run(flags+['-c',str(ROOT/'tools'/name),'-o',str(obj)],check=True)
        paths.append(obj)
    blobs,symbols,_=link_regions([(STUB,END,paths)],{'raw_native_debug':0x276fa4,
        'raw_native_normal':0x276f60,'native_live_continue':CONFIG_HOOK+4,'raw_diag_state':STATE})
    before=SOURCE.read_bytes(); after=bytearray(before); body=blobs[0]
    if before[HOOK-BASE:HOOK-BASE+4] != bytes.fromhex('40021037'):
        raise ValueError('Unexpected native diagnostic gate')
    if before[CONFIG_HOOK-BASE:CONFIG_HOOK-BASE+4] != CONFIG_ORIGINAL:
        raise ValueError('Unexpected configuration hook')
    if before[LOG_LEVEL-BASE:LOG_LEVEL-BASE+4] != bytes.fromhex('c0008052'):
        raise ValueError('Unexpected native raw log level')
    if any(before[STUB-BASE:STATE-BASE+1]):
        raise ValueError('Diagnostic code region is occupied')
    if symbols['raw_8k_diagnostic_hook'] != STUB: raise ValueError('Unexpected hook address')
    after[HOOK-BASE:HOOK-BASE+4]=branch(HOOK,STUB)
    after[CONFIG_HOOK-BASE:CONFIG_HOOK-BASE+4]=branch(CONFIG_HOOK,symbols['fullsensor_marker_hook'])
    after[LOG_LEVEL-BASE:LOG_LEVEL-BASE+4]=bytes.fromhex('a0008052') # mov w0,#5 (normal)
    after[STUB-BASE:STUB-BASE+len(body)]=body
    (OUT/'main_threadx_OFFLINE_ONLY.bin').write_bytes(after)
    report=dict(status='Offline experiment only; not a firmware update',
        hook=hex(HOOK),config_hook=hex(CONFIG_HOOK),log_level_patch=hex(LOG_LEVEL),state=hex(STATE),stub=hex(STUB),stub_bytes=len(body),width_threshold=6000,
        activation='The 4:3 Live Photo configuration checks C:\\RAW8K.ENABLE and enables the diagnostic only when open and close succeed; other resource configurations leave the state unchanged.',
        existing_log='[LV_RAW] VinId ... Compressed ... res ... aux_res',
        native_sampling='Existing native log samples when its incremented counter modulo 5000 is 1.',
        limitations=['The event width offset is inferred from existing native log argument setup and is not yet confirmed by a hardware raw-event log.',
          'The raw callback may not be delivered at the desired 8K time; native sampling and initial state matter.',
          'Logging context, stack, thread safety, state retention across mode changes and scheduling impact have not been validated on hardware.',
          'Recovery by marker removal has not been validated for this particular build; errors default to disabled when the configuration hook runs.',
          'No hardware change, flashable package, or card staging.'])
    (OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


if __name__=='__main__': print(json.dumps(build(),indent=2))
