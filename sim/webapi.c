/* Flat C API for the web game (compiled to WebAssembly by tools/build_web.py). One track, one player
 * bike, either physics core. JS fills the track/bike buffers, calls web_new_race, then each animation
 * frame web_set_throttle + web_advance(elapsed dt units) and reads web_state(). */
#include <emscripten/emscripten.h>
#include <string.h>
#include "dbcore.h"
#include "db2core.h"

static DbTrack track;
static DbBikeParams params;
static int physics; /* 0 original, 1 improved */
static DbGame g1;
static DbBike b1;
static Db2Game g2;
static Db2Bike b2;
static double state[32];
static Db2Config cfg2;

/* Indices into web_state() */
enum {
    S_X, S_Y, S_FWX, S_FWY, S_RWX, S_RWY, S_ANGLE, S_GEAR, S_RPM, S_THROTTLE, S_VX, S_VY, S_LAPS, S_CRASHES,
    S_FINISH_TIME, S_FINISHED_OK, S_STATE, S_RACE_TIME, S_COUNTDOWN, S_ENGINE, S_WHEEL_F, S_WHEEL_R,
    S_FRONT_TOUCH, S_REAR_TOUCH, S_FRONT_EXT, S_REAR_EXT, S_N
};

EMSCRIPTEN_KEEPALIVE void web_init(void) {
    db_init();
    db2_get_config(&cfg2);
}

EMSCRIPTEN_KEEPALIVE int32_t *web_track_points(void) { return &track.pts[0].x; }
EMSCRIPTEN_KEEPALIVE void web_track_set(int32_t n, int32_t laps, int32_t allow_get_back) {
    track.n_points = n;
    track.laps = laps;
    track.allow_get_back = allow_get_back;
}
EMSCRIPTEN_KEEPALIVE void web_track_generate(uint32_t seed) { db_track_generate(&track, seed); }
EMSCRIPTEN_KEEPALIVE int32_t web_track_n(void) { return track.n_points; }
EMSCRIPTEN_KEEPALIVE int32_t web_track_laps(void) { return track.laps; }
EMSCRIPTEN_KEEPALIVE int32_t web_track_allow_get_back(void) { return track.allow_get_back; }

/* 27 int32: 20 scalar params (dbcore.h order), 6 gear ratios, auto_trans */
EMSCRIPTEN_KEEPALIVE int32_t *web_bike_params(void) { return &params.front_radius; }
EMSCRIPTEN_KEEPALIVE void web_bike_expert(void) { db_bike_set_expert(&params); }
EMSCRIPTEN_KEEPALIVE void web_bike_beginner(void) { db_bike_set_beginner(&params); }

/* improved-core tunables, Db2Config field order */
EMSCRIPTEN_KEEPALIVE double *web_config(void) { return &cfg2.h; }

EMSCRIPTEN_KEEPALIVE void web_new_race(int32_t use_improved, int32_t frame_units_unused) {
    (void)frame_units_unused;
    physics = use_improved;
    if (physics) {
        db2_set_config(&cfg2);
        memset(&b2, 0, sizeof b2);
        b2.p = params;
        b2.player_type = DB_PLAYER_LOCAL;
        memset(&g2, 0, sizeof g2);
        g2.rand_seed = 1;
        db2_game_new_race(&g2, &b2, 1, &track, 0);
    } else {
        memset(&b1, 0, sizeof b1);
        b1.p = params;
        b1.player_type = DB_PLAYER_LOCAL;
        memset(&g1, 0, sizeof g1);
        g1.rand_seed = 1;
        db_game_new_race(&g1, &b1, 1, &track, 200);
    }
}

EMSCRIPTEN_KEEPALIVE void web_set_throttle(int32_t thr) {
    if (thr < 0) thr = 0;
    if (thr > DB_THROTTLE_MAX) thr = DB_THROTTLE_MAX;
    if (physics) b2.input_throttle = thr; else b1.input_throttle = thr;
}

EMSCRIPTEN_KEEPALIVE void web_shift(int32_t dir) {
    if (physics) {
        if (dir > 0) db2_shift_up(&b2, &g2); else if (dir < 0) db2_shift_down(&b2);
    } else {
        if (dir > 0) db_shift_up(&b1, &g1); else if (dir < 0) db_shift_down(&b1);
    }
}

/* Advance by one frame of `units` dt units (0.1 ms). Returns 1 when the race is over for the bike. */
EMSCRIPTEN_KEEPALIVE int32_t web_advance(int32_t units) {
    if (units < 1) units = 1;
    if (physics) {
        g2.frame_units = units;
        return db2_game_frame(&g2, &b2, 1, &track);
    }
    /* original loop: elapsed time feeds the next frame's substep count (acc capped at 700) */
    g1.frame_units = units;
    return db_game_frame(&g1, &b1, 1, &track);
}

EMSCRIPTEN_KEEPALIVE double *web_state(void) {
    if (physics) {
        double v[S_N] = {b2.x, b2.y, b2.fwx, b2.fwy, b2.rwx, b2.rwy, b2.angle_deg, b2.gear, b2.rpm, b2.throttle,
                         b2.vx, b2.vy, b2.laps_done, b2.crashes, b2.finish_time, b2.finished_ok, g2.state,
                         g2.race_time, g2.countdown, b2.engine_started, b2.wheel_angle_f, b2.wheel_angle_r,
                         b2.front_touch, b2.rear_touch, b2.front_ext, b2.rear_ext};
        memcpy(state, v, sizeof v);
    } else {
        double v[S_N] = {b1.x, b1.y, b1.fwx, b1.fwy, b1.rwx, b1.rwy, b1.angle_deg, b1.gear, b1.rpm, b1.throttle,
                         b1.vx, b1.vy, b1.laps_done, b1.crashes, b1.finish_time, b1.finished_ok, g1.state,
                         g1.race_time, g1.countdown, b1.engine_started, b1.wheel_angle_f, b1.wheel_angle_r,
                         b1.front_touch, b1.rear_touch, b1.front_ext, b1.rear_ext};
        memcpy(state, v, sizeof v);
    }
    return state;
}

EMSCRIPTEN_KEEPALIVE double web_ground_y(double x) { return db2_ground_y(&track, x); }
