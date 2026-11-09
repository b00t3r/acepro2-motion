"""Build and execute the marker hook in an emulator image, never a package."""
import functools
import struct
import subprocess

from unicorn.arm64_const import *
from build_background_prototype import link_regions
from livephoto_geometry_patch import branch
from livephoto_harness import BASE, CONTEXT, Harness, ROOT
from probe_guarded_fullsensor import HOOK, ORIGINAL

START, END = 0x2552c40, 0x2552ff0
OUT = ROOT/'builds/offline-fullsensor-diagnostic'


@functools.lru_cache(maxsize=1)
def image_and_symbols():
    OUT.mkdir(exist_ok=True)
    flags = ['clang', '-target', 'aarch64-none-elf', '-Os', '-ffreestanding',
             '-fno-builtin', '-fno-stack-protector', '-fno-unwind-tables',
             '-fno-asynchronous-unwind-tables', '-fno-jump-tables',
             '-mgeneral-regs-only', '-mno-outline-atomics']
    paths = []
    for source in ('fullsensor_marker_hook.S', 'fullsensor_marker_probe.c'):
        out = OUT/(source + '.o')
        source_flags = [x for x in flags if x != '-mgeneral-regs-only'] if source.endswith('.S') else flags
        subprocess.run(source_flags + ['-c', str(ROOT/'tools'/source), '-o', str(out)], check=True)
        paths.append(out)
    blobs, symbols, _ = link_regions([(START, END, paths)], {'native_live_continue': HOOK+4})
    body = blobs[0]
    original = (ROOT/'builds/offline-highres-memory/main_threadx.bin').read_bytes()
    modified = bytearray(original)
    if modified[HOOK-BASE:HOOK-BASE+4] != ORIGINAL or any(modified[START-BASE:START-BASE+len(body)]):
        raise ValueError('Unexpected hook site or occupied code gap')
    if symbols['fullsensor_marker_hook'] != START:
        raise ValueError('Unexpected hook entry placement')
    modified[HOOK-BASE:HOOK-BASE+4] = branch(HOOK, START)
    modified[START-BASE:START-BASE+len(body)] = body
    return bytes(modified), symbols, len(body)


def run(resource, narrow, marker_present, close_ok=True):
    image, _, length = image_and_symbols()
    h = Harness(image)
    cfg = CONTEXT + 0x1000
    h.uc.mem_write(cfg, bytes(0x70))
    h.uc.mem_write(cfg+6, struct.pack('<HHH', resource, 30, 0))
    h.uc.mem_write(cfg+0x34, struct.pack('<H', narrow))
    regs = [globals()['UC_ARM64_REG_X%d' % i] for i in range(31)]
    qregs = [globals()['UC_ARM64_REG_Q%d' % i] for i in range(32)]
    for i, reg in enumerate(regs):
        h.uc.reg_write(reg, 0x1234000000000000+i)
    for i, reg in enumerate(qregs):
        h.uc.reg_write(reg, (i+1)*0x123456789abcdef123456789abcdef)
    h.uc.reg_write(UC_ARM64_REG_X0, 30)
    h.uc.reg_write(UC_ARM64_REG_X19, cfg)
    h.uc.reg_write(UC_ARM64_REG_NZCV, 0xa0000000)
    before = [h.uc.reg_read(r) for r in regs]
    vectors = [h.uc.reg_read(r) for r in qregs]
    sp = h.uc.reg_read(UC_ARM64_REG_SP)
    calls = []
    def clobber(uc):
        for reg in regs[1:19]: uc.reg_write(reg, 0xdeadbeef)
        for reg in qregs: uc.reg_write(reg, 0)
        uc.reg_write(UC_ARM64_REG_NZCV, 0)
    def open_mock(uc):
        pointer = uc.reg_read(UC_ARM64_REG_X2)
        calls.append('open')
        if marker_present:
            uc.mem_write(pointer, struct.pack('<Q', CONTEXT+0x500))
        clobber(uc)
        return 0 if marker_present else 1
    def close_mock(uc):
        calls.append('close')
        clobber(uc)
        return 0 if close_ok else 1
    h.mocks = {0x26a860: open_mock, 0x26a8a0: close_mock}
    h.stops[HOOK+4] = 'native_continuation'
    h.run(HOOK)
    return dict(ids=list(struct.unpack('<HH', h.uc.mem_read(cfg+8, 4))), calls=calls,
                registers_preserved=[h.uc.reg_read(r) for r in regs] == before,
                vectors_preserved=[h.uc.reg_read(r) for r in qregs] == vectors,
                flags_preserved=h.uc.reg_read(UC_ARM64_REG_NZCV) == 0xa0000000,
                stack_preserved=h.uc.reg_read(UC_ARM64_REG_SP) == sp,
                code_bytes=length, outcome=h.outcome)
