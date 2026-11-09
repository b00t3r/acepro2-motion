/* OFFLINE prototype. Never pass camera media paths to this probe. Both files
 * must be created by the operator in a dedicated disposable directory. The
 * caller must verify marker gating, exact file contents, and close handles
 * before invoking it. A successful collision can replace the destination.
 */
typedef int (*rename_fn)(void *, const char *, const char *);
typedef int (*matches_fn)(void *, const char *, const char *);
struct rename_probe_ops { void *ctx; rename_fn rename; matches_fn matches; };

/* Return 0 when a collision was attempted, -1 if preconditions failed.
 * Always inspect both files after the attempt, irrespective of its result.
 */
int rename_collision_probe(struct rename_probe_ops *ops, int armed,
        int *rename_result, int *source_original, int *dest_original,
        int *dest_is_source) {
    const char *source="C:\\CODEX_RENAME_PROBE\\SOURCE.TST";
    const char *dest="C:\\CODEX_RENAME_PROBE\\DEST.TST";
    const char *src_contents="CODEX-RENAME-SOURCE-7139";
    const char *dst_contents="CODEX-RENAME-DEST-7139";
    if (!ops || !ops->rename || !ops->matches || !rename_result ||
        !source_original || !dest_original || !dest_is_source || !armed)
        return -1;
    if (ops->matches(ops->ctx,source,src_contents)!=1 ||
        ops->matches(ops->ctx,dest,dst_contents)!=1) return -1;
    *rename_result=ops->rename(ops->ctx,source,dest);
    *source_original=ops->matches(ops->ctx,source,src_contents);
    *dest_original=ops->matches(ops->ctx,dest,dst_contents);
    *dest_is_source=ops->matches(ops->ctx,dest,src_contents);
    return 0;
}
