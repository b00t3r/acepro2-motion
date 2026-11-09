/* Offline camera integration prototype. Storage barriers are exported but NOT
 * hooked to native mode transitions yet. Never stage this as firmware as-is.
 */
#include "motion_queue_core.c"
#define API(addr, ret, ...) ((ret (*)(__VA_ARGS__))(unsigned long)(addr))
#define alloc API(0x25dee0,int,void **,u32)
#define sleep_ms API(0x25ef40,int,u32)
#define task_create API(0x25ec00,int,void *)
#define task_resume API(0x1248ca0,int,void *)
#define live_enabled API(0x403820,int,void)
#define capture_time API(0x403920,u64,void)
#define ROOT_SLOT ((struct motion_worker *volatile *)0x2552ff0UL)
#define INITIALIZING ((struct motion_worker *)1UL)

struct motion_worker {
    unsigned char task[0x900];
    struct motion_queue queue;
    u32 ready;
};
extern void motion_save_captured(const char *,u64);

static struct motion_worker *load_worker(void) {
    return __atomic_load_n(ROOT_SLOT,__ATOMIC_ACQUIRE);
}

/* Called only on the camera's serial JPEG-metadata producer path. A concurrent
 * storage barrier waits for INITIALIZING to resolve before inspecting jobs. */
static struct motion_worker *get_worker(void);

int motion_worker_step(struct motion_worker *worker) {
    struct motion_job job;
    int result=motion_queue_take(&worker->queue,&job);
    if (result) return result;
    motion_save_captured(job.filename,job.timestamp_ms);
    while (motion_queue_finish(&worker->queue)==MQ_BUSY) sleep_ms(1);
    return MQ_OK;
}

static void worker_entry(unsigned long arg) {
    struct motion_worker *worker=(struct motion_worker *)arg;
    for (;;) {
        if (motion_worker_step(worker)!=MQ_OK) sleep_ms(10);
    }
}

static struct motion_worker *get_worker(void) {
    struct motion_worker *worker=load_worker();
    if (worker) return worker==INITIALIZING?0:worker;
    struct motion_worker *expected=0;
    if (!__atomic_compare_exchange_n(ROOT_SLOT,&expected,INITIALIZING,0,
                                     __ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE)) return 0;
    if (alloc((void **)&worker,0x11000)) {
        __atomic_store_n(ROOT_SLOT,(struct motion_worker *)0,__ATOMIC_RELEASE);
        return 0;
    }
    /* Zero only state, leaving stack setup to the native task implementation. */
    for (u32 i=0;i<0x1000;++i) ((unsigned char *)worker)[i]=0;
    *(const char **)(worker->task+0x8b0)="MotionPhoto worker";
    *(u32 *)(worker->task+0x8bc)=0; /* Create suspended; publish state first. */
    *(u32 *)(worker->task+0x8c0)=100;
    *(unsigned long *)(worker->task+0x8c8)=(unsigned long)worker;
    *(unsigned long *)(worker->task+0x8d0)=(unsigned long)worker_entry;
    *(unsigned long *)(worker->task+0x8d8)=(unsigned long)worker+0x1000;
    *(u32 *)(worker->task+0x8e0)=0x10000;
    int result=task_create(worker);
    __atomic_store_n(ROOT_SLOT,worker,__ATOMIC_RELEASE);
    if (!result && !task_resume(worker)) __atomic_store_n(&worker->ready,1,__ATOMIC_RELEASE);
    /* A failed partially created native task may still own this block. Retain
     * it, mark not ready, and use synchronous saving rather than freeing it. */
    return worker;
}

int motion_submit(const char *filename,u32 status) {
    if (status || !filename || !live_enabled()) return MQ_INVALID;
    u64 timestamp=capture_time(); /* Snapshot BEFORE returning to capture. */
    struct motion_worker *worker=get_worker();
    if (!worker || !__atomic_load_n(&worker->ready,__ATOMIC_ACQUIRE)) {
        motion_save_captured(filename,timestamp);
        return MQ_OK;
    }
    int result;
    do {
        result=motion_queue_submit(&worker->queue,filename,timestamp);
        if (result==MQ_BUSY || result==MQ_FULL) sleep_ms(1);
    } while (result==MQ_BUSY || result==MQ_FULL);
    return result;
}

/* Mode-transition wiring must quiesce BEFORE filesystem teardown and resume
 * only once native shooting owns storage again. These functions alone do not
 * make the integration safe: no call sites have been patched. */
int motion_worker_quiesce(void) {
    struct motion_worker *worker;
    while ((worker=load_worker())==INITIALIZING) sleep_ms(1);
    if (!worker) return MQ_OK;
    while (motion_queue_close(&worker->queue)==MQ_BUSY) sleep_ms(1);
    u32 pending;
    for (;;) {
        int result=motion_queue_pending(&worker->queue,&pending);
        if (!result && !pending) return MQ_OK;
        sleep_ms(1);
    }
}
int motion_worker_resume(void) {
    struct motion_worker *worker=load_worker();
    if (!worker) return MQ_OK;
    if (worker==INITIALIZING) return MQ_BUSY;
    return motion_queue_resume(&worker->queue);
}

/* Nonblocking extension of the native shutdown capture-busy query. Only the
 * shutdown call sites use this; the shutter keeps its native readiness test. */
u32 motion_worker_capture_busy(u32 native_busy) {
    if (native_busy) return native_busy;
    struct motion_worker *worker=load_worker();
    if (!worker) return 0;
    if (worker==INITIALIZING) return 1;
    u32 pending=0;
    if (motion_queue_pending(&worker->queue,&pending)) return 1;
    return pending!=0;
}

/* Called before native gallery entry, USB start and card formatting. Native
 * capture exclusion remains in charge; this adds the files already queued
 * after JPEG close. It never closes the producer queue or edits capture flags.
 * Callers must not hold a filesystem lock while waiting for the worker. */
void motion_worker_drain(void) {
    while (motion_worker_capture_busy(0)) sleep_ms(1);
}

void motion_worker_before_delete(const char *path) {
    const char *prefix="C:\\DCIM\\";
    if (!path) return;
    for (u32 i=0;prefix[i];++i) if (path[i]!=prefix[i]) return;
    motion_worker_drain();
}
