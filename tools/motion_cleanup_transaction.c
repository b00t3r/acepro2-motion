/* OFFLINE transaction core. Not wired to camera filesystem or firmware.
 *
 * The caller must supply collision-free, capture-specific paths, an already
 * synced/closed combined file, and a verifier that checks the complete JPEG,
 * motion payload, metadata and timestamps. No assumption about rename
 * durability or camera media indexing is made here.
 */
typedef int (*path_op)(void *, const char *);
typedef int (*rename_op)(void *, const char *, const char *);
typedef int (*verify_op)(void *, const char *, const char *, const char *);
typedef int (*barrier_op)(void *);

struct cleanup_ops {
    void *context;
    path_op exists; /* 1 exists, 0 missing, negative error */
    rename_op rename_no_replace; /* 0 success */
    path_op remove; /* 0 success; missing is caller-defined error */
    verify_op verify; /* 0 only for complete verified motion file */
    barrier_op durable; /* 0 only when prior data AND directory changes are durable */
};

enum { CLEAN_OK=0, CLEAN_ABORT=1, CLEAN_RESTORE_NEEDED=2, CLEAN_LEFTOVERS=3 };
static int same(const char *a,const char *b) {
    while (*a && *a==*b) { ++a; ++b; }
    return *a==*b;
}

int motion_cleanup_transaction(struct cleanup_ops *o, const char *original,
        const char *motion, const char *backup, const char *lrv, const char *mp4) {
    if (!o || !o->exists || !o->rename_no_replace || !o->remove || !o->verify || !o->durable ||
        !original || !motion || !backup || !lrv || !mp4) return CLEAN_ABORT;
    const char *paths[5]={original,motion,backup,lrv,mp4};
    for (int i=0;i<5;++i) {
        if (!*paths[i]) return CLEAN_ABORT;
        for (int j=0;j<i;++j) if (same(paths[i],paths[j])) return CLEAN_ABORT;
    }
    /* Any uncertainty, including a stale backup or a missing companion, aborts. */
    if (o->exists(o->context, backup)!=0 || o->exists(o->context, original)!=1 ||
        o->exists(o->context, motion)!=1 || o->exists(o->context, lrv)!=1 ||
        o->exists(o->context, mp4)!=1 || o->verify(o->context,motion,original,lrv))
        return CLEAN_ABORT;
    if (o->rename_no_replace(o->context,original,backup)) return CLEAN_ABORT;
    if (o->rename_no_replace(o->context,motion,original)) {
        return o->rename_no_replace(o->context,backup,original) ? CLEAN_RESTORE_NEEDED : CLEAN_ABORT;
    }
    /* No source is deleted unless reopening at its final name verifies too. */
    if (o->verify(o->context,original,backup,lrv)) return CLEAN_RESTORE_NEEDED;
    /* Re-reading alone can hit cache. Never discard a source without a proven
     * filesystem barrier covering file contents and directory metadata. */
    if (o->durable(o->context)) return CLEAN_RESTORE_NEEDED;
    int errors=0;
    errors |= !!o->remove(o->context,lrv);
    errors |= !!o->remove(o->context,mp4);
    if (errors) return CLEAN_LEFTOVERS;
    errors |= !!o->remove(o->context,backup);
    return errors ? CLEAN_LEFTOVERS : CLEAN_OK;
}

/* Offline recovery: if interrupted after moving the original aside, restore
 * it only when the original name is definitely absent. Never delete or
 * replace anything, and never infer that a combined file is valid. A caller
 * must enumerate only its own capture-specific backup names and separately
 * establish reliable missing-file status and no-replace rename semantics.
 */
int motion_cleanup_restore_original(struct cleanup_ops *o,const char *original,
                                    const char *backup) {
    if (!o || !o->exists || !o->rename_no_replace || !original || !backup ||
        !*original || !*backup || same(original,backup)) return CLEAN_ABORT;
    int original_state=o->exists(o->context,original);
    int backup_state=o->exists(o->context,backup);
    if (original_state==1) return CLEAN_OK;
    if (original_state!=0 || backup_state!=1) return CLEAN_ABORT;
    return o->rename_no_replace(o->context,backup,original) ? CLEAN_RESTORE_NEEDED : CLEAN_OK;
}
