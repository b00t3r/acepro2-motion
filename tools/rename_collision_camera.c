/* Offline adapter for firmware 2.0.51. Not installed or linked into firmware.
 * Files and arm marker must be manually staged; the probe is potentially
 * destructive to its two explicitly named disposable test files only.
 */
typedef unsigned int u32;
typedef unsigned long u64;
typedef void FILE;
#define API(addr,ret,...) ((ret (*)(__VA_ARGS__))(u64)(addr))
#define open_file API(0x26a860,int,const char *,const char *,FILE **)
#define close_file API(0x26a8a0,int,FILE *)
#define read_file API(0x26a960,u32,void *,u32,u32,FILE *)
#define rename_file API(0x26aba0,int,const char *,const char *)
#define log_line API(0x71b880,void,u32,const char *,const char *,const char *,...)
typedef int (*rename_fn)(void *,const char *,const char *);
typedef int (*matches_fn)(void *,const char *,const char *);
struct rename_probe_ops { void *ctx; rename_fn rename; matches_fn matches; };
extern int rename_collision_probe(struct rename_probe_ops *,int,int *,int *,int *,int *);

static int matches(void *ctx,const char *path,const char *expected) {
    FILE *f=0; unsigned char buf[40]; u32 n=0; (void)ctx;
    while (expected[n] && n<sizeof(buf)-1) ++n;
    if (expected[n] || open_file(path,"rb",&f) || !f) return -1;
    u32 got=read_file(buf,1,n+1,f);
    if (close_file(f)) return -1;
    if (got!=n) return 0;
    for (u32 i=0;i<n;++i) if (buf[i]!=(unsigned char)expected[i]) return 0;
    return 1;
}
static int do_rename(void *ctx,const char *a,const char *b) {
    (void)ctx; return rename_file(a,b);
}
/* A process-local latch limits a test to one attempt per boot. It does not
 * prevent another attempt after a reboot; remove the marker after testing. */
#define PROBE_STARTED ((unsigned int *)0x2552fe4UL)
void rename_collision_camera_probe(void) {
    int result=-1,source=-1,dest=-1,dest_source=-1;
    struct rename_probe_ops ops={0,do_rename,matches};
    int armed=matches(0,"C:\\CODEX_RENAME_PROBE\\ARM.TST","CODEX-RENAME-ARM-7139")==1;
    if (!armed || __atomic_exchange_n(PROBE_STARTED,1,__ATOMIC_ACQ_REL)) return;
    int attempted=rename_collision_probe(&ops,armed,&result,&source,&dest,&dest_source);
    log_line(4,"RENAME_DIAG","probe","attempt=%d rc=%d src=%d dst=%d dstsrc=%d",
             attempted,result,source,dest,dest_source);
}
