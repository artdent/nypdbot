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
import re
import socket
import time

try:
    from . import dotplacer
except ImportError:
    dotplacer = None

__all__ = ['Pd']

# This must match the port in driver.pd
SEND_PORT = 2001

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
    HEIGHT = 18
    _unique_name_count = -1

    def __init__(self, pd, *args, **kwargs):
        if any(isinstance(arg, Box) for arg in args):
            raise TypeError(
                'Object parents may be passed only as keyword arguments.')
        self.pd = pd
        self.args = args
        self._children = collections.defaultdict(list)
        self._parents = collections.defaultdict(list)
        self.rendered = False

        # These will be set when the box is placed on the parent patch.
        self.x = None
        self.y = None
        self.id = None

        for attr, other in kwargs.items():
            if not isinstance(other, collections.Iterable):
                other = [other]
            for obj in other:
                obj.patch(getattr(self, attr))

    @classmethod
    def gen_name(cls, prefix=None):
        """Generates a unique selector name."""
        cls._unique_name_count += 1
        prefix = prefix or cls.CREATION_COMMAND
        return '_%s_%d' % (prefix, cls._unique_name_count)

    def __getattr__(self, name):
        if name.startswith('out'):
            return Outlet(self, int(name[3:]))
        elif name.startswith('in'):
            return Inlet(self, int(name[2:]))
        raise AttributeError(name)

    def patch(self, other):
        return self.out0.patch(other)

    def place(self, coords, box_id):
        self.x, self.y = coords
        self.id = box_id
        return self._creation_commands()

    def is_placed(self):
        return bool(self.x)

    def _creation_commands(self):
        assert self.CREATION_COMMAND

        cmd = [self.CREATION_COMMAND, self.x, self.y] + list(self.args)
        return [cmd]

    def _patch(self, inlet, outlet):
        assert outlet.box is self
        self._children[outlet.idx].append(Connection(outlet, inlet))
        inlet.box._parents[inlet.idx].append(self)
        return inlet.box

    def inlet_count(self):
        return len(self._parents)

    def outlet_count(self):
        return len(self._children)

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
        return '%s(%s)' % (
            self.__class__.__name__,
            ' '.join(str(arg) for arg in self.args))


class Inlet(object):
    """Representation of a numbered inlet of an object.

    This is *not* a Pure Data [inlet] object.
    """
    def __init__(self, box, idx):
        self.box = box
        self.idx = idx


class Outlet(object):
    """Representation of a numbered outlet of an object.

    This is *not* a Pure Data [outlet] object.
    """
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

    # N.B. To get a message like "1 2, 3 4", call:
    # Msg(1, 2, ',', 3, 4)

    def __init__(self, *args, **kwargs):
        args = tuple(arg.replace(',', r'\,') for arg in args)
        super(Msg, self).__init__(*args, **kwargs)

@register
class Number(Box):
    """A number box."""
    CREATION_COMMAND = 'floatatom'

@register
class Symbol(Box):
    """A symbol box."""
    CREATION_COMMAND = 'symbolatom'

class Gui(Box):
    """A graphical box."""

    def __init__(self, pd, name=None, **kwargs):
        name = name or self.gen_name()
        super(Gui, self).__init__(pd, name, **kwargs)
        self.name = name

    def _creation_commands(self):
        assert self.CREATION_COMMAND

        cmds = []
        cmds.append([self.CREATION_COMMAND, self.name])
        # Graphical objects do not accept placement coordinates in their
        # creation command. Instead, one must simulate mouse movements.
        # No idea what the numbers after coords are for.
        cmds.append(['motion', self.x, self.y, 0])
        cmds.append(['mouseup', self.x, self.y, 1, 0])
        # Deselect the object.
        cmds.append(['mouse', 4, 4, 1, 0])
        cmds.append(['mouseup', 4, 4, 1, 0])
        return cmds

@register
class Bang(Gui):
    """A [bang] box."""
    CREATION_COMMAND = 'bng'

@register
class HSlider(Gui):
    """A [message( box."""
    CREATION_COMMAND = 'hslider'

@register
class VSlider(Gui):
    """A [message( box."""

    CREATION_COMMAND = 'vslider'
    HEIGHT = 128


@register
class Obj(Box):
    """A generic object box, e.g. [print foo]."""
    CREATION_COMMAND = 'obj'

    def __init__(self, pd, *args, **kwargs):
        super(Obj, self).__init__(pd, *args, **kwargs)
        self.name = args[0]  # Convenience alias

@register
class Recv(Obj):
    """An [r] object."""

    def __init__(self, pd, selector=None):
        selector = selector or self.gen_name('recv')
        super(Recv, self).__init__(pd, 'r', selector)
        self.selector = selector

    def send(self, *args):
        """Sends a message to this recv object."""
        self.pd.send_cmd(self.selector, *args)


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


# Table of Python-legal replacements for special characters in object names.
# In addition, CamelCasedName becomes camel-cased-name and trailing
# underscores tildes. For example, p.FooBarBaz_() becomes [foo-bar-baz~].
# This is confusing, but Python allows a paucity of symbols in identifiers.
# If this table proves inadequate, the fallback is to use p.Obj('==').
_SPECIAL_CHARACTERS = {
    '__': '/',
}
_CAPS_RE = re.compile(r'(.)([A-Z])')

# Table of special object names, with optional trailing tilde.
_SPECIAL_NAMES = {
    'plus': '+',
    'minus': '-',
    'times': '*',
    'div': '/',
    'lt': '<',
    'gt': '>',
    'lte': '<=',
    'gte': '>=',
    'eq': '==',
    'neq': '!=',
    'not': '!',
    'or': '|',
    'and': '&',
    'oror': '||',
    'andand': '&&',
    'mod': '%',
}

def _pd_obj_name(name):
    """Translates a python attribute name into a Pure Data object name."""
    # Place a hyphen before every non-initial [A-Z].
    name = _CAPS_RE.sub(lambda m: '%s-%s' % m.groups(), name).lower()

    audio_rate = name.endswith('_')
    name = name.rstrip('_')

    if name in _SPECIAL_NAMES:
        name = _SPECIAL_NAMES[name]
    else:
        for python_name, pd_name in _SPECIAL_CHARACTERS.items():
            name = name.replace(python_name, pd_name)
    if audio_rate:
        name += '~'
    return name


@register
class Canvas(Obj):
    """Reprents a Pd canvas, keeping track of objects added to it.

    Object creation messages are not sent directly; they are queued until
    render() is called. This is so the object placer can see the complete
    graph when deciding where to place objects.

    Because __getattr__ is overloaded, you can use e.g. canvas.Recv('foo')
    to create a [recv foo] object. To create an audio-rate object like osc~,
    use the Python-legal name canvas.Osc_(440).

    To create an object like [<~ 0.5], you may find it easier to call
    p.Obj('<~', 0.5) than to remember the Python-legal alternate name
    p.Lt_(0.5). In addition, this is an escape hatch in case an object
    is not expressible as a Python-legal name.
    """

    def __init__(self, pd, canvas_name, *args):
        # TODO: **kwargs not supported here, as the connection commands would
        # come from the child patch when they need to come from
        # the parent patch.
        super(Canvas, self).__init__(pd, 'pd', canvas_name, *args)
        self.pd = pd
        self.canvas_name = canvas_name
        self.boxes = []
        self.next_box_id = 0  # Track the 0-based ids assigned by pure data.
        self.interactive = False
        if self.canvas_name == '__main__':
            # The main patch already exists in driver.pd.
            self.rendered = True

    def __getattr__(self, name):
        if name[0].islower():
            # Fall back on parent class, for inlet and outlet attributes.
            return super(Canvas, self).__getattr__(name)
        # Uppercased or special-character attributes are for object creation.
        return self._create_object(name)

    def _create_object(self, name):
        """Create a Pure Data object."""
        def create(*args, **kwargs):
            constructor = PD_OBJECTS.get(name)
            if constructor:
                box = constructor(self.pd, *args, **kwargs)
            else:
                box = Obj(self.pd, _pd_obj_name(name), *args, **kwargs)
            return self.add(box)
        return create

    def add(self, box):
        """Add the given box to the canvas."""
        self.boxes.append(box)
        if self.interactive:
            # TODO: determine coordinates.
            self._render_box(box, (10, 10))
        # Chainable so you can write box = canvas.add(Box(...))
        return box

    def render(self):
        """Renders all unrendered children of this patch.

        Calling render() also places the patch into interactive mode,
        where future object additions happen right away. Set the
        interactive attribute to False to go back to batch mode.
        """
        boxes_to_place = [box for box in self.boxes if not box.is_placed()]
        placer = PLACER_CLASS()
        coords = placer.place_all(boxes_to_place)

        for box in boxes_to_place:
            self._render_box(box, coords[box])

        for box in self.boxes:
            for conn in box.outgoing():
                self._maybe_render_conn(conn)

        self.interactive = True

    def _render_box(self, box, coords):
        creation_commands = box.place(coords, self.next_box_id)
        self.next_box_id += 1
        for cmd in creation_commands:
            self.send_cmd(*cmd)
            # Hack: if mouse events happen too quickly, pd gets confused
            # and places objects in the wrong spot.
            if isinstance(box, Gui):
                time.sleep(0.01)
        if hasattr(box, 'render'):
            box.render()

    def _maybe_render_conn(self, conn):
        if not conn.rendered:
            conn.rendered = True
            self.send_cmd(
                'connect', conn.outlet.box.id, conn.outlet.idx,
                conn.inlet.box.id, conn.inlet.idx)

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
        self.main = Canvas(self, '__main__')

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
