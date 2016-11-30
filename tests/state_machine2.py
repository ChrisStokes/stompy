#!/usr/bin/env python

import actionlib
import rospy
import smach

import stompy
import stompy.ros
import stompy.gaits.restriction
#import stompy.planners.legs
# import stompy.sensors.joints


class Startup(smach.State):
    def __init__(self):
        smach.State.__init__(
            self, outcomes=['ready', ])
            # input_keys=[],
            #output_keys=['load', ],)

    def execute(self, userdata):
        # wait for joint data
        while stompy.sensors.joints.joints is None:
            rospy.sleep(0.05)
        rospy.sleep(1.)
        ## check if on dollies
        #load = 0.
        #for leg in stompy.info.legs:
        #    load += stompy.sensors.legs.legs[leg]['load']
        ## return if loaded/not-loaded
        #userdata.load = load
        # select action by mode
        while stompy.ros.joystick.mode is None:
            print("Waiting on joystick input...")
            rospy.sleep(0.5)
        return "ready"


class ModeTransition(smach.State):
    def __init__(self):
        smach.State.__init__(
            self, outcomes=[
                'moveleg', 'movebody', 'positionlegs', 'error', 'walk'])

    def execute(self, userdata):
        mode = stompy.ros.joystick.mode
        if mode < 12:
            return 'moveleg'
        if mode in (32, 33):
            return 'movebody'
        if mode == 34:
            return 'positionlegs'
        if mode == 35:
            return 'walk'
        return 'error'


class MoveLeg(smach.State):
    def __init__(self):
        smach.State.__init__(
            self, outcomes=['newmode', 'error'])

    def execute(self, userdata):

        legs_by_mode = ('rl', 'ml', 'fl', 'fr', 'mr', 'rr')

        def move_leg(data, state={}):
            mode = stompy.ros.joystick.mode
            # determine which leg to move
            if mode < 6:  # angles
                leg = legs_by_mode[mode]
                move_type = 'angle'
            elif mode < 12:  # foot
                leg = legs_by_mode[mode - 6]
                move_type = 'foot'
            else:
                return
            # check if a previous message had been sent to a different leg
            if 'leg' in state and state['leg'] != leg:
                # if so, cancel it as the leg changed
                stompy.ros.planner.plans[state['leg']].set_stop()
                del state['leg']
            movement = False
            for a in data.axes:
                if abs(a) > 0.01:
                    movement = True
                    break
            if not movement:
                stompy.ros.planner.plans[leg].set_stop()
                if 'leg' in state:
                    del state['leg']
                return
            else:
                # append new trajectory to old?
                if move_type == 'foot':
                    vector = [
                        data.axes[0] / 10.,
                        data.axes[1] / 10.,
                        data.axes[2] / 10.]
                    stompy.ros.planner.plans[leg].set_velocity(
                        vector, stompy.ros.planner.FOOT_FRAME)
                else:  # angles
                    vector = [
                        data.axes[0] / 5.,
                        data.axes[1] / 5.,
                        data.axes[2] / 5.]
                    stompy.ros.planner.plans[leg].set_velocity(
                        vector, stompy.ros.planner.JOINT_FRAME)
                state['leg'] = leg

        # attach callback to joystick
        cbid = stompy.ros.joystick.callbacks.register(
            move_leg)
        # sleep and watch for new modes
        while True:
            rospy.sleep(0.1)
            stompy.ros.planner.update()
            if not (stompy.ros.joystick.mode < 12):
                stompy.ros.planner.set_stop()
                break
        # unregister callback
        stompy.ros.joystick.callbacks.unregister(cbid)
        # transition to new mode
        return "newmode"


class MoveBody(smach.State):
    def __init__(self):
        smach.State.__init__(
            self, outcomes=['newmode', 'error'])

    def execute(self, userdata):

        def move_body(data, state={}):
            mode = stompy.ros.joystick.mode
            if mode not in (32, 33):
                return
            movement = False
            for a in data.axes:
                if abs(a) > 0.01:
                    movement = True
                    break
            if not movement:
                stompy.ros.planner.set_stop()
                return
            if mode == 32:  # translate
                vector = [
                    data.axes[0] / 10.,
                    data.axes[1] / 10.,
                    data.axes[2] / 10.]
                for leg in stompy.info.legs:
                    stompy.ros.planner.plans[leg].set_velocity(
                        vector, stompy.ros.planner.BODY_FRAME)
            else:  # 33, rotate
                rm = stompy.transforms.rotation_3d(
                    data.axes[0] / 5., data.axes[1] / 5., data.axes[2] / 5.,
                    degrees=True)
                for leg in stompy.info.legs:
                    stompy.ros.planner.plans[leg].set_transform(
                        rm, stompy.ros.planner.BODY_FRAME)

        # attach callback to joystick
        cbid = stompy.ros.joystick.callbacks.register(
            move_body)
        # sleep and watch for new modes
        while True:
            rospy.sleep(0.1)
            stompy.ros.planner.update()
            if not (stompy.ros.joystick.mode in (32, 33)):
                stompy.ros.planner.set_stop()
                break
        # unregister callback
        stompy.ros.joystick.callbacks.unregister(cbid)
        # transition to new mode
        return "newmode"


class PositionLegs(smach.State):
    def __init__(self):
        smach.State.__init__(
            self, outcomes=['ready', 'error'],
            input_keys=['leg_positions', 'leg_loads', 'lift_z'])

    def execute(self, userdata):
        load = 0.
        for leg in stompy.info.legs:
            load += stompy.sensors.legs.legs[leg]['load']
        if load > 4000:
            pt_distance = 0.2
        else:
            pt_distance = 0.3
        # positon legs one at a time
        # start with least loaded leg
        leg_loads = {}
        for leg in stompy.info.legs:
            leg_loads[leg] = stompy.sensors.legs.legs[leg]['load']
        legs_by_load = sorted(leg_loads, key=lambda k: leg_loads[k])

        lift_z = userdata.lift_z
        for leg in legs_by_load:
            print("leg: %s" % leg)
            #if leg not in userdata.leg_positions[leg]:
            #    pass
            #target_position = userdata.leg_positions[leg]
            target_position = stompy.info.foot_centers[leg]
            target_load = userdata.leg_loads[leg]
            plan = stompy.ros.planner.plans[leg]
            # check if leg is loaded
            if stompy.sensors.legs.legs[leg]['load'] > 100:
                print(
                    "leg is loaded %s, lifting" % (
                        stompy.sensors.legs.legs[leg]['load']))
                # lift until unloaded
                plan.set_velocity(
                    [0, 0, -pt_distance], stompy.ros.planner.BODY_FRAME)
                while stompy.sensors.legs.legs[leg]['load'] > 100.:
                    plan.update()
                    rospy.sleep(0.1)
                # continue lifting until lift_z off ground
                unloaded_z = stompy.sensors.legs.legs[leg]['foot'][2]
                while (
                        unloaded_z - stompy.sensors.legs.legs[leg]['foot'][2]
                        < lift_z):
                    plan.update()
                    rospy.sleep(0.1)
                plan.set_stop()
            rospy.sleep(0.25)
            # move to xy
            lifted_z = stompy.sensors.legs.legs[leg]['foot'][2]
            end = [target_position[0], target_position[1], lifted_z]
            print("moving to xy: %s" % end)
            # TODO compute duration
            fx, fy, fz = stompy.kinematics.body.leg_to_body(
                leg, *stompy.sensors.legs.legs[leg]['foot'])[:3]
            x, y, z = end
            d = ((x - fx) ** 2. + (y - fy) ** 2. + (z - fz) ** 2.) ** 0.5
            s = max(d / 0.2, 1.0)
            plan.set_line(
                end, stompy.ros.planner.BODY_FRAME, duration=s)
            publisher = stompy.ros.legs.publishers[leg]
            rospy.sleep(0.1)
            while True:
                # plan.update()
                state = publisher.get_state()
                if state == actionlib.GoalStatus.SUCCEEDED:
                    break
                if state != actionlib.GoalStatus.ACTIVE:
                    print(leg, actionlib.GoalStatus.to_string(state))
                    return "error"
                rospy.sleep(0.1)
            # lower until loaded
            rospy.sleep(0.25)
            print("Lower until loaded")
            plan.set_velocity(
                [0, 0, pt_distance], stompy.ros.planner.BODY_FRAME)
            while stompy.sensors.legs.legs[leg]['load'] <= target_load:
                plan.update()
                rospy.sleep(0.1)
            plan.set_stop()
        return 'ready'


class Stand(smach.State):
    def __init__(self):
        smach.State.__init__(
            self, outcomes=["ready", "error"],
            input_keys=['stand_z', ])

    def execute(self, userdata):
        stand_z = userdata.stand_z
        start_time = rospy.Time.now() + rospy.Duration(0.5)
        for leg in stompy.ros.planner.plans:
            plan = stompy.ros.planner.plans[leg]
            st, _ = plan.find_start(
                #timestamp=start_time,
                frame=stompy.ros.planner.FOOT_FRAME)
            end = (st[0], st[1], stand_z)
            print("stand, moving %s from %s to %s" % (leg, st, end))
            print("starting at: %s" % start_time.to_sec())
            plan.set_line(
                end, stompy.ros.planner.FOOT_FRAME, duration=4.0,
                start=st,
                timestamp=start_time)
        #rospy.sleep(0.5)
        done = False
        print(
            "waiting on legs to finish standing: %s" %
            rospy.Time.now().to_sec())
        while not done:
            done = True
            for leg in stompy.info.legs:
                s = stompy.ros.legs.publishers[leg].get_state()
                #print(leg, actionlib.GoalStatus.to_string(s))
                if s == actionlib.GoalStatus.SUCCEEDED:
                    continue
                if s != actionlib.GoalStatus.SUCCEEDED:
                    done = False
                if s not in (
                        actionlib.GoalStatus.ACTIVE,
                        actionlib.GoalStatus.PENDING):
                    print(leg, actionlib.GoalStatus.to_string(s))
                    return "error"
            rospy.sleep(0.1)
        print("done standing: %s" % rospy.Time.now().to_sec())
        stompy.ros.planner.set_stop()
        return "ready"


class Walk(smach.State):
    def __init__(self):
        smach.State.__init__(
            self, outcomes=["error", "newmode"])

    def execute(self, userdata):
        # use the target direction (cx, cy): rotation about point
        # leg states are:
        #  - lower (follow opposite of target direction and down)
        #  - stance (follow opposite of target direction)
        #  - lift (follow opposite of target direction and up)
        #  - swing (follow target direction, fast)
        #
        # when target changes
        #  - if movement stopped lower all legs in stance
        #  - recompute trajectories (passing through current points)
        #  - recompute limits (to know when to lift)
        #  - recompute ideal trajectories (can be resumed on swing)
        rc = stompy.gaits.restriction.RestrictionControl()

        def get_foot_positions():
            fps = {}
            for foot_name in rc.feet:
                leg = stompy.sensors.legs.legs[foot_name]
                fps[foot_name] = stompy.kinematics.body.leg_to_body(
                    foot_name, *leg['foot'])[:2]
            return fps

        # initialize restrictions
        rc.compute_foot_restrictions(get_foot_positions())
        # setup all default targets
        for foot_name in rc.feet:
            rc.feet[foot_name].stance_target = (0, 0)
            rc.feet[foot_name].swing_target = rc.feet[foot_name].center

        # TODO bring out
        step_size = 0.5
        half_step_size = step_size / 2.
        lift_velocity = -0.3
        lower_velocity = 0.2
        swing_velocity = 0.3

        # attach joystick callback
        def update_targets(data):
            # set all targets
            tx = data.axes[0] / 10.
            ty = data.axes[1] / 10.
            for foot_name in rc.feet:
                foot = rc.feet[foot_name]
                foot.stance_target = (-tx, -ty)
                cx, cy = foot.center
                tl = ((tx * tx) + (ty * ty)) ** 0.5
                if tl == 0.:
                    foot.swing_target = (cx, cy)
                else:
                    ntx, nty = tx / tl, ty / tl
                    print(tx, ty, tl, ntx, nty)
                    foot.swing_target = (
                        cx + ntx * half_step_size,
                        cy + nty * half_step_size)
                print(foot_name)
                print(foot.stance_target)
                print(foot.swing_target)
                if foot.state in ('stance', 'wait'):
                    dx, dy = foot.stance_target
                    plan.set_velocity(
                        (dx, dy, 0.), stompy.ros.planner.BODY_FRAME)
                elif foot.state == 'lift':
                    dx, dy = foot.stance_target
                    plan.set_velocity(
                        (dx, dy, lift_velocity),
                        stompy.ros.planner.BODY_FRAME)
                elif foot.state == 'lower':
                    dx, dy = foot.stance_target
                    plan.set_velocity(
                        (dx, dy, lower_velocity),
                        stompy.ros.planner.BODY_FRAME)
                elif foot.state == 'swing':
                    x, y = foot.swing_target
                    fx, fy = stompy.kinematics.body.leg_to_body(
                        foot_name, *leg['foot'])[:2]
                    d = ((x - fx) ** 2. + (y - fy) ** 2.) ** 0.5
                    s = max(d / swing_velocity, 1.0)
                    plan.set_line(
                        (x, y, 0.9), stompy.ros.planner.BODY_FRAME,
                        duration=s)
                else:
                    raise Exception("Unknown state: %s" % foot.state)

        cbid = stompy.ros.joystick.callbacks.register(
            update_targets)

        done = False
        while not done:
            # set leg positions by position and state
            requested_states = rc.update(
                rospy.Time.now().to_sec(), get_foot_positions())

            for foot_name in rc.feet:
                foot = rc.feet[foot_name]
                leg = stompy.sensors.legs.legs[foot_name]
                plan = stompy.ros.planner.plans[foot_name]
                requested = requested_states.get(foot_name, None)
                # check if leg should be paused...
                if requested == 'pause':
                    foot.stance_target = (0., 0.)
                    if foot.state in ('wait', 'stance'):
                        plan.set_stop()
                    elif foot.state == 'lift':
                        plan.set_velocity(
                            (0., 0., lift_velocity),
                            stompy.ros.planner.BODY_FRAME)
                    elif foot.state == 'lower':
                        plan.set_velocity(
                            (0., 0., lower_velocity),
                            stompy.ros.planner.BODY_FRAME)
                if leg['load'] > 50:
                    # leg is loaded
                    if foot.state == 'lower' and leg['foot'][2] >= 1.1:
                        dr = foot.restriction - foot.last_restriction
                        if dr > 0:
                            foot.set_state('stance')
                        else:
                            foot.set_state('wait')
                        # update planner, straight xy along target vec
                        dx, dy = foot.stance_target
                        # TODO arc
                        print('%s: %s, %s' % (
                            foot.state, foot.name, foot.stance_target))
                        plan.set_velocity(
                            (dx, dy, 0.), stompy.ros.planner.BODY_FRAME)
                else:
                    if foot.state == 'lift' and leg['foot'][2] <= 0.9:
                        foot.set_state('swing')
                        # update planner, straight xy to target
                        x, y = foot.swing_target
                        print('swing: %s, %s' % (foot.name, foot.swing_target))
                        fx, fy = stompy.kinematics.body.leg_to_body(
                            foot_name, *leg['foot'])[:2]
                        d = ((x - fx) ** 2. + (y - fy) ** 2.) ** 0.5
                        s = max(d / swing_velocity, 1.0)
                        print('swing: %s, %s[%s,%s]' % (
                            foot.name, foot.swing_target, d, s))
                        plan.set_line(
                            (x, y, 0.9), stompy.ros.planner.BODY_FRAME,
                            duration=s)
                if requested == 'swing':
                    foot.set_state('lift')
                    foot.last_lift_time = rospy.Time.now().to_sec()
                    dx, dy = foot.stance_target
                    print('lift: %s, %s' % (foot.name, foot.stance_target))
                    plan.set_velocity(
                        (dx, dy, lift_velocity),
                        stompy.ros.planner.BODY_FRAME)
                # check if swing is done, if so, lower
                if (
                        foot.state == 'swing' and
                        stompy.ros.legs.get_done(foot_name)):
                    foot.set_state('lower')
                    dx, dy = foot.stance_target
                    print('lower: %s, %s' % (foot.name, foot.stance_target))
                    plan.set_velocity(
                        (dx, dy, lower_velocity),
                        stompy.ros.planner.BODY_FRAME)
            stompy.ros.planner.update()
            rospy.sleep(0.1)
            if not (stompy.ros.joystick.mode == 35):
                stompy.ros.planner.set_stop()
                # TODO transition to position legs?
                break

        # detach joystick callback
        stompy.ros.joystick.callbacks.unregister(cbid)
        return 'newmode'


class Wait(smach.State):
    def __init__(self):
        smach.State.__init__(
            self, outcomes=["error", "newmode"])

    def execute(self, userdata):
        while True:
            if stompy.ros.joystick.mode != 34:
                return "newmode"
            rospy.sleep(0.1)
        return "error"


if __name__ == '__main__':
    stompy.ros.init.init()
    # setup state machine
    sm = smach.StateMachine(outcomes=["error", "ready"])
    sm.userdata.stand_z = 1.1
    sm.userdata.lift_z = 0.6
    sm.userdata.leg_positions = {
        'fr': (1.075, 0., 0.6),
        'mr': (1.075, 0., 0.6),
        'rr': (1.075, 0., 0.6),
        'fl': (1.075, 0., 0.6),
        'ml': (1.075, 0., 0.6),
        'rl': (1.075, 0., 0.6),
    }
    #leg_load = 5600 / 6.
    leg_load = 50
    sm.userdata.leg_loads = {
        'fr': leg_load, 'mr': leg_load, 'rr': leg_load,
        'fl': leg_load, 'ml': leg_load, 'rl': leg_load,
    }
    with sm:
        smach.StateMachine.add(
            'Startup', Startup(),
            transitions={'ready': 'ModeTransition'})
        smach.StateMachine.add(
            'ModeTransition', ModeTransition(),
            transitions={
                'moveleg': 'MoveLeg', 'movebody': 'MoveBody',
                'positionlegs': 'PositionLegs', 'walk': 'Walk'})
        smach.StateMachine.add(
            'MoveLeg', MoveLeg(),
            transitions={'newmode': 'ModeTransition'})
        smach.StateMachine.add(
            'MoveBody', MoveBody(),
            transitions={'newmode': 'ModeTransition'})
        smach.StateMachine.add(
            'PositionLegs', PositionLegs(),
            transitions={'ready': 'Stand'})
        smach.StateMachine.add(
            'Stand', Stand(),
            transitions={'ready': 'Wait'})
        smach.StateMachine.add(
            'Wait', Wait(),
            transitions={'newmode': 'ModeTransition'})
        smach.StateMachine.add(
            'Walk', Walk(),
            transitions={'newmode': 'ModeTransition'})

    outcome = sm.execute()
    print("State machine ended with: %s" % outcome)
