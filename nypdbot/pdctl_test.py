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

from . import pdctl


class TestPdSend(pdctl.PdSend):
    def __init__(self):
        self.sent = []

    def send(self, cmd):
        self.sent.append(cmd)

class PdTest(unittest.TestCase):

    def setUp(self):
        self.sender = TestPdSend()
        self.pd = pdctl.Pd(sender=self.sender)
        self.pd.main._placer.enter_test_mode()

    def testSmoke(self):
        # Add some arbitrary objects.
        patch = self.pd.main
        lb = patch.metro(500)
        echo = patch.print('hello', 'world!')
        lb.patch(echo)
        osc = patch.osc_(440)
        vol = patch.times_(0.04)
        dac = patch.dac_()
        osc.patch(vol).patch(dac)

        patch.render()
        self.pd.dsp(True)

        self.assertEquals(
            [
                b'pd-__main__ obj -1 -1 metro 500;',
                b'pd-__main__ obj -1 -1 print hello world!;',
                b'pd-__main__ obj -1 -1 osc~ 440;',
                b'pd-__main__ obj -1 -1 *~ 0.04;',
                b'pd-__main__ obj -1 -1 dac~;',
                b'pd-__main__ connect 0 0 1 0;',
                b'pd-__main__ connect 2 0 3 0;',
                b'pd-__main__ connect 3 0 4 0;',
                b'pd dsp 1;',
            ],
            self.sender.sent)

    def testSubpatch(self):
        patch = self.pd.main
        sub = patch.canvas('foo')
        patch.render()
        self.assertEquals(
            [b'pd-__main__ obj -1 -1 pd foo;'],
            self.sender.sent)

    def testSubpatch_args(self):
        patch = self.pd.main
        sub = patch.canvas('foo', 1, 2)
        patch.render()
        self.assertEquals(
            [b'pd-__main__ obj -1 -1 pd foo 1 2;'],
            self.sender.sent)


if __name__ == '__main__':
    unittest.main()
