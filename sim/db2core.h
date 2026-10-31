/* Dirt Bike "improved" physics core: the original model (dbcore.c) transcribed to double precision
 * with physics fixes, keeping the original units, parameters, controls and game rules.
 * Differences from the original (each can be dialled back via Db2Config):
 *  - floating point: no 32-bit overflow, no truncation (slow motion no longer stalls), continuous angles
 *  - fixed timestep h = 50 (5 ms) regardless of frame rate; exact race clock
 *  - ground = polyline segments; contact force is the continuous integral of the original per-vertex
 *    penalty at the original 50 mm density (same average stiffness, no ripple, resolution independent)
 *  - contact damping
 *  - drive force normalised with the Euclidean norm (original |N|_1 made drive 29% weaker on 45 deg
 *    slopes); traction is unlimited like the original by default (optional cap |drive| <= mu*|N|)
 *  - engine/rear wheel spin follows the throttle with a time constant when not driven by the ground
 *    (bounded gyration), rpm from the real rolling speed along the ground
 *  - "under ground" = wheel centre below the track surface; laps wrap by exact translation
 * Units as in the original: mm (+y up), velocities 0.1 mm/s, dt in 0.1 ms, forces in 0.1 N,
 * theta in mrad (angle_deg 180 = level, front toward +x). */
#ifndef DB2CORE_H
#define DB2CORE_H
#include "dbcore.h"

typedef struct {
    double h;               /* fixed substep, dt units (0.1 ms) */
    double contact_k;       /* per-vertex penalty of the original (force per mm overlap) */
    double contact_spacing; /* vertex spacing the original stiffness corresponds to (mm) */
    double contact_damping; /* force per (0.1 mm/s) of normal approach speed */
    double mu;              /* optional traction cap |drive| <= mu*|N|; default 1e9 = unlimited like the original */
    double tau_up;          /* s: free engine spin-up time constant toward a higher throttle */
    double tau_down;        /* s: free engine spin-down time constant toward a lower throttle */
    double tau_brake;       /* s: rear wheel spin-down with brake (throttle 0) while in gear */
    /* model switches (1 = improved, 0 = original behaviour, for ablation) */
    double contact_continuous; /* 0: per-vertex penalty sum (original), 1: segment integral */
    double rolling_rpm;        /* 0: rpm from vx+|vy| (0 if vx<=0), neutral wheel spin 0; 1: rolling speed along ground */
    double surface_under;      /* 0: "under" = no vertex in span below centre; 1: centre below surface */
} Db2Config;

typedef struct {
    DbBikeParams p;
    int32_t player_type;
    int32_t engine_started, finish_time, laps_done, finished_ok;
    int32_t front_seg, rear_seg;
    int32_t gear, rear_touch, front_touch;
    int32_t input_throttle, crashes;
    double x, y, fwx, fwy, rwx, rwy;
    double angle_deg, theta_mrad, omega;
    double vx, vy;
    double front_susp_vel, rear_susp_vel, front_ext, rear_ext;
    double rpm, throttle, rear_wheel_spin;
    double inertia, rear_wheel_inertia, total_mass, fork_arm_angle, fork_arm_len, fork_angle_deg;
    /* diagnostics: last rear contact normal force and requested drive force (0.1 N) */
    double last_normal, last_drive;
    /* display only: wheel rotation (rad, + = counter-clockwise) and rates (rad per dt unit) */
    double wheel_angle_f, wheel_angle_r, wheel_rate_f, wheel_rate_r;
} Db2Bike;

typedef struct {
    int32_t state, race_started, race_time, countdown;
    int32_t frame_units; /* dt units added per frame; substeps of h run while acc >= h */
    uint32_t rand_seed;
    double acc;
} Db2Game;

void db2_default_config(Db2Config *c);
void db2_set_config(const Db2Config *c);
void db2_get_config(Db2Config *c);

void db2_bike_reset(Db2Bike *b, const DbTrack *t);
int32_t db2_bike_step(Db2Bike *b, Db2Game *g, double dt, const DbTrack *t);
void db2_shift_up(Db2Bike *b, const Db2Game *g);
void db2_shift_down(Db2Bike *b);
void db2_game_new_race(Db2Game *g, Db2Bike *bikes, int32_t nb, const DbTrack *t, int32_t frame_units);
int32_t db2_game_substep(Db2Game *g, Db2Bike *bikes, int32_t nb, const DbTrack *t); /* DB_ALL_DONE|DB_FRAME_END */
int32_t db2_game_frame(Db2Game *g, Db2Bike *bikes, int32_t nb, const DbTrack *t);
/* Ground height under x (linear interpolation of the polyline). */
double db2_ground_y(const DbTrack *t, double x);
#endif
