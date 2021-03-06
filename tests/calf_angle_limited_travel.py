#!/usr/bin/env python

import sys

import numpy
import pylab

import stompy

calf_angle_threshold = 22.5
if len(sys.argv) > 1:
    calf_angle_threshold = float(sys.argv[1])


def xyz_to_calf_angle(x, y, z):
    h, t, k = stompy.kinematics.leg.point_to_angles(x, y, z)
    return numpy.degrees(
        stompy.kinematics.leg.angles_to_calf_angle(h, t, k))


x_steps = 30.
zs = numpy.arange(0, -72, -1.)

pts = []

for z in zs:
    xmin, xmax = stompy.kinematics.leg.limits_at_z_2d(z)
    xs = numpy.linspace(xmin, xmax, x_steps)
    for x in xs:
        ca = xyz_to_calf_angle(x, 0., z)
        pts.append([x, z, ca])

pts = numpy.array(pts)
cs = ['br'[int(abs(ca) > calf_angle_threshold)] for ca in pts[:, 2]]
pylab.scatter(pts[:, 0], pts[:, 1], color=cs)
pylab.xlabel('foot x position')
pylab.ylabel('foot z position')
pylab.title(
    'blue = valid foot touch down positions with +-%s calf angle'
    % calf_angle_threshold)
pylab.show()
