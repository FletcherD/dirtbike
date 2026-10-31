/* Planner template, included by dbplan.c (original core) and db2plan.c (improved core) with:
 *   BIKE_T, GAME_T, PLANNER_T  types;  PFX(name)  exported-name prefixer;
 *   CORE_SUBSTEP(g,b,n,t), CORE_FRAME(g,b,n,t), CORE_SHIFT_UP(b,g), CORE_SHIFT_DOWN(b).
 * Beam search: every step, each beam node is expanded with every action (held for
 * frames_per_step frames). Children that crash are dropped (or kept and penalised when the track
 * allows getting back on); the rest are bucketed by (progress, angle, vertical speed, gear, start
 * state) keeping the best per bucket for diversity, and the top beam_width by score survive.
 * Score = progress + vel_weight * forward speed; finished nodes rank by finish time. Tracking mode
 * scores by error to a target trajectory. Expansion is OpenMP-parallel. */
#include <stdlib.h>
#include <string.h>

typedef struct {
    GAME_T g;
    BIKE_T b;
    double score;
    int32_t parent, action, done;
    int32_t tidx;  /* next tracking target */
    double err;    /* accumulated tracking error */
} Node;

struct PLANNER_T {
    const DbTrack *t;
    DbPlanCfg cfg;
    int32_t max_steps, step, nbeam, status;
    Node *beam, *kids, *sel;
    int32_t *hist_parent, *hist_action;
    size_t hsize;
    uint64_t *hkeys;
    int32_t *hidx;
};

static int64_t lap_len(const DbTrack *t) { return t->pts[t->n_points - 100].x - t->pts[0].x; }

int64_t PFX(progress)(const BIKE_T *b, const DbTrack *t) { return (int64_t)b->x + (int64_t)b->laps_done * lap_len(t); }

/* Returns 0 running, 1 finished, 2 dead (crashed and not allowed to get back on, or
 * crashed when cfg->allow_crash is 0). */
static int apply_action(Node *n, const DbTrack *t, const DbPlanCfg *cfg, int32_t a) {
    BIKE_T *b = &n->b;
    int32_t c0 = b->crashes;
    if (cfg->shift[a] > 0) CORE_SHIFT_UP(b, &n->g);
    if (cfg->shift[a] < 0) CORE_SHIFT_DOWN(b);
    b->input_throttle = cfg->throttle[a];
    if (cfg->n_targets > 0) {
        for (int32_t f = 0; f < cfg->frames_per_step; f++) {
            int32_t r;
            do {
                r = CORE_SUBSTEP(&n->g, b, 1, t);
                while (n->tidx < cfg->n_targets && n->g.race_started && n->g.race_time >= cfg->targets[n->tidx].race_time) {
                    const DbTarget *q = &cfg->targets[n->tidx++];
                    double ex = (b->x - q->x) / cfg->pos_scale, ey = (b->y - q->y) / cfg->pos_scale;
                    double dth = b->theta_mrad - q->theta_mrad;
                    while (dth > 3141.5) dth -= 6283;
                    while (dth < -3141.5) dth += 6283;
                    double et = dth / cfg->theta_scale;
                    n->err += ex * ex + ey * ey + et * et;
                }
            } while (!(r & DB_FRAME_END));
            if (b->finish_time != 0) break;
        }
        return b->finish_time != 0 && n->tidx < cfg->n_targets ? 2 : (n->tidx >= cfg->n_targets);
    }
    for (int32_t f = 0; f < cfg->frames_per_step; f++) {
        CORE_FRAME(&n->g, b, 1, t);
        if (b->finish_time != 0) break;
        if (b->crashes != c0 && !cfg->allow_crash) break;
        if (cfg->max_tilt > 0 && (b->angle_deg < 180 - cfg->max_tilt || b->angle_deg > 180 + cfg->max_tilt)) return 2;
        if (cfg->max_rpm > 0 && b->rpm > cfg->max_rpm) return 2;
    }
    if (b->finish_time != 0) return b->finished_ok ? 1 : 2;
    if (b->crashes != c0 && !cfg->allow_crash) return 2;
    return 0;
}

static double score(const Node *n, const DbTrack *t, const DbPlanCfg *cfg, int status) {
    const BIKE_T *b = &n->b;
    if (status == 2) return -1e300;
    /* tie-break before the race starts: prefer nodes further along the start sequence */
    double pre = 1e-6 * (n->g.state * 2000 + n->g.countdown + n->b.engine_started * 1000);
    if (cfg->n_targets > 0) return 1e6 * n->tidx - n->err + pre; /* never prefer lagging the schedule */
    if (status == 1) return 1e15 - (double)b->finish_time;
    return (double)PFX(progress)(b, t) + cfg->vel_weight * (double)b->vx / 10.0 - cfg->crash_penalty * (double)b->crashes + pre;
}

static int cmp_desc(const void *a, const void *b) {
    double x = ((const Node *)a)->score, y = ((const Node *)b)->score;
    return x < y ? 1 : x > y ? -1 : 0;
}

static uint64_t bucket_key(const Node *n, const DbTrack *t, const DbPlanCfg *cfg) {
    const BIKE_T *b = &n->b;
    uint64_t k = (uint64_t)(PFX(progress)(b, t) / cfg->bucket_x);
    k = k * 1315423911u + (uint64_t)((int64_t)b->angle_deg / cfg->bucket_angle);
    k = k * 2654435761u + (uint64_t)((int64_t)(b->vy / 10) / cfg->bucket_vy + 100000);
    k = k * 40503u + (uint64_t)b->gear;
    k = k * 31u + (uint64_t)(b->engine_started * 4 + n->g.state);
    return k;
}

PLANNER_T *PFX(planner_new)(const DbTrack *t, const GAME_T *g0, const BIKE_T *b0, const DbPlanCfg *cfg, int32_t max_steps) {
    PLANNER_T *p = calloc(1, sizeof *p);
    int32_t W = cfg->beam_width, A = cfg->n_actions;
    p->t = t;
    p->cfg = *cfg;
    p->max_steps = max_steps;
    p->beam = malloc(sizeof(Node) * W);
    p->kids = malloc(sizeof(Node) * W * A);
    p->sel = malloc(sizeof(Node) * W * A);
    p->hist_parent = malloc(sizeof(int32_t) * (size_t)W * max_steps);
    p->hist_action = malloc(sizeof(int32_t) * (size_t)W * max_steps);
    p->hsize = 1;
    while (p->hsize < (size_t)W * A * 2) p->hsize <<= 1;
    p->hkeys = malloc(sizeof(uint64_t) * p->hsize);
    p->hidx = malloc(sizeof(int32_t) * p->hsize);
    p->nbeam = 1;
    p->beam[0].g = *g0;
    p->beam[0].b = *b0;
    p->beam[0].score = 0;
    p->beam[0].parent = -1;
    p->beam[0].done = 0;
    p->beam[0].tidx = 0;
    p->beam[0].err = 0;
    return p;
}

int32_t PFX(planner_run)(PLANNER_T *p, int32_t nsteps) {
    const DbTrack *t = p->t;
    const DbPlanCfg *cfg = &p->cfg;
    int32_t W = cfg->beam_width, A = cfg->n_actions;
    for (int32_t s = 0; s < nsteps && p->status == 0; s++) {
        if (p->step >= p->max_steps) {
            p->status = -1;
            break;
        }
        int32_t nk = p->nbeam * A;
        Node *beam = p->beam, *kids = p->kids;
#pragma omp parallel for schedule(dynamic, 16)
        for (int32_t k = 0; k < nk; k++) {
            Node *c = &kids[k];
            *c = beam[k / A];
            c->parent = k / A;
            c->action = k % A;
            int st = apply_action(c, t, cfg, c->action);
            c->done = st;
            c->score = score(c, t, cfg, st);
        }
        memset(p->hidx, 0xff, sizeof(int32_t) * p->hsize);
        int32_t nsel = 0;
        for (int32_t k = 0; k < nk; k++) {
            if (kids[k].done == 2) continue;
            uint64_t key = kids[k].done ? (uint64_t)k * 0x9e3779b97f4a7c15ull + 7 : bucket_key(&kids[k], t, cfg);
            size_t h = (size_t)((key * 0x9e3779b97f4a7c15ull) >> 20) & (p->hsize - 1);
            while (p->hidx[h] >= 0 && p->hkeys[h] != key) h = (h + 1) & (p->hsize - 1);
            if (p->hidx[h] < 0) {
                p->hkeys[h] = key;
                p->hidx[h] = k;
            } else if (kids[k].score > kids[p->hidx[h]].score) {
                p->hidx[h] = k;
            }
        }
        for (size_t h = 0; h < p->hsize; h++)
            if (p->hidx[h] >= 0) p->sel[nsel++] = kids[p->hidx[h]];
        if (nsel == 0) {
            p->status = -1;
            break;
        }
        qsort(p->sel, nsel, sizeof(Node), cmp_desc);
        p->nbeam = nsel < W ? nsel : W;
        memcpy(p->beam, p->sel, sizeof(Node) * p->nbeam);
        for (int32_t i = 0; i < p->nbeam; i++) {
            p->hist_parent[(size_t)p->step * W + i] = p->beam[i].parent;
            p->hist_action[(size_t)p->step * W + i] = p->beam[i].action;
        }
        p->step++;
        if (p->beam[0].done == 1) p->status = 1;
    }
    return p->status;
}

int32_t PFX(planner_best)(const PLANNER_T *p, int32_t *out_actions, GAME_T *g_out, BIKE_T *b_out) {
    int32_t W = p->cfg.beam_width, idx = 0;
    for (int32_t s = p->step - 1; s >= 0; s--) {
        out_actions[s] = p->hist_action[(size_t)s * W + idx];
        idx = p->hist_parent[(size_t)s * W + idx];
    }
    *g_out = p->beam[0].g;
    *b_out = p->beam[0].b;
    return p->step;
}

void PFX(planner_free)(PLANNER_T *p) {
    free(p->beam);
    free(p->kids);
    free(p->sel);
    free(p->hist_parent);
    free(p->hist_action);
    free(p->hkeys);
    free(p->hidx);
    free(p);
}
