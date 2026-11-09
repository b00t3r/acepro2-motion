// Offline-only experiment: use the firmware's existing sampled raw-event log.
// No registration, frame access, capture, allocation, or logging call is added.
.text
.align 2
.global raw_8k_diagnostic_hook
raw_8k_diagnostic_hook:
    stp x9, x10, [sp, #-16]!
    mrs x10, nzcv
    adrp x9, raw_diag_state
    add x9, x9, :lo12:raw_diag_state
    ldrb w9, [x9]
    cbz w9, .Lnormal
    ldrh w9, [x21, #0x16]
    lsr w9, w9, #1
    cmp w9, #3000
    b.hs .Ldebug
.Lnormal:
    msr nzcv, x10
    ldp x9, x10, [sp], #16
    tbnz w0, #2, .Lnative_debug
    b raw_native_normal
.Ldebug:
    msr nzcv, x10
    ldp x9, x10, [sp], #16
.Lnative_debug:
    b raw_native_debug
