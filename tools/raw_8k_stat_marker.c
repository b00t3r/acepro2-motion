/* Read-only, marker-gated filesystem diagnostic for the 2.0.51 firmware.
 * It makes no file modifications; test strings identify one existing marker,
 * one known-missing root path, and an intentionally invalid drive.
 */
typedef unsigned int u32;
typedef unsigned long u64;
typedef void FILE;
#define API(addr,ret,...) ((ret (*)(__VA_ARGS__))(u64)(addr))
#define open_file API(0x26a860,int,const char *,const char *,FILE **)
#define close_file API(0x26a8a0,int,FILE *)
#define log_line API(0x71b880,void,u32,const char *,const char *,const char *,...)
extern int motion_stat_detail(const char *,u32 *);

int fullsensor_marker_enabled(u32 resource,u32 narrow) {
    volatile unsigned char *state=(volatile unsigned char *)0x2552fe0UL;
    FILE *file=0;
    (void)narrow;
    if (resource!=227) return 0;
    *state=0;
    if (open_file("C:\\RAW8K.ENABLE","rb",&file) || !file) return 0;
    if (close_file(file)) return 0;
    *state=1;
    const char *paths[]={"C:\\RAW8K.ENABLE","C:\\CODEX_STAT_MISSING_4271.TST","Z:\\CODEX_STAT_MISSING_4271.TST"};
    for (u32 i=0;i<3;++i) {
        u32 code=0;
        int type=motion_stat_detail(paths[i],&code);
        log_line(4,"FS_DIAG","stat","case=%u class=%u code=%u",i,(u32)type,code);
    }
    return 0;
}
