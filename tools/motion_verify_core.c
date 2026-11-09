/* Offline verifier for the exact on-camera gallery-compatible file layout.
 * The caller supplies already-open read-only handles and an independent XMP
 * segment generated from checked capture metadata. No filesystem is mutated.
 */
typedef unsigned int u32;
typedef unsigned long long u64;
typedef int (*seek_fn)(void *,void *,u64);
typedef u32 (*read_fn)(void *,void *,void *,u32);
typedef int (*size_fn)(void *,void *,u64 *);
struct verify_io { void *ctx; seek_fn seek; read_fn read; size_fn size; };

static int compare(struct verify_io *io,void *a,void *b,u32 n,unsigned char *buf) {
    while (n) {
        u32 k=n>4096?4096:n;
        if (io->read(io->ctx,a,buf,k)!=k || io->read(io->ctx,b,buf+4096,k)!=k) return 1;
        for (u32 i=0;i<k;++i) if (buf[i]!=buf[4096+i]) return 1;
        n-=k;
    }
    return 0;
}

int motion_verify_complete(struct verify_io *io,void *jpg,void *lrv,void *motion,
        u32 exif_end,u32 jpeg_end,const unsigned char *xmp,u32 xmp_size,unsigned char *buf) {
    u64 js,vs,ms;
    if (!io || !io->seek || !io->read || !io->size || !jpg || !lrv || !motion || !xmp || !buf)
        return 1;
    if (io->size(io->ctx,jpg,&js) || io->size(io->ctx,lrv,&vs) || io->size(io->ctx,motion,&ms)) return 1;
    if (js>33554432 || vs>33554432 || js<1024 || vs<1024 ||
        exif_end<12 || exif_end>jpeg_end || jpeg_end>=js || xmp_size<33 || xmp_size>1030)
        return 1;
    u32 trailer=(u32)js-jpeg_end;
    u64 expected=js+xmp_size+vs+8+trailer;
    if (ms!=expected || io->seek(io->ctx,jpg,0) || io->seek(io->ctx,lrv,0) || io->seek(io->ctx,motion,0)) return 1;
    if (compare(io,jpg,motion,exif_end,buf)) return 1;
    if (io->read(io->ctx,motion,buf,xmp_size)!=xmp_size) return 1;
    for (u32 i=0;i<xmp_size;++i) if (buf[i]!=xmp[i]) return 1;
    if (compare(io,jpg,motion,(u32)js-exif_end,buf) || compare(io,lrv,motion,(u32)vs,buf)) return 1;
    if (io->read(io->ctx,motion,buf,8)!=8) return 1;
    u32 box=((u32)buf[0]<<24)|((u32)buf[1]<<16)|((u32)buf[2]<<8)|buf[3];
    if (box!=trailer+8 || buf[4]!='f' || buf[5]!='r' || buf[6]!='e' || buf[7]!='e') return 1;
    if (io->seek(io->ctx,jpg,jpeg_end) || compare(io,jpg,motion,trailer,buf)) return 1;
    return 0;
}
