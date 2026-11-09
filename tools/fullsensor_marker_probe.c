/* Offline activation experiment only. Not linked into camera firmware.
 * The marker is read-only. Failure to open or close means disabled. */
typedef unsigned int u32;
typedef unsigned long u64;
typedef void FILE;
#define API(addr, ret, ...) ((ret (*)(__VA_ARGS__))(u64)(addr))
#define open_file API(0x26a860, int, const char *, const char *, FILE **)
#define close_file API(0x26a8a0, int, FILE *)

int fullsensor_marker_enabled(u32 resource, u32 narrow) {
    FILE *file = 0;
    if (resource != 227 || narrow != 1) return 0;
    if (open_file("C:\\FULLSENSOR.ENABLE", "rb", &file)) return 0;
    if (!file) return 0;
    return close_file(file) == 0;
}
