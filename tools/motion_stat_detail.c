/* OFFLINE prototype: preserve the firmware's two stat failure sources.
 * Error 3 was observed for one absent file on the mounted card; its full
 * meaning and behavior under I/O faults have not been established.
 * Does not change the global wrapper or perform any filesystem mutation.
 */
typedef unsigned int u32;
#define API(addr,ret,...) ((ret (*)(__VA_ARGS__))(unsigned long)(addr))
#define path_convert API(0x14e1780,int,void *,const char *,u32)
#define native_stat API(0x14ebd40,int,const void *,void *)
enum { DETAIL_PRESENT=0, DETAIL_PATH_ERROR=1, DETAIL_FS_ERROR=2, DETAIL_INVALID=3 };

int motion_stat_detail(const char *path,u32 *detail) {
    unsigned char normalized[24]={0};
    unsigned char stat_result[32]={0};
    if (!path || !detail) return DETAIL_INVALID;
    *detail=0;
    int rc=path_convert(normalized,path,1);
    if (rc) { *detail=(u32)rc;return DETAIL_PATH_ERROR; }
    rc=native_stat(normalized,stat_result);
    if (rc) { *detail=(u32)rc;return DETAIL_FS_ERROR; }
    return DETAIL_PRESENT;
}
