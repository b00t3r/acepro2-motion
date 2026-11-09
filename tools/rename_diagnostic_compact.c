/* Offline-only compact probe for the known 2.0.51 camera calls. */
typedef unsigned int u32;
typedef unsigned long u64;
typedef void FILE;
#define API(a,r,...) ((r (*)(__VA_ARGS__))(u64)(a))
#define open_file API(0x26a860,int,const char *,const char *,FILE **)
#define close_file API(0x26a8a0,int,FILE *)
#define read_file API(0x26a960,u32,void *,u32,u32,FILE *)
#define rename_file API(0x26aba0,int,const char *,const char *)
#define log_line API(0x71b880,void,u32,const char *,const char *,const char *,...)
#define LATCH ((unsigned int *)0x2552fe4UL)
extern const char arm[],src[],dst[],signature[];
static int match(const char *path,char token) {
    FILE *f=0; char b[13];
    if (open_file(path,"rb",&f) || !f) return -1;
    u32 n=read_file(b,1,sizeof(b),f);
    if (close_file(f)) return -1;
    if (n!=11 || b[10]!=token) return 0;
    for (u32 i=0;i<10;++i) if (b[i]!=signature[i]) return 0;
    return 1;
}
int fullsensor_marker_enabled(u32 resource,u32 narrow) {
    (void)narrow;
    if (resource!=227 || match(arm,'A')!=1 ||
        __atomic_exchange_n(LATCH,1,__ATOMIC_ACQ_REL)) return 0;
    if (match(src,'S')!=1 || match(dst,'D')!=1) {
        log_line(4,"RENAME_DIAG","precheck","precheck_failed");return 0;
    }
    int rc=rename_file(src,dst);
    int s=match(src,'S'), d=match(dst,'D'), ds=match(dst,'S');
    log_line(4,"RENAME_DIAG","result","rc=%d src=%d dst=%d dstsrc=%d",rc,s,d,ds);
    return 0;
}
