/* OFFLINE adapter. This is not wired into the worker or a firmware build.
 * The caller must guarantee an exclusively owned capture and storage state,
 * validated paths, a stable parent directory, and a completed synced output.
 * Error 3 was observed for missing files both at card root and in Camera01;
 * deletion is not authorized until its meaning under I/O failures is known.
 */
typedef unsigned int u32;
typedef unsigned long u64;
#define API(addr,ret,...) ((ret (*)(__VA_ARGS__))(u64)(addr))
#define camera_rename API(0x26aba0,int,const char *,const char *)
/* Bypasses 0x26ab00's worker-drain hook: the worker must not wait on itself. */
#define camera_delete API(0x1077200,int,const char *)
extern int motion_stat_detail(const char *,u32 *);
extern int motion_verify_camera(const char *,const char *,const char *,u32,u32,
                                const unsigned char *,u32,unsigned char *);
typedef int (*path_op)(void *,const char *);
typedef int (*rename_op)(void *,const char *,const char *);
typedef int (*verify_op)(void *,const char *,const char *,const char *);
struct cleanup_ops { void *context; path_op exists; rename_op rename_no_replace;
                     path_op remove; verify_op verify; int (*durable)(void *); };
extern int motion_cleanup_transaction(struct cleanup_ops *,const char *,const char *,
                                      const char *,const char *,const char *);
struct camera_cleanup_context {
    u32 exif_end,jpeg_end,xmp_size;
    const unsigned char *xmp;
    unsigned char *scratch;
};
static int camera_exists(void *ctx,const char *path) {
    u32 code=0; (void)ctx;
    int type=motion_stat_detail(path,&code);
    if (type==0 && code==0) return 1;
    if (type==2 && code==3) return 0;
    return -1;
}
static int rename_no_replace(void *ctx,const char *src,const char *dst) {
    (void)ctx; return camera_rename(src,dst);
}
static int remove_file(void *ctx,const char *path) {
    (void)ctx; return camera_delete(path);
}
static int verify(void *context,const char *motion,const char *jpg,const char *lrv) {
    struct camera_cleanup_context *c=(struct camera_cleanup_context *)context;
    return motion_verify_camera(jpg,lrv,motion,c->exif_end,c->jpeg_end,c->xmp,c->xmp_size,c->scratch);
}
/* No directory-metadata durability operation has been proven on this camera.
 * This deliberately prevents all deletion until such a barrier is verified. */
static int durable_unknown(void *ctx) { (void)ctx; return 1; }
int motion_cleanup_camera(struct camera_cleanup_context *ctx,const char *jpg,
        const char *motion,const char *backup,const char *lrv,const char *mp4) {
    if (!ctx || !ctx->xmp || !ctx->scratch) return 1;
    struct cleanup_ops ops={ctx,camera_exists,rename_no_replace,remove_file,verify,durable_unknown};
    return motion_cleanup_transaction(&ops,jpg,motion,backup,lrv,mp4);
}
