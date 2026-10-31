/* Dirt Bike 4.3 physics core, ported from the PPC binary (see re/ and CLAUDE.md).
 * All arithmetic is 32-bit signed with wraparound (compile with -fwrapv) to match the original. */
#ifndef DBCORE_H
#define DBCORE_H
#include <stdint.h>

#define DB_MAX_PTS 4019 /* (0x7e64 - 0xf8) / 8 */
#define DB_THROTTLE_MAX 58800

typedef struct {
    int32_t x, y;
} DbPt;

typedef struct {
    int32_t n_points;
    int32_t laps;
    int32_t allow_get_back;
    DbPt pts[DB_MAX_PTS];
} DbTrack;

/* The 0x60-byte bike parameter block as stored in files (bike+0x88). */
typedef struct {
    int32_t front_radius, front_spring, front_rebound, front_compression, front_travel,
        front_wheel_mass, front_dist, front_height;
    int32_t rear_radius, rear_spring, rear_rebound, rear_compression, rear_travel,
        rear_wheel_mass, rear_dist, rear_height;
    int32_t rake_deg; /* short in original */
    int32_t body_mass, power, brake_power;
    int32_t gear_ratio[6]; /* shorts in original; [0] = neutral */
    int32_t auto_trans;    /* short in original */
} DbBikeParams;

enum { DB_PLAYER_LOCAL = 1, DB_PLAYER_COMPUTER = 8 };

typedef struct {
    DbBikeParams p;
    int32_t player_type;
    int32_t x, y; /* body CG, mm, +y up */
    int32_t fwx, fwy, rwx, rwy;
    int32_t angle_deg; /* 180 = level, front at +x */
    int32_t engine_started;
    int32_t finish_time; /* nonzero = out of race */
    int32_t max_seg, laps_done, finished_ok;
    int32_t vx, vy;
    int32_t front_susp_vel, rear_susp_vel, front_ext, rear_ext;
    int32_t rpm;
    int32_t front_seg, rear_seg;
    int32_t theta_mrad, omega, rear_wheel_spin;
    int32_t front_r2, rear_r2, inertia, rear_wheel_inertia, total_mass;
    int32_t fork_arm_angle, fork_arm_len, fork_angle_deg;
    int32_t throttle; /* target rpm, 0..58800; 0 = brake */
    int32_t gear;
    int32_t rear_touch, front_touch;
    /* control input for local bikes: throttle applied every substep (mouse mode) */
    int32_t input_throttle;
    /* diagnostics */
    int32_t crashes;
    /* display only (not part of the original): wheel rotation (rad, + = CCW), rad per dt unit */
    double wheel_angle_f, wheel_angle_r, wheel_rate_f, wheel_rate_r;
    /* diagnostics (not part of the original): last rear contact normal force and applied drive force */
    double last_normal, last_drive;
} DbBike;

typedef struct {
    int32_t state;        /* 0 wait for engines, 1 countdown, 2 racing */
    int32_t race_started; /* game+0x6c */
    int32_t race_time;    /* game+0x70, ms of game time (dt/10 per substep) */
    int32_t countdown;    /* game+0x74 */
    int32_t acc;          /* game+0x64, time accumulator in dt units */
    int32_t nsub;         /* game+0x68, substeps left in this frame */
    uint32_t rand_seed;   /* g_randSeed (used by computer bikes) */
    int32_t frame_units;  /* time added to acc per frame: original = elapsed us / 83 */
} DbGame;

void db_init(void);
extern int32_t db_sin[360], db_cos[360];

int32_t db_rand_range(uint32_t *seed, int32_t lo, int32_t hi);
int32_t db_int_distance(int32_t x1, int32_t y1, int32_t x2, int32_t y2);
int32_t db_angle_of(int32_t x1, int32_t y1, int32_t x2, int32_t y2);

void db_bike_set_expert(DbBikeParams *p);
void db_bike_set_beginner(DbBikeParams *p);
void db_bike_reset(DbBike *b, const DbTrack *t);
int32_t db_bike_step(DbBike *b, DbGame *g, int32_t dt, const DbTrack *t);
void db_shift_up(DbBike *b, const DbGame *g);
void db_shift_down(DbBike *b);

/* Game_NewRace: resets game state and every bike. frame_units: see DbGame. */
void db_game_new_race(DbGame *g, DbBike *bikes, int32_t nb, const DbTrack *t, int32_t frame_units);
/* One Game_Substep for nb bikes. Returns DB_ALL_DONE | DB_FRAME_END flags. */
#define DB_ALL_DONE 1
#define DB_FRAME_END 2
int32_t db_game_substep(DbGame *g, DbBike *bikes, int32_t nb, const DbTrack *t);
/* Run substeps until the current frame's time is consumed. Returns 1 if all bikes done. */
int32_t db_game_frame(DbGame *g, DbBike *bikes, int32_t nb, const DbTrack *t);

void db_track_generate(DbTrack *t, uint32_t seed);
void db_track_fixup_end(DbTrack *t, int32_t normalize);

#endif
