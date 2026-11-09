/* Offline background-save queue core. Not installed in a firmware candidate.
 * A camera port must provide task creation, wake/sleep, lifetime management,
 * timestamp snapshotting, storage barriers and a captured-timestamp save API.
 * Never hold this lock across filesystem work or a scheduler call.
 */
typedef unsigned int u32;
typedef unsigned long long u64;
enum { MQ_OK=0, MQ_BUSY=1, MQ_CLOSED=2, MQ_FULL=3, MQ_DUPLICATE=4,
       MQ_INVALID=5, MQ_EMPTY=6, MQ_NOT_DRAINED=7 };
struct motion_job { u64 timestamp_ms; char filename[100]; };
struct motion_queue {
    u32 lock, closing, head, count, active;
    struct motion_job queued[2], running;
};

static int take_lock(struct motion_queue *q) {
    u32 expected=0;
    return __atomic_compare_exchange_n(&q->lock,&expected,1,0,
                                       __ATOMIC_ACQUIRE,__ATOMIC_RELAXED);
}
static void unlock(struct motion_queue *q) {
    __atomic_store_n(&q->lock,0,__ATOMIC_RELEASE);
}
static int equal(const char *a,const char *b) {
    for (u32 i=0;i<100;++i) {
        if (a[i]!=b[i]) return 0;
        if (!a[i]) return 1;
    }
    return 0;
}
static void job_copy(struct motion_job *to,const struct motion_job *from) {
    to->timestamp_ms=from->timestamp_ms;
    for (u32 i=0;i<100;++i) to->filename[i]=from->filename[i];
}

int motion_queue_submit(struct motion_queue *q,const char *name,u64 timestamp) {
    if (!q || !name || timestamp>10000) return MQ_INVALID;
    struct motion_job job={0};
    u32 len=0;
    for (;len<100 && name[len];++len) job.filename[len]=name[len];
    if (!len || len==100) return MQ_INVALID;
    job.timestamp_ms=timestamp;
    if (!take_lock(q)) return MQ_BUSY;
    int result=MQ_OK;
    if (q->closing) result=MQ_CLOSED;
    else if (q->active && equal(q->running.filename,job.filename)) result=MQ_DUPLICATE;
    else {
        for (u32 i=0;i<q->count;++i)
            if (equal(q->queued[(q->head+i)%2].filename,job.filename)) result=MQ_DUPLICATE;
        if (!result && q->count+q->active>=2) result=MQ_FULL;
        if (!result) {
            job_copy(&q->queued[(q->head+q->count)%2],&job);
            ++q->count;
        }
    }
    unlock(q);
    return result;
}

int motion_queue_take(struct motion_queue *q,struct motion_job *job) {
    if (!q || !job) return MQ_INVALID;
    if (!take_lock(q)) return MQ_BUSY;
    int result=MQ_OK;
    if (q->active) result=MQ_BUSY;
    else if (!q->count) result=MQ_EMPTY;
    else {
        job_copy(&q->running,&q->queued[q->head]);
        job_copy(job,&q->running);
        q->head=(q->head+1)%2;
        --q->count;
        q->active=1;
    }
    unlock(q);
    return result;
}

int motion_queue_finish(struct motion_queue *q) {
    if (!q) return MQ_INVALID;
    if (!take_lock(q)) return MQ_BUSY;
    int result=q->active?MQ_OK:MQ_INVALID;
    q->active=0;
    unlock(q);
    return result;
}

/* Closure is sticky until an explicit, fully drained resume. The camera port
 * retries MQ_BUSY with a scheduler yield, and waits for pending == 0 before
 * entering gallery/delete/format, UDisk or shutdown storage teardown. */
int motion_queue_close(struct motion_queue *q) {
    if (!q) return MQ_INVALID;
    if (!take_lock(q)) return MQ_BUSY;
    q->closing=1;
    unlock(q);
    return MQ_OK;
}
int motion_queue_pending(struct motion_queue *q,u32 *pending) {
    if (!q || !pending) return MQ_INVALID;
    if (!take_lock(q)) return MQ_BUSY;
    *pending=q->count+q->active;
    unlock(q);
    return MQ_OK;
}
int motion_queue_resume(struct motion_queue *q) {
    if (!q) return MQ_INVALID;
    if (!take_lock(q)) return MQ_BUSY;
    int result=MQ_NOT_DRAINED;
    if (!q->count && !q->active) { q->closing=0; result=MQ_OK; }
    unlock(q);
    return result;
}
