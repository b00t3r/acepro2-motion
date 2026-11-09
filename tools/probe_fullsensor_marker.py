"""Compile a removable-marker guard and exercise it only in emulator memory.

No firmware is built or staged. Mocked file APIs do not show whether storage is
mounted or safe to access at the proposed hook point on a real camera.
"""
import json
import subprocess

from unicorn.arm64_const import UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2
from build_background_prototype import link_regions
from livephoto_harness import BASE, CONTEXT, Harness, ROOT

START, END = 0x2552d00, 0x2552ef0
OBJ = ROOT / 'builds/offline-fullsensor-diagnostic/marker-probe.o'


def build():
    OBJ.parent.mkdir(parents=True, exist_ok=True)
    flags = ['clang', '-target', 'aarch64-none-elf', '-Os', '-ffreestanding',
             '-fno-builtin', '-fno-stack-protector', '-fno-unwind-tables',
             '-fno-asynchronous-unwind-tables', '-fno-jump-tables',
             '-mgeneral-regs-only', '-mno-outline-atomics']
    subprocess.run(flags + ['-c', str(ROOT/'tools/fullsensor_marker_probe.c'), '-o', str(OBJ)], check=True)
    blobs, symbols, relocations = link_regions([(START, END, [OBJ])])
    return blobs[0], symbols, relocations


def run(resource, narrow, marker_present, close_ok=True, null_handle=False):
    blob, symbols, _ = build()
    before = (ROOT/'builds/offline-highres-memory/main_threadx.bin').read_bytes()
    image = bytearray(before)
    if any(image[START-BASE:START-BASE+len(blob)]):
        raise ValueError('Marker experiment overlaps existing code')
    image[START-BASE:START-BASE+len(blob)] = blob
    h = Harness(bytes(image))
    calls = []
    def string(uc, ptr):
        return bytes(uc.mem_read(ptr, 64)).split(b'\0', 1)[0].decode('ascii')
    def open_mock(uc):
        calls.append(['open', string(uc, uc.reg_read(UC_ARM64_REG_X0)),
                      string(uc, uc.reg_read(UC_ARM64_REG_X1))])
        if not marker_present:
            return 1
        handle = 0 if null_handle else CONTEXT+0x100
        uc.mem_write(uc.reg_read(UC_ARM64_REG_X2), handle.to_bytes(8, 'little'))
        return 0
    def close_mock(uc):
        calls.append(['close', uc.reg_read(UC_ARM64_REG_X0)])
        return 0 if close_ok else 1
    h.mocks = {0x26a860: open_mock, 0x26a8a0: close_mock}
    h.uc.reg_write(UC_ARM64_REG_X0, resource)
    h.uc.reg_write(UC_ARM64_REG_X1, narrow)
    h.run(symbols['fullsensor_marker_enabled'])
    return dict(resource=resource, narrow=narrow, marker_present=marker_present,
                close_ok=close_ok, null_handle=null_handle,
                enabled=bool(h.uc.reg_read(UC_ARM64_REG_X0)), calls=calls)


def main():
    cases = [run(227, 1, True), run(227, 1, False), run(227, 1, True, False),
             run(227, 1, True, null_handle=True), run(227, 0, True), run(226, 1, True)]
    result = dict(cases=cases, firmware_changed=False, hardware_tested=False,
        limitation='File access is mocked. Mount timing, thread safety, and startup recovery after SD removal are not tested. The guard is not wired into a firmware package.')
    out = ROOT/'analysis/motion-resolution-audit/fullsensor-marker-offline.json'
    out.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
