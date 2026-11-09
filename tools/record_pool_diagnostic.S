// Called on the record task after the stop request, before stream teardown.
.text
.align 2
.global record_pool_diagnostic
record_pool_diagnostic:
    stp x29, x30, [sp, #-64]!
    mov x29, sp
    adrp x9, raw_diag_state
    add x9, x9, :lo12:raw_diag_state
    ldrb w9, [x9]
    cbz w9, 1f
    add x0, sp, #16
    add x1, sp, #24
    add x2, sp, #28
    bl native_get_pool_info
1:
    ldp x29, x30, [sp], #64
    mov w2, #3000
    b record_stop_continue
