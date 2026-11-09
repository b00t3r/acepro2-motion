/* 2.0.51-only payload. All original media are opened read-only. */
typedef unsigned int u32;
typedef unsigned long u64;
typedef unsigned char u8;
typedef void FILE;
#define API(addr, ret, ...) ((ret (*)(__VA_ARGS__))(u64)(addr))
#define open_file API(0x26a860, int, const char *, const char *, FILE **)
#define close_file API(0x26a8a0, int, FILE *)
#define read_file API(0x26a960, u32, void *, u32, u32, FILE *)
#define write_file API(0x26a9c0, u32, const void *, u32, u32, FILE *)
#define seek_file API(0x26aa20, int, FILE *, u64, int)
#define tell_file API(0x26aa40, int, FILE *, u64 *)
#define rename_file API(0x26aba0, int, const char *, const char *)
#define alloc API(0x25dee0, int, void **, u32)
#define release API(0x25e5e0, int, void *)
#define format API(0x2639a0, int, char *, u64, const char *, ...)
#define live_enabled API(0x403820, int, void)
#define capture_time API(0x403920, u64, void)
#ifdef MOTION_DURABLE_SAVE
#define sync_file API(0x26aa80, int, FILE *)
#endif
#ifdef MOTION_VERIFY_AFTER_SAVE
extern int motion_verify_camera(const char *,const char *,const char *,u32,u32,
                                const unsigned char *,u32,unsigned char *);
#endif
#ifndef MOTION_COPY_BYTES
#define MOTION_COPY_BYTES 4096
#endif

static int copy(FILE *in, FILE *out, u8 *buffer, u32 bytes) {
    while (bytes) {
        u32 n = bytes > MOTION_COPY_BYTES ? MOTION_COPY_BYTES : bytes;
        if (read_file(buffer, 1, n, in) != n || write_file(buffer, 1, n, out) != n) return 0;
        bytes -= n;
    }
    return 1;
}

static u32 size(FILE *f) {
    u64 n = 0;
    if (seek_file(f, 0, 2) || tell_file(f, &n) || seek_file(f, 0, 0) || n > 33554432) return 0;
    return (u32)n;
}

/* Camera JPEGs are baseline. Skip APP thumbnails before scanning entropy EOI. */
static u32 jpeg_end(FILE *f, u8 *buffer, u32 total) {
    u32 pos = 2, previous = 0;
    if (read_file(buffer, 1, 2, f) != 2 || buffer[0] != 255 || buffer[1] != 216) return 0;
    while (pos + 4 <= total) {
        if (read_file(buffer, 1, 4, f) != 4 || buffer[0] != 255) return 0;
        u32 marker = buffer[1], len = ((u32)buffer[2] << 8) | buffer[3];
        if (len < 2 || pos + len + 2 > total) return 0;
        pos += len + 2;
        if (seek_file(f, pos, 0)) return 0;
        if (marker == 218) break;
        if (pos + 4 > total) return 0;
    }
    while (pos < total) {
        u32 n = total - pos > 4096 ? 4096 : total - pos;
        if (read_file(buffer, 1, n, f) != n) return 0;
        for (u32 i = 0; i < n; ++i) {
            if (previous == 255 && buffer[i] == 217) return pos + i + 1;
            previous = buffer[i];
        }
        pos += n;
    }
    return 0;
}

#ifdef MOTION_CAPTURED_TIMESTAMP
__attribute__((noinline)) void motion_save_captured(const char *filename, u64 stamp) {
#else
__attribute__((noinline)) void motion_save(const char *filename, u32 status) {
#endif
    char lrv[128], output[128], temp[128];
    FILE *jpg = 0, *video = 0, *dest = 0, *exists = 0;
    u8 *buffer = 0;
    u32 len = 0, base = 0, ok = 0;
#ifdef MOTION_VERIFY_AFTER_SAVE
    u32 checked_end = 0, checked_exif_end = 0, checked_xmp_size = 0;
#endif
#ifdef MOTION_CAPTURED_TIMESTAMP
    if (!filename) return;
#else
    if (status || !filename || !live_enabled()) return;
#endif
    while (len < 100 && filename[len]) {
        if (filename[len] == '\\') base = len + 1;
        ++len;
    }
    if (len >= 100 || len < 12 || filename[0] != 'C' || filename[1] != ':' ||
        filename[2] != '\\' || filename[base] != 'L' || filename[base+1] != 'I' ||
        filename[base+2] != 'V' || filename[base+3] != '_' ||
        filename[len-4] != '.' || filename[len-3] != 'j' ||
        filename[len-2] != 'p' || filename[len-1] != 'g') return;
    for (u32 i = 0; i < len-4; ++i) lrv[i] = output[i] = temp[i] = filename[i];
    lrv[len-4]='.'; lrv[len-3]='l'; lrv[len-2]='r'; lrv[len-1]='v'; lrv[len]=0;
    const char *suffix = ".MP.jpg";
    for (u32 i = 0; i < 8; ++i) output[len-4+i] = suffix[i];
    suffix = ".MP.tmp";
    for (u32 i = 0; i < 8; ++i) temp[len-4+i] = suffix[i];
    /* Repeat callbacks and a previous interrupted save must not overwrite files. */
    if (!open_file(output, "rb", &exists)) { close_file(exists); return; }
    exists = 0;
    if (!open_file(temp, "rb", &exists)) { close_file(exists); return; }
    if (open_file(filename, "rb", &jpg) || open_file(lrv, "rb", &video)) goto done;
    u32 js = size(jpg), vs = size(video);
#ifndef MOTION_CAPTURED_TIMESTAMP
    u64 stamp = capture_time();
#endif
    if (js < 1024 || vs < 1024 || stamp > 10000 || alloc((void **)&buffer, MOTION_COPY_BYTES + 1024)) goto done;
    u32 end = jpeg_end(jpg, buffer, js);
    if (!end || seek_file(jpg, 0, 0) || read_file(buffer, 1, 12, jpg) != 12) goto done;
#ifdef MOTION_GALLERY_TRAILER
    /* Keep the camera JPEG's native trailer at EOF inside an MP4 free box.
       Preserve the existing JPEG trailer and exact LRV as well. */
    u32 gallery_trailer = js - end;
    if (!gallery_trailer || vs > 33554424 || gallery_trailer > 33554424 - vs) goto done;
    u32 motion_bytes = vs + 8 + gallery_trailer;
#else
    u32 motion_bytes = vs;
#endif
    if (buffer[2] != 255 || buffer[3] != 225 || buffer[6] != 'E' ||
        buffer[7] != 'x' || buffer[8] != 'i' || buffer[9] != 'f' || buffer[10] || buffer[11]) goto done;
    u32 exif_end = 4 + ((u32)buffer[4] << 8) + buffer[5];
    if (exif_end > end || seek_file(jpg, 0, 0)) goto done;
#ifdef MOTION_VERIFY_AFTER_SAVE
    checked_end = end;
    checked_exif_end = exif_end;
#endif
    /* Preserve the exact LRV, including its metadata, matching the phone-tested sample. */
    char *xmp = (char *)buffer + MOTION_COPY_BYTES;
    int n = format(xmp, 1024,
        "http://ns.adobe.com/xap/1.0/|<x:xmpmeta xmlns:x=\"adobe:ns:meta/\">"
        "<rdf:RDF xmlns:rdf=\"http://www.w3.org/1999/02/22-rdf-syntax-ns#\">"
        "<rdf:Description rdf:about=\"\" xmlns:Camera=\"http://ns.google.com/photos/1.0/camera/\" "
        "xmlns:Container=\"http://ns.google.com/photos/1.0/container/\" "
        "xmlns:Item=\"http://ns.google.com/photos/1.0/container/item/\" "
        "Camera:MotionPhoto=\"1\" Camera:MotionPhotoVersion=\"1\" "
        "Camera:MotionPhotoPresentationTimestampUs=\"%llu\">"
        "<Container:Directory><rdf:Seq><rdf:li rdf:parseType=\"Resource\">"
        "<Container:Item Item:Mime=\"image/jpeg\" Item:Semantic=\"Primary\" Item:Padding=\"%u\"/>"
        "</rdf:li><rdf:li rdf:parseType=\"Resource\"><Container:Item Item:Mime=\"video/mp4\" "
        "Item:Semantic=\"MotionPhoto\" Item:Length=\"%u\"/></rdf:li></rdf:Seq>"
        "</Container:Directory></rdf:Description></rdf:RDF></x:xmpmeta>",
        (unsigned long long)(stamp * 1000), js-end, motion_bytes);
    if (n <= 29 || n >= 1024) goto done;
    xmp[28] = 0;
#ifdef MOTION_VERIFY_AFTER_SAVE
    checked_xmp_size = (u32)n;
#endif
    if (open_file(temp, "wb", &dest)) goto done;
    if (!copy(jpg, dest, buffer, exif_end)) goto done;
    buffer[0]=255; buffer[1]=225; buffer[2]=(n+2)>>8; buffer[3]=(n+2)&255;
    if (write_file(buffer, 1, 4, dest) != 4 || write_file(xmp, 1, n, dest) != (u32)n ||
        !copy(jpg, dest, buffer, js-exif_end) || !copy(video, dest, buffer, vs)) goto done;
#ifdef MOTION_GALLERY_TRAILER
    u32 box_size = gallery_trailer + 8;
    buffer[0]=box_size>>24; buffer[1]=box_size>>16; buffer[2]=box_size>>8; buffer[3]=box_size;
    buffer[4]='f'; buffer[5]='r'; buffer[6]='e'; buffer[7]='e';
    if (write_file(buffer, 1, 8, dest) != 8 || seek_file(jpg, end, 0) ||
        !copy(jpg, dest, buffer, gallery_trailer)) goto done;
#endif
#ifdef MOTION_DURABLE_SAVE
    /* Sync while the output handle is still open; a failure must not publish. */
    if (sync_file(dest)) goto done;
#endif
    ok = 1;
done:
    if (dest && close_file(dest)) ok = 0;
#ifdef MOTION_VERIFY_AFTER_SAVE
    if (video && close_file(video)) ok = 0;
    if (jpg && close_file(jpg)) ok = 0;
    if (ok) {
        /* Reconstruct the exact APP1 header in unused scratch immediately
         * before the still-preserved XMP payload. */
        u8 *segment=buffer+MOTION_COPY_BYTES-4;
        segment[0]=255; segment[1]=225;
        segment[2]=(checked_xmp_size+2)>>8; segment[3]=(checked_xmp_size+2)&255;
        if (motion_verify_camera(filename,lrv,temp,checked_exif_end,checked_end,
                                 segment,checked_xmp_size+4,buffer)) ok=0;
    }
#else
    if (video) close_file(video);
    if (jpg) close_file(jpg);
#endif
    if (buffer) release(buffer);
    /* Incomplete outputs remain .tmp; only a fully closed save receives .jpg. */
    if (ok) rename_file(temp, output);
}
