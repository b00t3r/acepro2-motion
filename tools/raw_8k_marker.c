/* Runs only in the already-tested Live Photo configuration hook.
 * Absence or I/O error keeps the diagnostic disabled. Never selects a mode.
 */
typedef unsigned int u32;
typedef unsigned long u64;
typedef void FILE;
#define API(addr, ret, ...) ((ret (*)(__VA_ARGS__))(u64)(addr))
#define open_file API(0x26a860, int, const char *, const char *, FILE **)
#define close_file API(0x26a8a0, int, FILE *)
#define log_line API(0x71b880, void, u32, const char *, const char *, const char *, ...)
int fullsensor_marker_enabled(u32 resource, u32 narrow) {
    volatile unsigned char *state=(volatile unsigned char *)0x2552fe0UL;
    FILE *file=0;
    (void)narrow;
    if (resource != 227) return 0;
    *state=0;
    if (!open_file("C:\\RAW8K.ENABLE", "rb", &file) && file) {
        if (!close_file(file)) *state=1;
    }
    log_line(4,"RAW8K_DIAG","marker","armed=%u",(u32)*state);
    return 0;
}
