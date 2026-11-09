/* Preserve all native scratch registers and flags across each inserted wait.
 * Stack setup displaced at function entry is replayed after restoring SP.
 */
.text
.macro save
 sub sp,sp,#176
 stp x0,x1,[sp,#0]
 stp x2,x3,[sp,#16]
 stp x4,x5,[sp,#32]
 stp x6,x7,[sp,#48]
 stp x8,x9,[sp,#64]
 stp x10,x11,[sp,#80]
 stp x12,x13,[sp,#96]
 stp x14,x15,[sp,#112]
 stp x16,x17,[sp,#128]
 stp x18,x30,[sp,#144]
 mrs x9,nzcv
 str x9,[sp,#160]
.endm
.macro restore
 ldr x9,[sp,#160]
 msr nzcv,x9
 ldp x0,x1,[sp,#0]
 ldp x2,x3,[sp,#16]
 ldp x4,x5,[sp,#32]
 ldp x6,x7,[sp,#48]
 ldp x8,x9,[sp,#64]
 ldp x10,x11,[sp,#80]
 ldp x12,x13,[sp,#96]
 ldp x14,x15,[sp,#112]
 ldp x16,x17,[sp,#128]
 ldp x18,x30,[sp,#144]
 add sp,sp,#176
.endm

.global motion_gallery_guard
motion_gallery_guard:
 save
 bl motion_worker_drain
 restore
 stp x29,x30,[sp,#-0x170]!
 b native_gallery_continue

.global motion_usb_guard
motion_usb_guard:
 save
 bl motion_worker_drain
 restore
 stp x29,x30,[sp,#-0xa0]!
 b native_usb_continue

.global motion_format_guard
motion_format_guard:
 save
 bl motion_worker_drain
 restore
 stp x29,x30,[sp,#-0xa0]!
 b native_format_continue

.global motion_delete_guard
motion_delete_guard:
 save
 bl motion_worker_before_delete
 restore
 cbnz x0,1f
 b native_delete_invalid
1:
 b native_delete_continue

/* These are BL call replacements: native return values must survive. */
.global motion_poweroff_guard
motion_poweroff_guard:
 save
 bl motion_worker_drain
 restore
 b native_poweroff_step

.global motion_shutdown_busy_guard
motion_shutdown_busy_guard:
 save
 bl native_capture_busy
 bl motion_worker_capture_busy
 str x0,[sp,#0]
 restore
 ret
