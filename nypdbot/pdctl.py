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

"""
Pure Data object graph manipulation library.
"""

from __future__ import print_function

import collections
import logging
import socket

try:
    from . import dotplacer
except ImportError:
    dotplacer = None

__all__ = ['Pd']

# This must match the port in driver.pd
SEND_PORT = 2001

# Table of Python-legal replacements for special characters in object names.
SPECIAL_CHARACTERS = {
    '_': '~',
    'plus': '+',
    'minus': '-',
    'times': '*',
    'div': '/',
    }

# Classes for creating particular PD objects. Obj can be used to create any
# object, but you can register a class here to provide more specialized methods.
# See Recv as an example.
PD_OBJECTS = {}

def register(cls):
    """Decorator declaring that a class is for creating a PD object."""
    PD_OBJECTS[cls.__name__] = cls
    return cls


class Connection(object):

    def __init__(self, outlet, inlet):
        self.outlet = outlet
        self.inlet = inlet
        self.rendered = False


class Box(object):
    """Base class for all Pure Data boxes.

    For patching purposes, the attributes 'in0', 'in1', etc. refer to the
    inlets of this box, and 'out0', 'out1', etc. refer to the outlets.
    In addition, the box itself can be patched, which will connect the
    leftmost outlet or inlet. That is, a.patch(b) is shorthand for
    a.out0.patch(b.in0).
    """

    CREATION_COMMAND = None

    def __init__(self, parent_canvas, name, *args):
        self.parent_canvas = parent_canvas
        self.name = name
        self.args = args
        self._children = collections.defaultdict(list)
        self._parents = collections.defaultdict(list)
        self.rendered = False

    def __getattr__(self, name):
        if name.startswith('out'):
            return Outlet(self, int(name[3:]))
        elif name.startswith('in'):
            return Inlet(self, int(name[2:]))
        return getattr(super(Box, self), name)

    def patch(self, other):
        return self.out0.patch(other)

    def _patch(self, inlet, outlet):
        assert outlet.box is self
        self._children[outlet.idx].append(Connection(outlet, inlet))
        inlet.box._parents[inlet.idx].append(self)
        return inlet.box

    def parents(self):
        """Yields the boxes connected to the inlets of this box."""
        for i in sorted(self._parents):
            for obj in self._parents[i]:
                yield obj

    def children(self):
        """Yields the boxes connected to the outlets of this box."""
        for conn in self.outgoing():
            yield conn.inlet.box

    def outgoing(self):
        """Yields Connection objects for the outlets of this box."""
        for i in sorted(self._children):
            for conn in self._children[i]:
                yield conn

    def parent(self):
      """Return the left-most parent, if any."""
      return next(self.parents(), None)

    def child(self):
      """Return the left-most child, if any."""
      return next(self.children(), None)

    def __repr__(self):
        return '%s(%s %s)' % (
            self.__class__.__name__, self.name,
            ' '.join(str(arg) for arg in self.args))


class Inlet(object):
    def __init__(self, box, idx):
        self.box = box
        self.idx = idx


class Outlet(object):
    def __init__(self, box, idx):
        self.box = box
        self.idx = idx

    def patch(self, other):
        """Connects this outlet to the given inlet."""
        if (isinstance(other, Box)):
            inlet = other.in0
        else:
            inlet = other
        return self.box._patch(inlet, self)


@register
class Msg(Box):
    """A [message( box."""
    CREATION_COMMAND = 'msg'


@register
class Obj(Box):
    """A generic object box, e.g. [print foo]."""
    CREATION_COMMAND = 'obj'


@register
class Recv(Obj):
    """An [r] object."""

    _recv_count = -1

    @classmethod
    def gen_name(cls):
        """Generates a unique selector name."""
        cls._recv_count += 1
        return '_recv_%d' % cls._recv_count

    def __init__(self, parent_canvas, selector=None):
        selector = selector or self.gen_name()
        super(Recv, self).__init__(parent_canvas, 'r', selector)
        self.selector = selector

    def send(self, *args):
        """Sends a message to this recv object."""
        self.parent_canvas.pd.send_cmd(self.selector, *args)


class Placer(object):
    """A simple breadth-first object placer.."""

    TOP = 10
    LEFT = 10

    def __init__(self, test_mode=False):
        if test_mode:
            # For test purposes, place all objects at (-1, -1).
            self.TOP = -1
            self.LEFT = -1
            self.y_step = 0
            self.x_step = 0
        else:
            self.y_step = 20
            self.x_step = 80
        self.left = self.LEFT
        self.coords = {}
        # Count of children of each object
        self.children = collections.defaultdict(int)

    def place_all(self, boxes):
        to_place = [box for box in boxes if not box.parent()]
        placed = {}
        while to_place:
            box = to_place.pop(0)
            if box in self.coords:
                continue
            coords = self.place(box)
            if not coords:
                to_place.append(box)
                continue
            self.coords[box] = placed[box] = coords
            to_place.extend(box.children())
        return placed

    def place(self, obj):
        parent = obj.parent()
        if not parent:
            self.left += self.x_step
            return self.left, self.TOP
        if parent not in self.coords:
            return
        px, py = self.coords[parent]
        left = px + self.x_step * self.children[parent]
        top = py + self.y_step
        self.children[parent] += 1
        return left, top

# If pygraphviz is available, use it for smarter object placement.
if dotplacer:
    PLACER_CLASS = dotplacer.DotPlacer
else:
    PLACER_CLASS = Placer


@register
class Canvas(Obj):
    """Reprents a Pd canvas, keeping track of objects added to it.

    Object creation messages are not sent directly; they are queued until
    render() is called. This is so the object placer can see the complete
    graph when deciding where to place objects.

    Because __getattr__ is overloaded, you can use e.g. canvas.recv('foo')
    to create a [recv foo] object. To create an audio-rate object like osc~,
    use the Python-legal name canvas.osc_(440).
    """

    def __init__(self, pd, parent_canvas, canvas_name, *args):
        super(Canvas, self).__init__(parent_canvas, 'pd', canvas_name, *args)
        self.pd = pd
        self.canvas_name = canvas_name
        self.boxes = []
        self.ids = {}

    def _pd_obj_name(self, name):
        name = name.lower()
        for python_name, pd_name in SPECIAL_CHARACTERS.items():
            name = name.replace(python_name, pd_name)
        return name

    def __getattr__(self, name):
        def create(*args):
            constructor = PD_OBJECTS.get(name)
            if constructor:
                box = constructor(self, *args)
            else:
                box = Obj(self, self._pd_obj_name(name), *args)
            return self.add(box)
        return create

    def add(self, box):
        """Add the given box to the canvas."""
        self.boxes.append(box)
        # Chainable so you can write box = canvas.add(Box(...))
        return box

    def canvas(self, name, *args):
        return self.add(Canvas(self.pd, self, name, *args))

    def render(self):
        """Send all queued box and conn creation messages."""
        for cmd in self._creation_commands():
            self.send_cmd(*cmd)

    def _creation_commands(self):
        # TODO: only generate commands for boxes and conns that are new
        # since the last time render() was called.
        connections = []
        for box in self.boxes:
            connections.extend(box.outgoing())

        boxes_to_place = [box for box in self.boxes if not box.rendered]
        placer = PLACER_CLASS()
        coords = placer.place_all(boxes_to_place)

        start_id = len(self.ids)
        for i, box in enumerate(boxes_to_place):
            self.ids[box] = i + start_id

        for box in boxes_to_place:
            box.rendered = True
            assert box.CREATION_COMMAND
            yield [box.CREATION_COMMAND, coords[box][0], coords[box][1],
                   box.name] + list(box.args)
        for conn in connections:
            if not conn.rendered:
                conn.rendered = True
                yield ['connect', self.ids[conn.outlet.box], conn.outlet.idx,
                       self.ids[conn.inlet.box], conn.inlet.idx]

    def send_cmd(self, *args):
        """Sends a command to this canvas in Pure Data."""
        self.pd.send_cmd('pd-' + self.canvas_name, *args)

    def clear(self):
        """Removes all boxes from this canvas."""
        self.boxes = []
        self.send_cmd('clear')


class PdSend(object):
    """Sends messages to Pure Data."""
    def __init__(self, port=SEND_PORT):
        self.conn = socket.create_connection(('localhost', port))
        logging.debug('Sender connected')

    def send(self, cmd):
        logging.debug(cmd)
        self.conn.send(cmd)


class FakePdSend(object):
    def send(self, cmd):
        print(cmd)


def fudi_escape(arg):
    if hasattr(arg, 'to_fudi'):
        serialized = arg.to_fudi()
    else:
        serialized = str(arg)
    return serialized.replace(';', r'\;')


def to_fudi(args):
    """Serialize a list of objects into a PD protocol message."""
    msg = ' '.join(fudi_escape(arg) for arg in args) + ';'
    return msg.encode('utf-8')


class Pd(object):
    def __init__(self, sender=None):
        self.sender = sender or PdSend()
        self.main = Canvas(self, None, '__main__')

    def dsp(self, on):
        self.send_cmd('pd', 'dsp', 1 if on else 0)

    def send_cmd(self, *args):
        self.sender.send(to_fudi(args))


def main():
    pd = Pd(sender=FakePdSend())

    patch = pd.main
    lb = patch.metro(500)
    echo = patch.print('hello', 'world!')
    lb.patch(echo)
    osc = patch.osc_(440)
    vol = patch.times_(0.04)
    dac = patch.dac_()
    osc.patch(vol).patch(dac)

    patch.render()
    pd.dsp(True)

if __name__ == '__main__':
    main()
