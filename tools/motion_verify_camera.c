/* OFFLINE ONLY: adapter from the camera's file API to the verifier core.
 * No filenames are changed and no source is deleted. The caller provides
 * checked metadata, independent XMP bytes and at least 8192 bytes scratch.
 */
typedef unsigned int u32;
typedef unsigned long long u64;
typedef void FILE;
#define API(addr,ret,...) ((ret (*)(__VA_ARGS__))(unsigned long)(addr))
#define fs_open API(0x26a860,int,const char *,const char *,FILE **)
#define fs_close API(0x26a8a0,int,FILE *)
#define fs_read API(0x26a960,u32,void *,u32,u32,FILE *)
#define fs_seek API(0x26aa20,int,FILE *,u64,int)
#define fs_tell API(0x26aa40,int,FILE *,u64 *)
typedef int (*seek_fn)(void *,void *,u64);
typedef u32 (*read_fn)(void *,void *,void *,u32);
typedef int (*size_fn)(void *,void *,u64 *);
struct verify_io { void *ctx; seek_fn seek; read_fn read; size_fn size; };
extern int motion_verify_complete(struct verify_io *,void *,void *,void *,u32,u32,
                                  const unsigned char *,u32,unsigned char *);

static int v_seek(void *ctx,void *f,u64 pos) { (void)ctx;return fs_seek(f,pos,0); }
static u32 v_read(void *ctx,void *f,void *buf,u32 size) { (void)ctx;return fs_read(buf,1,size,f); }
static int v_size(void *ctx,void *f,u64 *out) {
    (void)ctx;
    return fs_seek(f,0,2) || fs_tell(f,out) || fs_seek(f,0,0);
}

int motion_verify_camera(const char *jpgpath,const char *lrvpath,const char *outpath,
        u32 exif_end,u32 jpeg_end,const unsigned char *xmp,u32 xmp_size,unsigned char *scratch) {
    FILE *jpg=0,*lrv=0,*out=0;
    int bad=1;
    struct verify_io io={0,v_seek,v_read,v_size};
    if (!jpgpath || !lrvpath || !outpath || !xmp || !scratch) return 1;
    if (fs_open(jpgpath,"rb",&jpg) || !jpg) goto done;
    if (fs_open(lrvpath,"rb",&lrv) || !lrv) goto done;
    if (fs_open(outpath,"rb",&out) || !out) goto done;
    bad=motion_verify_complete(&io,jpg,lrv,out,exif_end,jpeg_end,xmp,xmp_size,scratch);
done:
    if (out && fs_close(out)) bad=1;
    if (lrv && fs_close(lrv)) bad=1;
    if (jpg && fs_close(jpg)) bad=1;
    return bad;
}
