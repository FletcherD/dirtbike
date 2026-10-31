/* Planner over the improved core. */
#include "dbplan.h"
#include "db2core.h"
#define BIKE_T Db2Bike
#define GAME_T Db2Game
#define PLANNER_T Db2Planner
#define PFX(name) db2_##name
#define CORE_SUBSTEP db2_game_substep
#define CORE_FRAME db2_game_frame
#define CORE_SHIFT_UP db2_shift_up
#define CORE_SHIFT_DOWN db2_shift_down
#include "dbplan_impl.h"
