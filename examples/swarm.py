#!/usr/bin/python

# Copyright 2011 Jacob Lee.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import code
import logging
import random
import time

import nypdbot
from nypdbot import Time

CT = 10

# Globals
pd = None
hzs = None
lopf = None

def rand_freq(base=440, spread=50):
    return max(0, base + random.random()*spread - spread/2)

def draw(patch):
    global hzs, lopf

    patch.clear()
    hzs = [patch.Recv() for i in range(CT)]
    oscs = [patch.Phasor_(rand_freq(), in0=hzs[i]) for i in range(CT)]
    vol = patch.Times_(0.04, in0=oscs)
    lopf = patch.Recv('lopf')
    lop = patch.Lop_(10000, in0=vol, in1=lopf)
    dac = patch.Dac_(in0=lop, in1=lop)

    patch.render()

def swarm():
    pd.dsp(True)
    yield Time(3000)
    for i in range(1000):
        yield Time(50)
        cutoff = 6000 - i * 25
        if cutoff < 0:
            break
        lopf.send(cutoff)
        hzs[i % CT].send(rand_freq(spread=50 + 10*i))
    pd.dsp(False)

def main():
    global pd

    logging.getLogger().setLevel(logging.DEBUG)

    pd = nypdbot.Pd()
    scheduler = nypdbot.Mta(120)

    draw(pd.main)
    scheduler.add(swarm())
    scheduler.loop()

if __name__ == '__main__':
    main()
