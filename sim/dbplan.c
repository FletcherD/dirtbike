/* Planner over the original (bit-exact) core. */
#include "dbplan.h"
#define BIKE_T DbBike
#define GAME_T DbGame
#define PLANNER_T DbPlanner
#define PFX(name) db_##name
#define CORE_SUBSTEP db_game_substep
#define CORE_FRAME db_game_frame
#define CORE_SHIFT_UP db_shift_up
#define CORE_SHIFT_DOWN db_shift_down
#include "dbplan_impl.h"
