/* Improved physics core; see db2core.h for the list of changes vs dbcore.c (the bit-exact port).
 * Structure and equations follow dbcore.c line for line where unchanged; "(orig: ...)" notes mark
 * deliberate departures. */
#include "db2core.h"
#include <math.h>
#include <string.h>

#define DEG (M_PI / 180.0)
#define TWO_PI_MRAD (2000.0 * M_PI)

static Db2Config cfg = {50.0, 100.0, 50.0, 0.15, 1e9, 0.15, 0.10, 0.05, 1, 1, 1};

void db2_default_config(Db2Config *c) {
    Db2Config d = {50.0, 100.0, 50.0, 0.15, 1e9, 0.15, 0.10, 0.05, 1, 1, 1};
    *c = d;
}
void db2_set_config(const Db2Config *c) { cfg = *c; }
void db2_get_config(Db2Config *c) { *c = cfg; }

static double sd(double a) { return sin(a * DEG); }
static double cd(double a) { return cos(a * DEG); }

double db2_ground_y(const DbTrack *t, double x) {
    int32_t lo = 0, hi = t->n_points - 1;
    if (x <= t->pts[lo].x) return t->pts[lo].y;
    if (x >= t->pts[hi].x) return t->pts[hi].y;
    while (hi - lo > 1) {
        int32_t m = (lo + hi) / 2;
        if (t->pts[m].x <= x) lo = m; else hi = m;
    }
    double u = (x - t->pts[lo].x) / (double)(t->pts[hi].x - t->pts[lo].x);
    return t->pts[lo].y + u * (t->pts[hi].y - t->pts[lo].y);
}

static void place_wheels(Db2Bike *b) {
    const DbBikeParams *p = &b->p;
    double a = b->angle_deg, fa = b->fork_angle_deg;
    b->fwx = b->x - (p->front_dist * cd(a) - (p->front_height + b->front_ext) * sd(fa));
    b->fwy = b->y + (p->front_dist * sd(a) + (p->front_height + b->front_ext) * cd(fa));
    b->rwx = b->x + (p->rear_dist * cd(a) + (p->rear_height + b->rear_ext) * sd(a));
    b->rwy = b->y - (p->rear_dist * sd(a) - (p->rear_height + b->rear_ext) * cd(a));
}

void db2_bike_reset(Db2Bike *b, const DbTrack *t) {
    const DbBikeParams *p = &b->p;
    b->rear_seg = b->front_seg = 500;
    b->gear = 0;
    b->rpm = 0;
    b->engine_started = 0;
    b->throttle = 0;
    b->x = 2500;
    b->y = t->pts[1].y + 2000;
    b->vx = b->vy = 0;
    b->theta_mrad = TWO_PI_MRAD / 2;
    b->angle_deg = 180;
    b->omega = 0;
    b->rear_wheel_spin = 0;
    b->rear_touch = b->front_touch = 0;
    b->fork_angle_deg = b->angle_deg - p->rake_deg;
    b->front_ext = p->front_travel;
    b->front_susp_vel = 0;
    b->rear_ext = p->rear_travel;
    b->rear_susp_vel = 0;
    place_wheels(b);
    b->inertia = (p->body_mass * (double)p->front_dist * p->rear_dist + p->front_wheel_mass * (double)p->front_dist * p->front_dist +
                  p->rear_wheel_mass * (double)p->rear_dist * p->rear_dist) / 1000.0;
    b->total_mass = p->body_mass + p->front_wheel_mass + p->rear_wheel_mass;
    b->rear_wheel_inertia = p->rear_wheel_mass * (double)p->rear_radius * p->rear_radius / 1000.0;
    double ax = p->front_dist + (p->front_height + p->front_travel / 2.0) * sd(p->rake_deg);
    double ay = (p->front_height + p->front_travel / 2.0) * cd(p->rake_deg);
    b->fork_arm_len = hypot(ax, ay);
    b->fork_arm_angle = p->rake_deg + atan2(ay, ax) / DEG; /* orig: nearest table degree */
    b->laps_done = 0;
    b->finish_time = 0;
    b->finished_ok = 0;
    b->last_normal = b->last_drive = 0;
    b->wheel_angle_f = b->wheel_angle_r = b->wheel_rate_f = b->wheel_rate_r = 0;
}

void db2_shift_up(Db2Bike *b, const Db2Game *g) {
    if (b->engine_started == 0 || g->state != 2) {
        if (b->engine_started == 0) b->engine_started = 1;
    } else if (b->gear < 5) {
        b->gear++;
    }
}

void db2_shift_down(Db2Bike *b) {
    if (b->gear > 1) b->gear--;
}

static void auto_shift(Db2Bike *b, const Db2Game *g) {
    if (b->gear == 0) db2_shift_up(b, g);
    if (g->state != 0 && b->rear_touch != 0) {
        if (b->gear < 5 && b->rpm > 40000 && b->angle_deg > 170) {
            db2_shift_up(b, g);
            if (b->player_type == DB_PLAYER_COMPUTER && b->gear == 2) b->throttle = 0;
        }
        if (b->gear > 1 && b->rpm < 20000) db2_shift_down(b);
    }
}

static void update_throttle(Db2Bike *b, Db2Game *g, double dt) {
    if (b->player_type == DB_PLAYER_COMPUTER) {
        int32_t lean = db_rand_range(&g->rand_seed, 15, 35);
        double rate = b->gear == 1 ? 4 : 1000;
        if ((b->rear_touch == 0 || b->front_touch == 0) && b->angle_deg <= 180 - lean)
            b->throttle -= dt * rate;
        else
            b->throttle += dt * rate;
        if (b->gear == 0) b->throttle = 10000;
    } else {
        b->throttle = b->input_throttle;
    }
    if (b->throttle < 0) b->throttle = 0;
    else if (b->throttle > DB_THROTTLE_MAX) b->throttle = DB_THROTTLE_MAX;
}

/* Velocity of a wheel hub (0.1 mm/s): body velocity + rotation + suspension extension rate along
 * (s, c) = d(hub)/d(ext). */
static void hub_velocity(const Db2Bike *b, double hx, double hy, double s, double c, double susp_vel, double *vx, double *vy) {
    double rx = hx - b->x, ry = hy - b->y;
    *vx = b->vx + b->omega / 1000.0 * ry - susp_vel * s;
    *vy = b->vy - b->omega / 1000.0 * rx - susp_vel * c;
}

/* Continuous version of the original per-vertex penalty: integrate k/spacing * (R - d) along each
 * segment inside the wheel circle, force directed from the ground point to the wheel centre.
 * Adds contact damping against the hub's approach velocity. Returns the force in *fx, *fy. */
static void wheel_contact(const DbTrack *t, int32_t *seg, double wx, double wy, double r, double hvx, double hvy,
                          double *fx, double *fy) {
    double left = wx - r;
    while (*seg > 1 && left <= t->pts[*seg - 1].x) (*seg)--;
    while (*seg < t->n_points - 1 && t->pts[*seg].x < left) (*seg)++;
    double lam = cfg.contact_k / cfg.contact_spacing;
    double sx = 0, sy = 0;
    if (!cfg.contact_continuous) {
        for (int32_t i = *seg; i < t->n_points && t->pts[i].x < wx + r; i++) {
            double dx = t->pts[i].x - wx, dy = t->pts[i].y - wy, d = hypot(dx, dy);
            if (d >= r) continue;
            double pen = (r - d) * cfg.contact_k, dd = d > 1 ? d : 1;
            sx -= pen * dx / dd;
            sy -= pen * dy / dd;
        }
    }
    for (int32_t i = *seg - 1; cfg.contact_continuous && i + 1 < t->n_points && t->pts[i].x < wx + r; i++) {
        double ax = t->pts[i].x, ay = t->pts[i].y, bx = t->pts[i + 1].x, by = t->pts[i + 1].y;
        double len = hypot(bx - ax, by - ay);
        if (len <= 0) continue;
        double ux = (bx - ax) / len, uy = (by - ay) / len;
        double ta = -((wx - ax) * ux + (wy - ay) * uy); /* A relative to the foot point */
        double fxp = ax - ta * ux, fyp = ay - ta * uy;  /* foot point */
        double nx = wx - fxp, ny = wy - fyp, hh = hypot(nx, ny);
        if (hh >= r) continue;
        double c = sqrt(r * r - hh * hh);
        double t1 = fmax(ta, -c), t2 = fmin(ta + len, c);
        if (t1 >= t2) continue;
        double d1 = hypot(hh, t1), d2 = hypot(hh, t2);
        double fn = hh > 1e-9 ? lam * hh * (r * (asinh(t2 / hh) - asinh(t1 / hh)) - (t2 - t1)) : 0;
        double ft = -lam * ((r * d2 - d2 * d2 / 2) - (r * d1 - d1 * d1 / 2));
        if (hh > 1e-9) {
            sx += fn * nx / hh;
            sy += fn * ny / hh;
        }
        sx += ft * ux;
        sy += ft * uy;
    }
    double mag = hypot(sx, sy);
    if (mag > 0) {
        double nx = sx / mag, ny = sy / mag;
        double fmag = mag - cfg.contact_damping * (hvx * nx + hvy * ny);
        if (fmag < 0) fmag = 0;
        sx = nx * fmag;
        sy = ny * fmag;
    }
    *fx = sx;
    *fy = sy;
}

/* original crash test: no vertex in the wheel's x-span lies below its centre */
static int vertex_under(const DbTrack *t, double wx, double wy, double r) {
    int32_t lo = 0, hi = t->n_points - 1;
    while (hi - lo > 1) {
        int32_t m = (lo + hi) / 2;
        if (t->pts[m].x < wx - r) lo = m; else hi = m;
    }
    for (int32_t i = hi; i < t->n_points && t->pts[i].x < wx + r; i++)
        if (t->pts[i].y < wy) return 0;
    return 1;
}

static void update_wheel_display(Db2Bike *b, const DbTrack *t, double dt, double fvt) {
    if (b->front_touch) b->wheel_rate_f = -(fvt / 10.0) / b->p.front_radius * 1e-4;
    b->wheel_rate_r = -(b->rear_wheel_spin / 1e4) * 1e-4;
    b->wheel_angle_f = fmod(b->wheel_angle_f + b->wheel_rate_f * dt, 2 * M_PI);
    b->wheel_angle_r = fmod(b->wheel_angle_r + b->wheel_rate_r * dt, 2 * M_PI);
    (void)t;
}

int32_t db2_bike_step(Db2Bike *b, Db2Game *g, double dt, const DbTrack *t) {
    const DbBikeParams *p = &b->p;
    if (b->finish_time != 0) return 1;

    b->fork_angle_deg = b->angle_deg - p->rake_deg;
    if (b->fork_angle_deg < 0) b->fork_angle_deg += 360;
    double fa = b->fork_angle_deg, a = b->angle_deg;
    double sfa = sd(fa), cfa = cd(fa), sa = sd(a), ca = cd(a);

    /* orig: wheel is "under" if no vertex in its x-span lies below its centre */
    int front_under, rear_under;
    if (cfg.surface_under) {
        front_under = b->fwy < db2_ground_y(t, b->fwx);
        rear_under = b->rwy < db2_ground_y(t, b->rwx);
    } else {
        front_under = vertex_under(t, b->fwx, b->fwy, p->front_radius);
        rear_under = vertex_under(t, b->rwx, b->rwy, p->rear_radius);
    }

    double hvx, hvy, ffx, ffy, rfx, rfy;
    hub_velocity(b, b->fwx, b->fwy, sfa, cfa, b->front_susp_vel, &hvx, &hvy);
    wheel_contact(t, &b->front_seg, b->fwx, b->fwy, p->front_radius, hvx, hvy, &ffx, &ffy);
    double front_n = hypot(ffx, ffy);
    double f_tan_vel = front_n > 0 ? hvx * (ffy / front_n) - hvy * (ffx / front_n) : 0;

    double f_perp = ffy * sfa - ffx * cfa;
    double damp = b->front_susp_vel < 0 ? b->front_susp_vel * p->front_rebound : b->front_susp_vel * p->front_compression;
    double f_susp = p->front_spring * (b->front_ext - p->front_travel) - damp / 1000;
    b->front_susp_vel += (dt * (((-ffy * cfa) - ffx * sfa + f_susp) / 10)) / p->front_wheel_mass;
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
    double carm = cd(b->fork_arm_angle), sarm = sd(b->fork_arm_angle);

    hub_velocity(b, b->rwx, b->rwy, sa, ca, b->rear_susp_vel, &hvx, &hvy);
    wheel_contact(t, &b->rear_seg, b->rwx, b->rwy, p->rear_radius, hvx, hvy, &rfx, &rfy);
    double rear_n = hypot(rfx, rfy);

    if (!front_under && !rear_under) {
        if (p->auto_trans != 0 || b->player_type == DB_PLAYER_COMPUTER) auto_shift(b, g);
        update_throttle(b, g, dt);
        double ratio = p->gear_ratio[b->gear];
        double torque;
        if (b->throttle < 1)
            torque = p->brake_power * (b->throttle - b->rpm) / 1024.0 * ratio / 1024.0;
        else
            torque = (b->throttle - b->rpm) * (p->power * (b->rpm + 10000) / 53000.0) / 1024.0 * ratio / 1024.0;
        /* orig: drive magnitude = torque*|N|/|N|_1 with no limit (any contact gives full traction) */
        b->last_normal = rear_n;
        b->last_drive = rear_n > 0 ? torque : 0;
        double tnx = 0, tny = 0;
        if (rear_n > 0) {
            tnx = rfy / rear_n;
            tny = -rfx / rear_n;
            double drive = torque, lim = cfg.mu * rear_n;
            if (drive > lim) drive = lim;
            if (drive < -lim) drive = -lim;
            rfx += tnx * drive;
            rfy += tny * drive;
        }
        double r_perp = rfy * sa - rfx * ca;
        damp = b->rear_susp_vel < 0 ? b->rear_susp_vel * p->rear_rebound : b->rear_susp_vel * p->rear_compression;
        double r_susp = p->rear_spring * (b->rear_ext - p->rear_travel) - damp / 1000;
        b->rear_susp_vel += (dt * ((-(rfy * ca + rfx * sa) + r_susp) / 10)) / p->rear_wheel_mass;
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
        b->vx += ((((f_susp * sfa - f_perp * cfa) + (r_susp * sa - r_perp * ca)) / 10) * dt) / b->total_mass;
        b->vy += (((b->total_mass * -98 + (f_susp * cfa + f_perp * sfa) + (r_susp * ca + r_perp * sa)) / 10) * dt) / b->total_mass;
        b->x += ((b->vx / 10) * dt) / 10000;
        b->y += ((b->vy / 10) * dt) / 10000;
        b->front_touch = front_n > 0;
        b->rear_touch = rear_n > 0;

        /* orig: rpm = (vx +- vy)*ratio/128 on the ground, rpm = throttle instantly otherwise */
        double old_spin = b->rear_wheel_spin;
        double v_roll = cfg.rolling_rpm ? hvx * tnx + hvy * tny /* along the ground, 0.1 mm/s */
                                         : (b->vx < 1 ? 0 : b->vx + fabs(b->vy));
        if (b->gear != 0 && b->rear_touch) {
            b->rpm = fmax(0.0, v_roll * ratio / 128.0);
        } else {
            double tau = (b->gear != 0 && b->throttle < 1) ? cfg.tau_brake : (b->throttle > b->rpm ? cfg.tau_up : cfg.tau_down);
            b->rpm += (b->throttle - b->rpm) * (1 - exp(-dt * 1e-4 / tau));
        }
        if (b->gear != 0)
            b->rear_wheel_spin = ((b->rpm * 128.0) / ratio * 1000.0) / p->rear_radius;
        else if (!cfg.rolling_rpm)
            b->rear_wheel_spin = 0;
        else if (b->rear_touch)
            b->rear_wheel_spin = v_roll * 1000.0 / p->rear_radius;
        /* gyration: reaction to rear wheel spin change */
        b->omega -= ((b->rear_wheel_spin - old_spin) * (b->rear_wheel_inertia * 0.75)) / b->inertia;
        b->omega -= (dt * ((b->fork_arm_len * (-f_susp * carm + f_perp * sarm) + r_perp * (p->rear_height + b->rear_ext) +
                            p->rear_dist * r_susp) / 10)) / b->inertia;
        b->theta_mrad += ((b->omega / 10) * dt) / 10000;
        if (b->theta_mrad < 0) b->theta_mrad += TWO_PI_MRAD;
        else if (b->theta_mrad >= TWO_PI_MRAD) b->theta_mrad -= TWO_PI_MRAD;
        b->angle_deg = b->theta_mrad * 180.0 / (1000.0 * M_PI);
    }

    if (front_under || rear_under || ((b->angle_deg < 45 || b->angle_deg > 315) && (front_n > 0 || rear_n > 0))) {
        b->crashes++;
        if (t->allow_get_back == 0) {
            b->finish_time = g->race_time;
            b->finished_ok = 0;
        } else {
            b->gear = 0;
            b->engine_started = 0;
            b->throttle = 0;
            b->rpm = 0;
            b->x = t->pts[b->rear_seg].x;
            b->y = t->pts[b->rear_seg].y + 2000;
            b->vx = b->vy = 0;
            b->angle_deg = 180;
            b->theta_mrad = TWO_PI_MRAD / 2;
            b->omega = 0;
            b->rear_wheel_spin = 0;
        }
    }

    /* orig: x snapped to a track vertex, y offset taken from a different vertex */
    int32_t n = t->n_points;
    double lap_dx = t->pts[n - 100].x - t->pts[0].x, lap_dy = t->pts[n - 100].y - t->pts[0].y;
    if (t->pts[n - 40].x < b->x) {
        b->laps_done++;
        if (b->laps_done >= t->laps) {
            b->finish_time = g->race_time;
            b->finished_ok = 1;
        }
        b->x -= lap_dx;
        b->y -= lap_dy;
    } else if (b->x < t->pts[40].x) {
        b->x += lap_dx;
        b->y += lap_dy;
        b->laps_done--;
    }
    b->fork_angle_deg = b->angle_deg - p->rake_deg;
    if (b->fork_angle_deg < 0) b->fork_angle_deg += 360;
    place_wheels(b);
    update_wheel_display(b, t, dt, f_tan_vel);
    return b->finish_time != 0;
}

void db2_game_new_race(Db2Game *g, Db2Bike *bikes, int32_t nb, const DbTrack *t, int32_t frame_units) {
    for (int32_t i = nb - 1; i >= 0; i--) db2_bike_reset(&bikes[i], t);
    g->state = 0;
    g->race_started = 0;
    g->race_time = 0;
    g->countdown = 0;
    g->frame_units = frame_units;
    g->acc = 0;
}

/* Fixed-step loop (orig: frame time split into 1-7 variable substeps, race time += dt/10 truncated). */
int32_t db2_game_substep(Db2Game *g, Db2Bike *bikes, int32_t nb, const DbTrack *t) {
    int32_t ret = 0;
    double h = cfg.h;
    if (g->acc < h) g->acc += g->frame_units;
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
    g->acc -= h;
    int32_t ms = (int32_t)lround(h / 10);
    if (g->race_started) g->race_time += ms;
    if (g->state == 1) g->countdown += ms;
    int all_done = 1;
    for (int32_t i = nb - 1; i >= 0; i--)
        if (db2_bike_step(&bikes[i], g, h, t) == 0) all_done = 0;
    if (nb == 0) all_done = 0;
    if (all_done) ret |= DB_ALL_DONE;
    if (g->acc < h) ret |= DB_FRAME_END;
    return ret;
}

int32_t db2_game_frame(Db2Game *g, Db2Bike *bikes, int32_t nb, const DbTrack *t) {
    int32_t r;
    do {
        r = db2_game_substep(g, bikes, nb, t);
    } while (!(r & DB_FRAME_END));
    return r & DB_ALL_DONE;
}
