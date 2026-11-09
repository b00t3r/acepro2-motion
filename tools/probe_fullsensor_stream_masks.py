"""Run native stream mask selection against unmodified format templates.

The meaning of each caller's selector and runtime changes to template fields
are not assumed. These are controlled selector inputs, not camera recordings.
"""
import json
from unicorn import UC_HOOK_CODE
from unicorn.arm64_const import UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2
from audit_motion_resolution import FORMAT_BASE, FORMAT_STRIDE
from livephoto_harness import BASE, CONTEXT, Harness, ROOT, image


def select(index, selector, exact):
    h = Harness((ROOT / 'builds/offline-highres-memory/main_threadx.bin').read_bytes())
    start = FORMAT_BASE - 0x20 + index * FORMAT_STRIDE
    h.uc.mem_write(CONTEXT, image()[start-BASE:start-BASE+FORMAT_STRIDE])
    for reg, value in ((UC_ARM64_REG_X0, CONTEXT), (UC_ARM64_REG_X1, selector),
                       (UC_ARM64_REG_X2, exact)):
        h.uc.reg_write(reg, value)
    h.run(0x28e160)
    return h.uc.reg_read(UC_ARM64_REG_X0) & 0xffffffff


def native_exact_fallback(index):
    """Exercise native exact-8 then exact-9 fallback, with service mocks."""
    h = Harness((ROOT / 'builds/offline-highres-memory/main_threadx.bin').read_bytes())
    start = FORMAT_BASE - 0x20 + index * FORMAT_STRIDE
    h.uc.mem_write(CONTEXT, image()[start-BASE:start-BASE+FORMAT_STRIDE])
    observed, selected = [], []
    def watch(uc, address, size, unused):
        if address in (0x299900, 0x29996c):
            observed.append(uc.reg_read(UC_ARM64_REG_X1))
    def sink(uc):
        selected.append(uc.reg_read(UC_ARM64_REG_X1))
        return 0
    h.uc.hook_add(UC_HOOK_CODE, watch)
    h.mocks = {0x28e120: lambda uc: CONTEXT, 0x797820: lambda uc: 1,
               0x797b40: sink}
    h.run(0x2998a0)
    return dict(format_index=index, selectors_attempted=observed,
                one_based_selected_stream=selected[0], native_list_function_executed=True,
                state_query_mocked_as_enabled=True)


def main():
    cases = [dict(format_index=index, selector=selector, exact=bool(exact),
                  mask=hex(select(index, selector, exact)))
             for index in (16, 42) for selector in (1, 8, 9) for exact in (0, 1)]
    report = dict(cases=cases, native_exact_fallback=[native_exact_fallback(i) for i in (16, 42)],
        native_encoder_start=dict(address='0x27e6c0', log_label='InsMw_Media_EncodeStart',
            selector_calls=['bitwise 8', 'bitwise 0x10000000', 'bitwise 1'],
            behavior='Compares the requested stream mask with the three selected masks. In format 42, bitwise selectors 8 and 1 overlap on stream 1; this differs from format 16.',
            runtime_requested_masks_verified=False),
        hardware_tested=False, firmware_changed=False,
        limitation='Native selector run over static template values; actual caller selector, runtime stream changes, encoding and file generation remain unverified.')
    out = ROOT / 'analysis/motion-resolution-audit/fullsensor-stream-masks.json'
    out.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
