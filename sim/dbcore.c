/* Dirt Bike 4.3 physics core. Each function names the original it ports (PPC address, see
 * re/symbols.txt). Field comments in dbcore.h. Build with -fwrapv. */
#include "dbcore.h"
#include <math.h>
#include <string.h>

int32_t db_sin[360], db_cos[360];

/* InitTrigTables @1000b5e4. The original uses the literal 3.1415927, not M_PI. */
void db_init(void) {
    for (int i = 0; i < 360; i++) {
        double a = (3.1415927 * (double)i) / 180.0;
        db_sin[i] = (int32_t)(1024.0 * sin(a) + 0.5);
        db_cos[i] = (int32_t)(1024.0 * cos(a) + 0.5);
    }
}

/* RandRange @10002df0 */
int32_t db_rand_range(uint32_t *seed, int32_t lo, int32_t hi) {
    int32_t r;
    do {
        *seed = *seed * 0x41c64e6du + 0x3039u;
        r = (int32_t)(((double)(*seed >> 17) / 32768.0) * (double)((hi + 2) - lo) + (double)(lo - 1));
    } while (r < lo || hi < r);
    return r;
}

/* IntDistance @100163f0 */
int32_t db_int_distance(int32_t x1, int32_t y1, int32_t x2, int32_t y2) {
    int32_t d2 = (x1 - x2) * (x1 - x2) + (y1 - y2) * (y1 - y2);
    return (int32_t)sqrt((double)d2);
}

/* AngleOf @10016480: table angle whose (sin,cos) best matches the direction. */
int32_t db_angle_of(int32_t x1, int32_t y1, int32_t x2, int32_t y2) {
    int32_t s = ((y2 - y1) * 1024) / db_int_distance(x1, y1, x2, y2);
    int32_t c = ((x2 - x1) * 1024) / db_int_distance(x1, y1, x2, y2);
    int32_t best = 0, bestErr = 9999;
    for (int32_t i = 0; i < 360; i++) {
        int32_t e = (db_sin[i] < s ? s - db_sin[i] : db_sin[i] - s) + (db_cos[i] < c ? c - db_cos[i] : db_cos[i] - c);
        if (e < bestErr) {
            best = i;
            bestErr = e;
        }
    }
    return best;
}

/* Bike_SetExpertDefaults @100102bc (also the constructor default). */
void db_bike_set_expert(DbBikeParams *p) {
    static const int32_t ratios[6] = {0, 0x84, 0x3d, 0x24, 0x17, 0xe};
    memcpy(p->gear_ratio, ratios, sizeof ratios);
    p->body_mass = 40;
    p->front_spring = 40;
    p->front_travel = 600;
    p->front_rebound = 800;
    p->front_compression = 0x128;
    p->front_radius = 0x167;
    p->front_wheel_mass = 5;
    p->rear_spring = 40;
    p->rear_rebound = 800;
    p->rear_compression = 0x128;
    p->rear_travel = 600;
    p->rear_wheel_mass = 5;
    p->rear_radius = 0x167;
    p->front_dist = 0x23b;
    p->rear_dist = 0x28a;
    p->rake_deg = 0x16;
    p->front_height = 0x32;
    p->rear_height = 0x32;
    p->power = 10000;
    p->brake_power = 2000;
    p->auto_trans = 1; /* set by the original only for local players (type 1) */
}

/* Bike_SetBeginnerDefaults @100103a4 */
void db_bike_set_beginner(DbBikeParams *p) {
    db_bike_set_expert(p);
    p->power = 5000;
    p->front_travel = 400;
    p->rear_travel = 400;
    p->rear_dist = 0x2ee;
    p->front_spring = 0x46;
    p->rear_spring = 0x46;
}

static void place_wheels(DbBike *b) {
    const DbBikeParams *p = &b->p;
    int32_t a = b->angle_deg, fa = b->fork_angle_deg;
    b->fwx = b->x - ((p->front_dist * db_cos[a] - (p->front_height + b->front_ext) * db_sin[fa]) >> 10);
    b->fwy = b->y + ((p->front_dist * db_sin[a] + (p->front_height + b->front_ext) * db_cos[fa]) >> 10);
    b->rwx = b->x + ((p->rear_dist * db_cos[a] + (p->rear_height + b->rear_ext) * db_sin[a]) >> 10);
    b->rwy = b->y - ((p->rear_dist * db_sin[a] - (p->rear_height + b->rear_ext) * db_cos[a]) >> 10);
}

/* Bike_Reset @1001060c */
void db_bike_reset(DbBike *b, const DbTrack *t) {
    const DbBikeParams *p = &b->p;
    b->rear_seg = 500;
    b->front_seg = 500;
    b->gear = 0;
    b->rpm = 0;
    b->engine_started = 0;
    b->throttle = 0;
    b->x = 2500;
    b->y = t->pts[1].y + 2000;
    b->vx = 0;
    b->vy = 0;
    b->angle_deg = 180;
    b->theta_mrad = (b->angle_deg * 0xc45) / 0xb4;
    b->omega = 0;
    b->rear_wheel_spin = 0;
    b->rear_touch = 0;
    b->front_touch = 0;
    b->fork_angle_deg = b->angle_deg - p->rake_deg;
    b->front_ext = p->front_travel;
    b->front_susp_vel = 0;
    b->rear_ext = p->rear_travel;
    b->rear_susp_vel = 0;
    place_wheels(b);
    b->front_r2 = p->front_radius * p->front_radius;
    b->rear_r2 = p->rear_radius * p->rear_radius;
    b->inertia = (p->body_mass * p->front_dist * p->rear_dist) / 1000;
    b->inertia += (p->front_wheel_mass * p->front_dist * p->front_dist) / 1000;
    b->inertia += (p->rear_wheel_mass * p->rear_dist * p->rear_dist) / 1000;
    b->total_mass = p->body_mass + p->front_wheel_mass + p->rear_wheel_mass;
    b->rear_wheel_inertia = (p->rear_wheel_mass * p->rear_radius * p->rear_radius) / 1000;
    int32_t ax = p->front_dist + (((p->front_height + p->front_travel / 2) * db_sin[p->rake_deg]) >> 10);
    int32_t ay = ((p->front_height + p->front_travel / 2) * db_cos[p->rake_deg]) >> 10;
    b->fork_arm_len = db_int_distance(0, 0, ax, ay);
    b->fork_arm_angle = p->rake_deg + db_angle_of(0, 0, ax, ay);
    if (b->fork_arm_angle > 359) b->fork_arm_angle -= 360;
    if (b->fork_arm_angle < 0) b->fork_arm_angle += 360;
    b->max_seg = 0;
    b->laps_done = 0;
    b->finish_time = 0;
    b->finished_ok = 0;
    b->wheel_angle_f = b->wheel_angle_r = b->wheel_rate_f = b->wheel_rate_r = 0;
}

/* Bike_ShiftUp @10011cf4 */
void db_shift_up(DbBike *b, const DbGame *g) {
    if (b->engine_started == 0 || g->state != 2) {
        if (b->engine_started == 0) b->engine_started = 1;
    } else if (b->gear < 5) {
        b->gear++;
    }
}

/* Bike_ShiftDown @10011dd4 */
void db_shift_down(DbBike *b) {
    if (b->gear > 1) b->gear--;
}

/* Bike_AutoShift @10011c18 */
static void auto_shift(DbBike *b, const DbGame *g) {
    if (b->gear == 0) db_shift_up(b, g);
    if (g->state != 0 && b->rear_touch != 0) {
        if (b->gear < 5 && b->rpm > 40000 && b->angle_deg > 170) {
            db_shift_up(b, g);
            if (b->player_type == DB_PLAYER_COMPUTER && b->gear == 2) b->throttle = 0;
        }
        if (b->gear > 1 && b->rpm < 20000) db_shift_down(b);
    }
}

/* vtable slot 0x30. Local: LocalBike_UpdateThrottle @10017cc8 in mouse mode (throttle set
 * directly from input). Computer: ComputerBike_UpdateThrottle @1001395c. */
static void update_throttle(DbBike *b, DbGame *g, int32_t dt) {
    if (b->player_type == DB_PLAYER_COMPUTER) {
        int32_t lean = db_rand_range(&g->rand_seed, 15, 35);
        int32_t rate = b->gear == 1 ? 4 : 1000;
        if ((b->rear_touch == 0 || b->front_touch == 0) && b->angle_deg <= 180 - lean)
            b->throttle -= dt * rate;
        else
            b->throttle += dt * rate;
        if (b->gear == 0) b->throttle = 10000;
    } else {
        b->throttle = b->input_throttle;
    }
    if (b->throttle < 0)
        b->throttle = 0;
    else if (b->throttle > DB_THROTTLE_MAX)
        b->throttle = DB_THROTTLE_MAX;
}

/* Bike_SetFinished @10013648 */
static void set_finished(DbBike *b, int32_t race_time, int32_t ok) {
    b->finish_time = race_time;
    b->finished_ok = ok;
}

/* Wheel/track contact: sums penalty forces from every track vertex inside the wheel circle.
 * Returns 1 if no vertex in the wheel's x-span lies below the wheel centre (wheel is under the
 * surface -> crash). */
static int wheel_contact(const DbTrack *t, int32_t *seg, int32_t wx, int32_t wy, int32_t r, int32_t r2,
                         int32_t *fx, int32_t *fy) {
    int32_t left = wx - r;
    while (left <= t->pts[*seg - 1].x) (*seg)--;
    while (t->pts[*seg].x < left) (*seg)++;
    int under = 1;
    for (int32_t i = *seg; t->pts[i].x < wx + r; i++) {
        if (t->pts[i].y < wy) under = 0;
        if (wy - r < t->pts[i].y) {
            int32_t dx = t->pts[i].x - wx, dy = t->pts[i].y - wy;
            int32_t d2 = dx * dx + dy * dy;
            if (d2 < r2) {
                int32_t d = (int32_t)sqrt((double)d2);
                int32_t pen = (r - d) * 100;
                if (d == 0) d = 1;
                *fx -= (pen * dx) / d;
                *fy -= (pen * dy) / d;
            }
        }
    }
    return under;
}

/* Display-only wheel rotation (the original draws no spokes): a touching wheel rolls with its hub's motion
 * (also backwards); in the air the rear follows the engine-driven spin in gear, otherwise keeps its last rate. */
static void update_wheel_display(DbBike *b, int32_t dt, int32_t ofx, int32_t ofy, int32_t orx, int32_t ory) {
    double dfx = b->fwx - ofx, dfy = b->fwy - ofy, drx = b->rwx - orx, dry = b->rwy - ory;
    if (dt > 0 && b->front_touch && fabs(dfx) < 1000) b->wheel_rate_f = -copysign(hypot(dfx, dfy), dfx) / b->p.front_radius / dt;
    if (dt > 0 && b->rear_touch && fabs(drx) < 1000)
        b->wheel_rate_r = -copysign(hypot(drx, dry), drx) / b->p.rear_radius / dt;
    else if (!b->rear_touch && b->gear != 0)
        b->wheel_rate_r = -(b->rear_wheel_spin / 1e4) * 1e-4;
    b->wheel_angle_f = fmod(b->wheel_angle_f + b->wheel_rate_f * dt, 2 * M_PI);
    b->wheel_angle_r = fmod(b->wheel_angle_r + b->wheel_rate_r * dt, 2 * M_PI);
}

/* Bike_PhysicsStep @10010a18 (vtable slot 0x20). Returns 1 if the bike is out of the race. */
int32_t db_bike_step(DbBike *b, DbGame *g, int32_t dt, const DbTrack *t) {
    const DbBikeParams *p = &b->p;
    if (b->finish_time != 0) return 1;
    int32_t ofx = b->fwx, ofy = b->fwy, orx = b->rwx, ory = b->rwy;

    int32_t ffx = 0, ffy = 0; /* front contact force */
    int front_under = wheel_contact(t, &b->front_seg, b->fwx, b->fwy, p->front_radius, b->front_r2, &ffx, &ffy);
    if (b->max_seg < b->front_seg) b->max_seg = (int16_t)b->front_seg;

    b->fork_angle_deg = b->angle_deg - p->rake_deg;
    if (b->fork_angle_deg < 0) b->fork_angle_deg += 360;
    int32_t fa = b->fork_angle_deg;
    int32_t f_perp = (ffy * db_sin[fa] - ffx * db_cos[fa]) >> 10;
    int32_t damp = b->front_susp_vel < 0 ? b->front_susp_vel * p->front_rebound : b->front_susp_vel * p->front_compression;
    int32_t f_susp = p->front_spring * (b->front_ext - p->front_travel) - damp / 1000;
    b->front_susp_vel += (dt * (((((-ffy * db_cos[fa]) - ffx * db_sin[fa]) >> 10) + f_susp) / 10)) / p->front_wheel_mass;
    b->front_ext -= ((b->front_susp_vel / 10) * dt) / 10000;
    if (b->front_ext < 0) {
        f_susp += ((b->front_susp_vel * p->front_wheel_mass) / dt) * -10;
        b->front_ext = 0;
        b->front_susp_vel = 0;
    } else if (p->front_travel < b->front_ext) {
        f_susp += ((b->front_susp_vel * p->front_wheel_mass) / dt) * -10;
        b->front_ext = p->front_travel;
        b->front_susp_vel = 0;
    }
    int32_t cfa = db_cos[fa], sfa = db_sin[fa];
    int32_t carm = db_cos[b->fork_arm_angle], sarm = db_sin[b->fork_arm_angle];

    int32_t rfx = 0, rfy = 0;
    int rear_under = wheel_contact(t, &b->rear_seg, b->rwx, b->rwy, p->rear_radius, b->rear_r2, &rfx, &rfy);

    if (!front_under && !rear_under) {
        if (p->auto_trans != 0 || b->player_type == DB_PLAYER_COMPUTER) auto_shift(b, g);
        update_throttle(b, g, dt);
        int32_t ratio = p->gear_ratio[b->gear];
        int32_t torque;
        if (b->throttle < 1)
            torque = ((p->brake_power * (b->throttle - b->rpm)) >> 10) * ratio;
        else
            torque = (((b->throttle - b->rpm) * ((p->power * (b->rpm + 10000)) / 53000)) >> 10) * ratio;
        torque >>= 10;
        /* drive force: tangential to the contact normal, magnitude ~torque (x|N|/|N|_1) regardless of how
         * hard the wheel presses; any contact at all gives full traction */
        int32_t nsum = (rfx < 1 ? -rfx : rfx) + (rfy < 1 ? -rfy : rfy);
        b->last_normal = hypot(rfx, rfy);
        b->last_drive = nsum > 0 ? (double)torque * b->last_normal / nsum : 0;
        if (nsum > 0) {
            int32_t tmp = rfy * torque;
            rfy -= (rfx * torque) / nsum;
            rfx += tmp / nsum;
        }
        int32_t a = b->angle_deg;
        int32_t r_perp = (rfy * db_sin[a] - rfx * db_cos[a]) >> 10;
        damp = b->rear_susp_vel < 0 ? b->rear_susp_vel * p->rear_rebound : b->rear_susp_vel * p->rear_compression;
        int32_t r_susp = p->rear_spring * (b->rear_ext - p->rear_travel) - damp / 1000;
        b->rear_susp_vel += (dt * (((-(rfy * db_cos[a] + rfx * db_sin[a]) >> 10) + r_susp) / 10)) / p->rear_wheel_mass;
        b->rear_ext -= ((b->rear_susp_vel / 10) * dt) / 10000;
        if (b->rear_ext < 0) {
            r_susp += ((b->rear_susp_vel * p->rear_wheel_mass) / dt) * -10;
            b->rear_ext = 0;
            b->rear_susp_vel = 0;
        } else if (p->rear_travel < b->rear_ext) {
            r_susp += ((b->rear_susp_vel * p->rear_wheel_mass) / dt) * -10;
            b->rear_ext = p->rear_travel;
            b->rear_susp_vel = 0;
        }
        int32_t ca = db_cos[a], sa = db_sin[a];
        b->vx += (((((f_susp * sfa - f_perp * cfa) >> 10) + ((r_susp * sa - r_perp * ca) >> 10)) / 10) * dt) / b->total_mass;
        b->vy += (((b->total_mass * -98 + ((f_susp * cfa + f_perp * sfa) >> 10) + ((r_susp * ca + r_perp * sa) >> 10)) / 10) * dt) /
                 b->total_mass;
        b->x += ((b->vx / 10) * dt) / 10000;
        b->y += ((b->vy / 10) * dt) / 10000;
        int32_t speed;
        if (b->vx < 1)
            speed = 0;
        else if (b->vy < 1)
            speed = b->vx - b->vy;
        else
            speed = b->vx + b->vy;
        b->front_touch = ffy != 0;
        b->rear_touch = rfy != 0;
        if (b->rear_touch == 0 || b->gear == 0)
            b->rpm = b->throttle;
        else
            b->rpm = (speed * ratio) >> 7;
        int32_t old_spin = b->rear_wheel_spin;
        if (b->gear == 0)
            b->rear_wheel_spin = 0;
        else
            b->rear_wheel_spin = (((b->rpm << 7) / ratio) * 1000) / p->rear_radius;
        /* gyration: reaction to rear wheel spin change */
        b->omega -= ((b->rear_wheel_spin - old_spin) * ((b->rear_wheel_inertia * 3) / 4)) / b->inertia;
        b->omega -= (dt * ((b->fork_arm_len * (((-f_susp * carm) + f_perp * sarm) >> 10) + r_perp * (p->rear_height + b->rear_ext) +
                            p->rear_dist * r_susp) /
                           10)) /
                    b->inertia;
        b->theta_mrad += ((b->omega / 10) * dt) / 10000;
        b->angle_deg = (b->theta_mrad * 0xeab) >> 16;
        if (b->angle_deg < 0) {
            b->angle_deg += 360;
            b->theta_mrad += 0x188b;
        } else if (b->angle_deg > 359) {
            b->angle_deg -= 360;
            b->theta_mrad -= 0x188b;
        }
    }

    if (front_under || rear_under || ((b->angle_deg < 45 || b->angle_deg > 315) && (ffy != 0 || rfy != 0))) {
        b->crashes++;
        if (t->allow_get_back == 0) {
            set_finished(b, g->race_time, 0);
        } else {
            b->gear = 0;
            b->engine_started = 0;
            b->throttle = 0;
            b->rpm = 0;
            b->x = t->pts[b->rear_seg].x;
            b->y = t->pts[b->rear_seg].y + 2000;
            b->vx = 0;
            b->vy = 0;
            b->angle_deg = 180;
            b->theta_mrad = (b->angle_deg * 0xc45) / 0xb4;
            b->omega = 0;
            b->rear_wheel_spin = 0;
        }
    }

    int32_t n = t->n_points;
    if (t->pts[n - 40].x < b->x) {
        b->laps_done++;
        if (b->laps_done >= t->laps) set_finished(b, g->race_time, 1);
        int32_t idx = (b->x - t->pts[n - 100].x) / 50;
        b->x = t->pts[idx].x;
        b->y += t->pts[idx].y - t->pts[n - 40].y;
        b->max_seg = 0;
    } else if (b->x < t->pts[40].x) {
        int32_t idx = b->x / 50;
        b->x = t->pts[n + idx - 100].x;
        b->y += t->pts[n + idx - 100].y - t->pts[0].y;
        b->laps_done--;
    }
    place_wheels(b);
    update_wheel_display(b, dt, ofx, ofy, orx, ory);
    return b->finish_time != 0;
}

/* FUN_1000dc54 (new race) */
void db_game_new_race(DbGame *g, DbBike *bikes, int32_t nb, const DbTrack *t, int32_t frame_units) {
    for (int32_t i = nb - 1; i >= 0; i--) db_bike_reset(&bikes[i], t);
    g->nsub = 1;
    g->acc = 1;
    g->race_started = 0;
    g->race_time = 0;
    g->countdown = 0;
    g->state = 0;
    g->frame_units = frame_units;
}

/* Game_Substep @1000df04. Bikes are iterated last-to-first as in the original. */
int32_t db_game_substep(DbGame *g, DbBike *bikes, int32_t nb, const DbTrack *t) {
    int32_t ret = 0;
    if (g->state == 0) {
        int all = 1;
        for (int32_t i = nb - 1; i >= 0; i--)
            if (bikes[i].engine_started == 0) all = 0;
        if (all) g->state = 1;
    } else if (g->state == 1) {
        if (g->countdown > 1000) {
            g->state = 2;
            g->race_time = 0;
            g->race_started = 1;
        }
    }
    int32_t dt = g->acc / g->nsub;
    g->acc -= dt;
    if (g->race_started) g->race_time += dt / 10;
    if (g->state == 1) g->countdown += dt / 10;
    int all_done = 1;
    for (int32_t i = nb - 1; i >= 0; i--)
        if (db_bike_step(&bikes[i], g, dt, t) == 0) all_done = 0;
    if (nb == 0) all_done = 0;
    if (all_done) ret |= DB_ALL_DONE;
    if (--g->nsub < 1) {
        g->acc += g->frame_units;
        if (g->acc < 51) g->nsub = 1;
        else if (g->acc < 81) g->nsub = 2;
        else if (g->acc < 151) g->nsub = 3;
        else if (g->acc < 241) g->nsub = 4;
        else if (g->acc < 401) g->nsub = 5;
        else if (g->acc < 561) g->nsub = 6;
        else {
            g->nsub = 7;
            if (g->acc > 700) g->acc = 700;
        }
        ret |= DB_FRAME_END;
    }
    return ret;
}

int32_t db_game_frame(DbGame *g, DbBike *bikes, int32_t nb, const DbTrack *t) {
    int32_t r;
    do {
        r = db_game_substep(g, bikes, nb, t);
    } while (!(r & DB_FRAME_END));
    return r & DB_ALL_DONE;
}

/* Track_FixupEnd @1001b3d0 */
void db_track_fixup_end(DbTrack *t, int32_t normalize) {
    int32_t n = t->n_points;
    DbPt *p = t->pts;
    int32_t dx = (db_cos[20] * 50) >> 10, dy = (db_sin[20] * 50) >> 10;
    if (t->laps > 1) {
        int32_t i = n - 100, sgn;
        if (p[0].y < p[n - 100].y) {
            while (i > 0 && dy * ((n - 99) - i) < p[i].y - p[0].y) i--;
            sgn = -1;
        } else {
            while (i > 0 && dy * ((n - 99) - i) < p[0].y - p[i].y) i--;
            sgn = 1;
        }
        for (; i < n - 100; i++) {
            p[i + 1].x = p[i].x + dx;
            p[i + 1].y = p[i].y + sgn * dy;
        }
        for (; i < n - 1; i++) {
            p[i + 1].x = p[i].x + 50;
            p[i + 1].y = p[i].y;
        }
    }
    if (normalize) {
        int32_t miny = p[0].y;
        for (int32_t i = 1; i < n; i++)
            if (p[i].y < miny) miny = p[i].y;
        for (int32_t i = 0; i < n; i++) p[i].y += 300 - miny;
    }
}

/* Track_GenerateFromSeed @1001b698 (random tracks; Beginner's = 0x5b694da2, Expert's = 0x25dd37d2) */
void db_track_generate(DbTrack *t, uint32_t seed) {
    uint32_t s = seed;
    int32_t n = 4000, x = 0, y = 0, idx;
    t->n_points = n;
    t->laps = 3;
    t->allow_get_back = 1;
    for (idx = 0; idx < 100; idx++) {
        x += 50;
        t->pts[idx].x = x;
        t->pts[idx].y = 0;
    }
    float ang = 180.0f;
    while (idx < n - 1) {
        int32_t lim = db_rand_range(&s, 5, 40);
        int32_t len = db_rand_range(&s, 50, 2000);
        float div = (float)db_rand_range(&s, 20, 200);
        if ((n - 1) - idx < len) len = (n - 1) - idx;
        for (int32_t j = 0; j < len; j++) {
            int32_t d;
            if (len / 2 < j)
                d = y < 1 ? db_rand_range(&s, -270, 300) : db_rand_range(&s, -300, 270);
            else
                d = db_rand_range(&s, -300, 300);
            ang = ang + (float)d / div;
            if ((float)(lim + 180) < ang) ang = (float)(lim + 180);
            if (ang < (float)(180 - lim)) ang = (float)(180 - lim);
            x -= (db_cos[(int32_t)ang] * 50) / 1024;
            y -= (db_sin[(int32_t)ang] * 50) / 1024;
            t->pts[idx].x = x;
            t->pts[idx].y = y;
            idx++;
        }
    }
    db_track_fixup_end(t, 1);
}
