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

"""
Pure Data object graph manipulation library.
"""

import collections
import logging
import socket

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
    """Class decorator for declaring that a class is for creating a PD object."""
    PD_OBJECTS[cls.__name__] = cls
    return cls


class Connection:

    def __init__(self, src, dest, outlet, inlet):
        self.src = src
        self.dest = dest
        self.outlet = outlet
        self.inlet = inlet
        self.rendered = False


class Box:
    """Base class for all Pure Data boxes."""

    CREATION_COMMAND = None

    def __init__(self, parent_canvas, name, *args):
        self.parent_canvas = parent_canvas
        self.name = name
        self.args = args
        self.children = []
        self.parents = []
        self.rendered = False

    def patch(self, other, outlet=0, inlet=0):
        self.children.append(Connection(self, other, outlet, inlet))
        other.parents.append(self)
        return other

    def parent(self):
      """Return the left-most parent, if any."""
      if self.parents:
          return self.parents[0]

    def __repr__(self):
        return '%s(%s %s)' % (
                self.__class__.__name__, self.name,
                ' '.join(str(arg) for arg in self.args))


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

    def __init__(self, parent_canvas, selector):
        super().__init__(parent_canvas, 'r', selector)
        self.selector = selector

    def send(self, *args):
        self.parent_canvas.pd.send_cmd(self.selector, *args)


class Placer:
    """An extremely dumb object placer. TODO: write a better one."""

    LEFT = 10

    def __init__(self):
        self.top = 10
        self.y_step = 20
        self.x_step = 100
        self.ys = {}
        # Count of children of each object
        self.children = collections.defaultdict(int)

    def place_all(self, boxes):
        return [self.place(box, box.parent()) for box in boxes]

    def place(self, obj, parent):
        assert obj not in self.ys
        if not parent or parent not in self.ys:
            self.ys[obj] = self.top
            self.top += self.y_step
            return self.LEFT, self.top

        self.children[parent] += 1
        top = self.ys[parent] + self.y_step
        self.ys[obj] = top
        left = self.LEFT + self.x_step * self.children[parent]
        if top >= self.top:
            self.top = top
        return left, top


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

    def __init__(self, pd, parent_canvas, canvas_name):
        super().__init__(parent_canvas, 'pd', canvas_name)
        self.pd = pd
        self.canvas_name = canvas_name
        self.boxes = []
        self._placer = Placer()

    def _creation_class(self, name):
        return name.capitalize()

    def _pd_obj_name(self, name):
        for python_name, pd_name in SPECIAL_CHARACTERS.items():
            name = name.replace(python_name, pd_name)
        return name

    def __getattr__(self, name):
        def create(*args):
            constructor = PD_OBJECTS.get(self._creation_class(name))
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
            connections.extend(box.children)
        coord_list = self._placer.place_all(self.boxes)
        coords = dict(zip(self.boxes, coord_list))
        ids = dict((box, i) for i, box in enumerate(self.boxes))
        for box in self.boxes:
            if not box.rendered:
                box.rendered = True
                assert box.CREATION_COMMAND
                yield [box.CREATION_COMMAND, coords[box][0], coords[box][1],
                       box.name] + list(box.args)
        for conn in connections:
            if not conn.rendered:
                conn.rendered = True
                yield ['connect', ids[conn.src], conn.outlet,
                       ids[conn.dest], conn.inlet]

    def send_cmd(self, *args):
        """Sends a command to this canvas in Pure Data."""
        self.pd.send_cmd('pd-' + self.canvas_name, *args)

    def clear(self):
        """Removes all boxes from this canvas."""
        self.boxes = []
        self._placer = Placer()
        self.send_cmd('clear')


class PdSend:
    """Sends messages to Pure Data."""
    def __init__(self, port=SEND_PORT):
        self.conn = socket.create_connection(('localhost', port))
        logging.debug('Sender connected')

    def send(self, cmd):
        logging.debug(cmd)
        self.conn.send(cmd)


class FakePdSend:
    def send(self, cmd):
        print(cmd)


def fudi_escape(arg):
    return str(arg).replace(';', r'\;')


def to_fudi(args):
    """Serialize a list of objects into a PD protocol message."""
    msg = ' '.join(fudi_escape(arg) for arg in args) + ';'
    return msg.encode('utf-8')


class Pd:
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
