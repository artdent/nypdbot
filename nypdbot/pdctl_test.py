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
        pdctl.PLACER_CLASS = lambda: pdctl.Placer(test_mode=True)

    def testSmoke(self):
        # Add some arbitrary objects.
        patch = self.pd.main
        lb = patch.Metro(500)
        echo = patch.Print('hello', 'world!')
        lb.patch(echo)
        osc = patch.Osc_(440)
        vol = patch.Times_(0.04)
        dac = patch.Dac_()
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

    def testInletsAndOutlets(self):
        patch = self.pd.main
        a = patch.A()
        b = patch.B()
        pdctl.Outlet(a, 1).patch(pdctl.Inlet(b, 2))
        self.assertEquals([b], list(a.children()))
        self.assertEquals([a], list(b.parents()))

        a = patch.A()
        b = patch.B()
        a.out1.patch(b.out2)
        self.assertEquals([b], list(a.children()))
        self.assertEquals([a], list(b.parents()))

    def testSubpatch(self):
        patch = self.pd.main
        sub = patch.Canvas('foo')
        patch.render()
        self.assertEquals(
            [b'pd-__main__ obj -1 -1 pd foo;'],
            self.sender.sent)

    def testSubpatch_args(self):
        patch = self.pd.main
        sub = patch.Canvas('foo', 1, 2)
        patch.render()
        self.assertEquals(
            [b'pd-__main__ obj -1 -1 pd foo 1 2;'],
            self.sender.sent)

    def testRecvName(self):
        patch = self.pd.main
        r = patch.Recv('foo')
        self.assertEquals('foo', r.selector)
        r2 = patch.Recv()
        self.assertEquals('_recv_0', r2.selector)
        r3 = patch.Recv('bar')
        self.assertEquals('bar', r3.selector)
        r4 = patch.Recv()
        self.assertEquals('_recv_1', r4.selector)
        r5 = patch.Recv()
        self.assertEquals('_recv_2', r5.selector)

    def testSpecialObjectNames(self):
        for attr, replacement in [
                ('Foo', 'foo'),
                ('FooBarBaz', 'foo-bar-baz'),
                ('Foo_', 'foo~'),
                ('FooBarBaz_', 'foo-bar-baz~'),
                ('Foo__bar__baz', 'foo/bar/baz'),
                ('Plus', '+'),
                ('Plus_', '+~'),
                ('Div', '/'),
                ('Neq', '!='),
                ('Or', '|'),
                ('Oror', '||'),
                ('Phasor_', 'phasor~'),  # Note "or" substring in "phasor"
                ]:
            self.assertEquals(replacement, pdctl._pd_obj_name(attr))

    def testGetattr(self):
        """Tests for object class registration and access via getattr."""
        patch = self.pd.main

        obj = patch.Lt_(0.5)
        self.assertEquals('<~', obj.name)
        self.assertEquals(('<~', 0.5), obj.args)

        alternate = patch.Obj('<~', 0.5)
        self.assertEquals('<~', alternate.name)
        self.assertEquals(('<~', 0.5), alternate.args)

        bang = patch.Bang()
        self.assertTrue(isinstance(bang, pdctl.Bang))

if __name__ == '__main__':
    unittest.main()
