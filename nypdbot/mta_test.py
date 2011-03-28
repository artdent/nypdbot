#!/usr/bin/python3

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

import unittest

from . import mta


class UntimedMta(mta.Mta):
    """Version of MTA that doesn't actually sleep."""

    def __init__(self):
        super().__init__(60)  # BPM doesn't matter
        self.slept = 0
        self.events = 0

    def _sleep(self, ms):
        print('sleeping for', ms)
        self.slept += ms

    def _now(self):
        print('it is now', self.slept)
        return self.slept

    def _fire_event(self, ev):
        super()._fire_event(ev)
        self.events += 1


class MtaTest(unittest.TestCase):

    def setUp(self):
        self.output = []

    def out(self, s):
        self.output.append(s)

    def go(self):
        self.out('a')
        self.out('b')
        yield mta.Time(1)
        self.out('c')
        self.out('d')

    def testLoop_basic(self):
        scheduler = UntimedMta()
        scheduler.add(self.go())
        scheduler.loop()
        self.assertEquals(['a', 'b', 'c', 'd'], self.output)

    def testTick_basic(self):
        scheduler = UntimedMta()
        self.assertEquals(0, scheduler.events)
        scheduler.add(self.go())
        self.assertEquals(1, scheduler.tick())
        self.assertEquals(1, scheduler.events)
        self.assertEquals(['a', 'b'], self.output)

        # Calling tick() again without any time elapsed.
        self.assertEquals(1, scheduler.tick())
        self.assertEquals(1, scheduler.events)
        self.assertEquals(['a', 'b'], self.output)

        scheduler._sleep(10)
        self.assertIsNone(scheduler.tick())
        self.assertEquals(2, scheduler.events)
        self.assertEquals(['a', 'b', 'c', 'd'], self.output)

        self.assertIsNone(scheduler.tick())
        scheduler._sleep(10)
        self.assertIsNone(scheduler.tick())
        self.assertEquals(['a', 'b', 'c', 'd'], self.output)


class BeatTest(unittest.TestCase):
    def testToMs(self):
        beat = mta.Beat()
        self.assertEquals(500, beat.to_ms(120))
        self.assertEquals(1000, beat.to_ms(60))

        beat = mta.Beat(4)
        self.assertEquals(2000, beat.to_ms(120))
        self.assertEquals(4000, beat.to_ms(60))

        beat = mta.Beat(0.5)
        self.assertEquals(250, beat.to_ms(120))
        self.assertEquals(500, beat.to_ms(60))


if __name__ == '__main__':
    unittest.main()
