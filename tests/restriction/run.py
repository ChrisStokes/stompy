#!/usr/bin/env python

import calc
import vis

r = calc.RestrictionControl()
vis.run(r, r.update, 0.1)
