/* Full-sensor diagnostic activation. This is not a 20 MP implementation. */
typedef unsigned int u32;
typedef unsigned long u64;
typedef void FILE;
#define API(addr, ret, ...) ((ret (*)(__VA_ARGS__))(u64)(addr))
#define open_file API(0x26a860, int, const char *, const char *, FILE **)
#define close_file API(0x26a8a0, int, FILE *)
#define log_line API(0x71b880, void, u32, const char *, const char *, const char *, ...)
int fullsensor_marker_enabled(u32 resource, u32 narrow) {
    FILE *file = 0;
    u32 status = 0;
    if (resource != 227) return 0;
    if (!open_file("C:\\FULLSENSOR.ENABLE", "rb", &file) && file)
        status = close_file(file) ? 2 : 1;
    log_line(4, "FULLSENSOR_DIAG", "marker", "marker status %u", status);
    return status == 1;
}
