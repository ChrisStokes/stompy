#!/usr/bin/env python
"""
Much of this is from the StompyLegControl firmware
make sure it is up to date
"""

# plan updates occur every N seconds
#PLAN_TICK = 0.025
#PLAN_TICK = 0.0025
#PLAN_TICK = 0.025
PLAN_TICK = None

ESTOP_OFF = 0
ESTOP_SOFT = 1
ESTOP_HARD = 2
ESTOP_HOLD = 3
ESTOP_SENSOR_LIMIT = 4
ESTOP_FOLLOWING_ERROR = 5
ESTOP_HEARTBEAT = 6
ESTOP_ON = 2
ESTOP_DEFAULT = 2

ESTOP_BY_NUMBER = {
    ESTOP_OFF: 'off',
    ESTOP_SOFT: 'soft',
    ESTOP_HARD: 'hard',
    ESTOP_HOLD: 'hold',
    ESTOP_SENSOR_LIMIT: 'sensor limit',
    ESTOP_FOLLOWING_ERROR: 'following error',
    ESTOP_HEARTBEAT: 'heartbeat',
}

HEARTBEAT_TIMEOUT = 1.0
HEARTBEAT_PERIOD = HEARTBEAT_TIMEOUT / 2.

LEG_UNDEFINED = 0
LEG_FL = 1
LEG_ML = 2
LEG_RL = 3
LEG_RR = 4
LEG_MR = 5
LEG_FR = 6
LEG_FAKE = 7

LEG_NAME_BY_NUMBER = {
    LEG_UNDEFINED: 'Undefined',
    LEG_FL: 'Front-Left',
    LEG_ML: 'Middle-Left',
    LEG_RL: 'Rear-Left',
    LEG_RR: 'Rear-Right',
    LEG_MR: 'Middle-Right',
    LEG_FR: 'Front-Right',
    LEG_FAKE: 'Fake',
}

LEG_NUMBER_BY_NAME = {
    LEG_NAME_BY_NUMBER[k]: k for
    k in LEG_NAME_BY_NUMBER}

MIDDLE_LEGS = (LEG_ML, LEG_MR)
REAL_LEGS = (LEG_FL, LEG_ML, LEG_RL, LEG_RR, LEG_MR, LEG_FR)
REAL_LEG_NAMES = tuple([LEG_NAME_BY_NUMBER[N] for N in REAL_LEGS])

PLAN_STOP_MODE = 0
PLAN_VELOCITY_MODE = 1
PLAN_ARC_MODE = 2
PLAN_TARGET_MODE = 3
PLAN_MATRIX_MODE = 4

PLAN_MODE_BY_NUMBER = {
    PLAN_STOP_MODE: 'stop',
    PLAN_VELOCITY_MODE: 'velocity',
    PLAN_ARC_MODE: 'arc',
    PLAN_TARGET_MODE: 'target',
}

PLAN_MODE_BY_NAME = {
    PLAN_MODE_BY_NUMBER[k]: k for
    k in PLAN_MODE_BY_NUMBER}

PLAN_SENSOR_FRAME = 0
PLAN_JOINT_FRAME = 1
PLAN_LEG_FRAME = 2
PLAN_BODY_FRAME = 3

PLAN_FRAMES_BY_NUMBER = {
    PLAN_SENSOR_FRAME: 'sensor',
    PLAN_JOINT_FRAME: 'joint',
    PLAN_LEG_FRAME: 'leg',
    PLAN_BODY_FRAME: 'body',
}

PLAN_FRAMES_BY_NAME = {
    PLAN_FRAMES_BY_NUMBER[k]: k for
    k in PLAN_FRAMES_BY_NUMBER}

HIP_JOINT_INDEX = 0
THIGH_JOINT_INDEX = 1
KNEE_JOINT_INDEX = 2

JOINT_INDEX_BY_NAME = {
    'hip': HIP_JOINT_INDEX,
    'thigh': THIGH_JOINT_INDEX,
    'knee': KNEE_JOINT_INDEX,
}

JOINT_NAMES = ('hip', 'thigh', 'knee')

JOINT_NAME_BY_INDEX = {
    JOINT_INDEX_BY_NAME[k]: k for
    k in JOINT_INDEX_BY_NAME}

GEOM_CYLINDER_MIN = 0
GEOM_CYLINDER_MAX = 1
GEOM_TRIANGLE_A = 2
GEOM_TRIANGLE_B = 3
GEOM_ZERO_ANGLE = 4
GEOM_REST_ANGLE = 5
GEOM_LENGTH = 6
GEOM_MIN_ANGLE = 7
GEOM_MAX_ANGLE = 8

GEOM_INDEX_BY_NAME = {
    'cylinder_min': GEOM_CYLINDER_MIN,
    'cylinder_max': GEOM_CYLINDER_MAX,
    'triangle_a': GEOM_TRIANGLE_A,
    'triangle_b': GEOM_TRIANGLE_B,
    'zero_angle': GEOM_ZERO_ANGLE,
    'rest_angle': GEOM_REST_ANGLE,
    'length': GEOM_LENGTH,
    'min_angle': GEOM_MIN_ANGLE,
    'max_angle': GEOM_MAX_ANGLE,
}

GEOM_NAME_BY_INDEX = {
    GEOM_INDEX_BY_NAME[k]: k for
    k in GEOM_INDEX_BY_NAME}
