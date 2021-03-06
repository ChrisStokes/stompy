#!/usr/bin/env python
"""
One issue is not knowing the non-halt target during halt (because set_target
is used for both). So legs should have
    target: path to walk when walking
    halted: if halted (don't want)

I want this to be modular so I can write tests that run in
a perfect simulated environment (that doesn't require bullet)
so I can validate changes.

It should also be compatible with bullet to allow for other tests

Things to remove (from body):
    - odometer

Body needs the following:
    - halt/unhalt state
    - current 'walk' target (curve or translate)
    - current 'halt' target (always stop?)
    - enable state
    - feet (for sending plans, attaching callbacks, etc)
    - foot centers (that might be offset)
    - arbitrate leg res state changes (lift -> swing etc)

Leg needs the following
    - halt/unhalt state
    - current 'walk' target [in leg coords]
    - current 'halt' target [in leg coords]
    - enable?
    - foot (for sending plans, attaching callbacks, etc)
    - foot center (possibly offset)
    - joint info (limits, xyz, etc)
    - joint configuration (angles, foot xyz)
    - time since last lift
    - restriction modifier
    - loaded/unloaded height

Supply this a stance plan in body coordinates
it will produce plans in body coordinates
restriction will be updated with foot coordinates

it will produce 'requests' for plans that will be 'accepted'
"""

import math

from .. import consts
from .. import kinematics
from . import leg
from .. import log
from . import odometer
from .. import signaler


parameters = {
    # slow down plan proportional to most restricted leg
    'speed_by_restriction': False,

    # threshold at which a leg is considered 'restricted' and could be lifted
    'r_thresh': 0.4,

    # if restricted by more than this, halt lateral movement
    'r_max': 0.8,

    # allow this many feet up at a time
    'max_feet_up': 1,

    # allow this much slop (in inches) between actual and target body height
    'height_slop': 3.,

    # joint limit restriction shape parameters
    'fields.joint_angle.eps': 0.3,
    'fields.joint_angle.range': 0.9,  # limit movement to ratio of total range
    'fields.joint_angle.inflection': 0.4,

    # calf angle restriction shape parameters
    'fields.calf_angle.eps': 0.3,
    'fields.calf_angle.inflection': 0.4,
    'fields.calf_angle.max': 30,

    # min distance from foot to hip restriction shape parameter
    'fields.min_hip.eps': 0.15,
    # max restriction (and avoid) this many inches from the min_hip_distance
    'fields.min_hip.buffer': 10.0,

    # distance from foot to 'center' restriction shape parameters
    'fields.center.eps': 0.1,
    'fields.center.inflection': 5.,
    'fields.center.radius': 30.,

    # angle (degrees from vertical = 0) of calf when foot at center position
    'target_calf_angle': 10.0,

    # lift foot this many inches off the ground
    'lift_height': 12.0,

    # keep body [hip to thigh pins] this many inches off ground
    'lower_height': -40.0,

    # min/max lower height setting available on slider
    'min_lower_height': -70,
    'max_lower_height': -40,

    # if leg sees < this many lbs, consider unloaded (during lifted)
    'unloaded_weight': 600.,
    
    # if leg sees > this many lbs, consider loaded (during lowering)
    'loaded_weight': 400.,

    # finish swing when within this many inches of target
    'swing_slop': 5.0,

    # ratio of actual step size to maximum step size (1.0)
    'step_ratio': 0.6,

    # if re-locating a leg moves less than many this inches, don't lift
    'min_step_size': 6.0,
}

parameter_metas = {
    'max_feet_up': {'min': 0, 'max': 3},
}


class BodyTarget(object):
    def __init__(self, rotation_center, speed, dz):
        self.rotation_center = rotation_center
        self.speed = speed
        self.dz = dz

    def __eq__(self, other):
        if other is None:
            return False
        return (
            (self.rotation_center == other.rotation_center) and
            (self.speed == other.speed) and
            (self.dz == other.dz))

    def __repr__(self):
        return (
            "BodyTarget(%r, %r, %r)" %
            (self.rotation_center, self.speed, self.dz))


class Body(signaler.Signaler):
    def __init__(self, legs, param):
        """Takes leg controllers"""
        super(Body, self).__init__()
        self.odo = odometer.Odometer()
        self.logger = log.make_logger('Res-Body')
        self.param = param
        self.param.set_param_from_dictionary('res', parameters)
        [
            self.param.set_meta('res.%s' % (k, ), parameter_metas[k])
            for k in parameter_metas]
        self.legs = legs
        self.feet = {}
        self.halted = False
        self.enabled = False
        self.target = None
        inds = sorted(self.legs)
        self.neighbors = {}
        if len(inds) > 1:
            for (i, n) in enumerate(inds):
                if i == 0:
                    self.neighbors[n] = [
                        inds[len(inds) - 1], inds[i+1]]
                elif i == len(inds) - 1:
                    self.neighbors[n] = [inds[i - 1], inds[0]]
                else:
                    self.neighbors[n] = [inds[i - 1], inds[i + 1]]
        for i in self.legs:
            self.feet[i] = leg.Foot(self.legs[i], self.param)
            self.feet[i].on(
                'restriction', lambda s, ln=i: self.on_restriction(s, ln))
            self.feet[i].on(
                'state', lambda s, ln=i: self.on_foot_state(s, ln))
        #print("Feet:", self.feet)
        self.disable()

    def set_halt(self, value):
        self.halted = value
        for i in self.feet:
            self.feet[i].set_halt(value)
        self.odo.enabled = not value
        self.trigger('halt', value)

    def enable(self, foot_states):
        self.logger.debug("enable")
        self.enabled = True
        self.set_halt(False)
        # TODO always reset odometer on enable?
        self.odo.reset()
        # TODO set foot states, target?
        for i in self.feet:
            self.feet[i].reset()

    def offset_foot_centers(self, dx, dy):
        for i in self.feet:
            ldx, ldy, _ = kinematics.body.body_to_leg_rotation(i, dx, dy, 0.)
            # TODO limit to inside limits
            # don't allow -X offset?
            if self.param['limit_center_x_shifts'] and ldx < 0:
                ldx = 0
            self.feet[i].center_offset = (ldx, ldy)

    def calc_stance_speed(self, bxy, mag):
        # scale to pid future time ms
        speed = (
            mag * self.param['speed.foot'] * 
            self.param['speed.scalar'] * consts.PLAN_TICK)

        # find furthest foot
        x, y = bxy
        z = 0.
        mr = None
        for i in self.feet:
            tx, ty, tz = kinematics.body.body_to_leg(i, x, y, z)
            r = tx * tx + ty * ty + tz * tz
            if mr is None or r > mr:
                mr = r
        mr = math.sqrt(mr)
        # account for radius sign
        rspeed = speed / mr
        max_rspeed = (
            self.param['speed.foot'] / self.param['arc_speed_radius'] *
            self.param['speed.scalar'])
        if abs(rspeed) > max_rspeed:
            print("Limiting because of angular speed")
            rspeed = math.copysign(max_rspeed, rspeed)
        # TODO this should adjust speed on times OTHER than set_target
        if self.param['res.speed_by_restriction']:
            rs = self.get_speed_by_restriction()
        else:
            rs = 1.
        return rspeed * rs

    def set_target(self, target=None, update_swing=True):
        if target is None:
            target = self.target
        if not isinstance(target, BodyTarget):
            raise ValueError("Body.set_target requires BodyTarget")
        self.logger.debug({"set_target": (target, update_swing)})
        self.target = target
        if target.dz != 0.0:
            # TODO update stand height
            self.odo.set_target(self.target)  # TODO fix odometer
            pass
        for i in self.feet:
            self.feet[i].set_target(target)
        return

    def disable(self):
        self.logger.debug("disable")
        self.enabled = False
        for i in self.feet:
            self.feet[i].set_state(None)

    def get_speed_by_restriction(self):
        rmax = max([
            self.feet[i].restriction['r'] for i in self.feet
            if self.feet[i].state not in ('swing', 'lower')])
        return max(0., min(1., 1. - rmax))

    def on_foot_state(self, state, leg_number):
        # TODO update 'support' legs
        pass

    def on_restriction(self, restriction, leg_number):
        if not self.enabled:
            return
        # only update odometer when not estopped
        self.odo.update()
        if (
                self.halted and
                (
                    restriction['r'] < self.param['res.r_max'] or
                    self.feet[leg_number] in ('wait', 'swing', 'lower') or
                    restriction['nr'] < restriction['r'])):
            # unhalt?
            maxed = False
            for i in self.feet:
                # make sure foot is not in swing (or lower?)
                #if self.feet[i].state in ('swing', 'lower', 'wait'):
                if self.feet[i].state in ('swing', 'lower', 'wait'):
                    continue
                r = self.feet[i].restriction
                if r['nr'] < r['r']:  # moving to a less restricted spot
                    continue
                if r['r'] > self.param['res.r_max']:
                    maxed = True
            if not maxed:
                self.logger.debug({
                    "unhalt": {
                        'restriction': {
                            i: self.feet[i].restriction for i in self.feet},
                        'states': {
                            i: self.feet[i].state for i in self.feet},
                        #'_pre_halt_target': self._pre_halt_target,
                    }})
                self.set_halt(False)
                return
        if (
                restriction['r'] > self.param['res.r_max'] and
                (not self.halted) and
                (self.feet[leg_number].state not in ('wait', 'swing', 'lower')) and
                restriction['nr'] >= restriction['r']):
            self.set_halt(True)
            return
        # TODO scale stance speed by restriction?
        if (
                (restriction['r'] > self.param['res.r_thresh']) and
                self.feet[leg_number].state == 'stance'):
            #if self.halted:
            #    print(
            #        leg_number, self.feet[leg_number].state,
            #        restriction)
            # lift?
            # check n_feet up
            states = {i: self.feet[i].state for i in self.feet}
            n_up = len([
                s for s in states.values() if s not in ('stance', 'wait')])
            # check if neighbors are up
            if len(self.neighbors.get(leg_number, [])) == 0:
                #if self.halted:
                #    print("halted but no neighbors")
                return
            ns = self.neighbors[leg_number]
            n_states = [states[n] for n in ns]
            ns_up = len([s for s in n_states if s not in ('stance', 'wait')])
            # check if any other feet are restricted:
            last_lift_times = {}
            for ln in self.feet:
                if ln == leg_number:
                    last_lift_times[ln] = self.feet[ln].last_lift_time
                    continue
                if states[ln] not in ('stance', 'wait'):
                    continue
                if (
                        self.feet[ln].restriction is not None and
                        self.feet[ln].restriction['r'] >
                        self.param['res.r_thresh']):
                    # found another restricted foot
                    #other_restricted.append(ln)
                    last_lift_times[ln] = self.feet[ln].last_lift_time
            #if self.halted:
            #    print("last_lift_times: %s" % last_lift_times)
            #    print("ns_up: %s, n_up: %s" % (ns_up, n_up))
            #  yes? pick least recently lifted
            if ns_up == 0 and n_up < self.param['res.max_feet_up']:
                n_can_lift = self.param['res.max_feet_up'] - n_up
                #if self.halted:
                #    print("n_can_lift: %s" % n_can_lift)
                #if self.halted:
                #    self.feet[leg_number].set_state('lift')
                if len(last_lift_times) > n_can_lift:
                    # TODO prefer lifting of feet with
                    # restriction_modifier != 0
                    # only allow this foot if it was moved later than
                    # the other restricted feet
                    ln_by_lt = sorted(
                        last_lift_times, key=lambda ln: last_lift_times[ln])
                    #if self.halted:
                    #    print(
                    #        "ln_by_lt: %s[%s]" %
                    #        (ln_by_lt, ln_by_lt[:n_can_lift+1]))
                    if leg_number in ln_by_lt[:n_can_lift+1]:
                        if self.feet[leg_number].should_lift():
                            self.feet[leg_number].set_state('lift')
                else:
                    #if self.halted:
                    #    print("lift %s" % leg_number)
                    # check if should lift based on swing target being
                    # > N in from current position
                    if self.feet[leg_number].should_lift():
                        self.feet[leg_number].set_state('lift')
