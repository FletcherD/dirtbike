/* Beam-search lookahead planner over the dbcore simulation (single local bike). */
#ifndef DBPLAN_H
#define DBPLAN_H
#include "dbcore.h"
#include "db2core.h"

#define DB_PLAN_MAX_ACTIONS 64

/* Tracking target: a recorded trajectory sample (as stored in high-score replays). */
typedef struct {
    int32_t race_time, x, y, theta_mrad;
} DbTarget;

typedef struct {
    int32_t n_actions;
    int32_t throttle[DB_PLAN_MAX_ACTIONS]; /* throttle held for the step */
    int32_t shift[DB_PLAN_MAX_ACTIONS];    /* -1 down, 0 none, +1 up, applied at step start */
    int32_t frames_per_step;
    int32_t beam_width;
    int32_t bucket_x;     /* mm */
    int32_t bucket_angle; /* deg */
    int32_t bucket_vy;    /* mm/s */
    double vel_weight;    /* seconds of current forward speed added to progress in the score */
    int32_t allow_crash;  /* keep crashed branches (only meaningful if the track allows getting back on) */
    double crash_penalty; /* mm subtracted from the score per crash */
    /* Tracking mode (n_targets > 0): score = -sum of squared errors to the targets, checked after
     * every substep whose race time reaches the next target's time. */
    const DbTarget *targets;
    int32_t n_targets;
    double pos_scale;   /* mm per unit error */
    double theta_scale; /* mrad per unit error */
    /* "reasonable rider": branches whose angle leaves 180 +- max_tilt (deg) at any frame die (0 = off) */
    int32_t max_tilt;
    int32_t max_rpm; /* branches whose rpm exceeds this die (0 = off); forbids the original's overflow exploit */
} DbPlanCfg;

typedef struct DbPlanner DbPlanner;

int64_t db_progress(const DbBike *b, const DbTrack *t);
DbPlanner *db_planner_new(const DbTrack *t, const DbGame *g0, const DbBike *b0, const DbPlanCfg *cfg, int32_t max_steps);
/* Advance the beam by up to nsteps decisions. Returns 1 once the best node has finished the race,
 * -1 if the beam died (every child crashed) or max_steps reached, else 0. */
int32_t db_planner_run(DbPlanner *p, int32_t nsteps);
/* Best node so far: writes its action sequence (returns its length) and end state. */
int32_t db_planner_best(const DbPlanner *p, int32_t *out_actions, DbGame *g_out, DbBike *b_out);
void db_planner_free(DbPlanner *p);

/* Same API over the improved core (db2core). */
typedef struct Db2Planner Db2Planner;
int64_t db2_progress(const Db2Bike *b, const DbTrack *t);
Db2Planner *db2_planner_new(const DbTrack *t, const Db2Game *g0, const Db2Bike *b0, const DbPlanCfg *cfg, int32_t max_steps);
int32_t db2_planner_run(Db2Planner *p, int32_t nsteps);
int32_t db2_planner_best(const Db2Planner *p, int32_t *out_actions, Db2Game *g_out, Db2Bike *b_out);
void db2_planner_free(Db2Planner *p);
#endif
