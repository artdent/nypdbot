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
Generator-based event sequencer.

This scheduler is loosely inspired by the ChucK audio programming language
and its approach to time manipulation (see
http://chuck.cs.princeton.edu/doc/language/time.html).

This module is distributed as part of nypdbot, but it could easily be used
standalone.
"""

import functools
import heapq
import logging
import time
try:
  from functools import total_ordering
except ImportError:
  from .total_ordering import total_ordering

__all__ = ['Mta', 'Beat', 'Time', 'forever', 'measure']


@total_ordering
class ScheduledEvent:
    """An event scheduled to happen after a given delay."""

    def __init__(self, data, bpm, delay):
        self.bpm = bpm
        self.delay = delay
        self.data = data

    def __lt__(self, other):
        if not other.delay:
            return False
        return self.delay.to_ms(self.bpm) < other.delay.to_ms(self.bpm)

    def __str__(self):
        return 'Event @ %s' % self.delay


class Mta:
    """Event scheduler. Stands for Metronomic Timing Activity.

    This scheduler can be driven externally by calling the tick method
    as necessary, or you can call loop to sleep between events until
    all events are exhausted.
    """
    def __init__(self, bpm):
        self.bpm = bpm
        self.scheduler = []
        self.tm = None

    def add(self, f):
        """Add an iterator to the scheduler."""
        self._enqueue(f, Time(0))

    def _enqueue(self, ev, delay):
        """Schedule an event."""
        heapq.heappush(self.scheduler, ScheduledEvent(ev, self.bpm, delay))

    def _sleep(self, delay_ms):
        time.sleep(delay_ms / 1000.0)

    def _now(self):
        return time.time() * 1000

    def tick(self):
        """Fires any events that are ready.

        Returns:
          The delay (in ms) until the next event, or None if there are
        no more events.
        """
        logging.debug('firing events at %s', self.tm)
        if self.tm is None:
            self.tm = self._now()
        else:
            now = self._now()
            # TODO: store absolute time instead of relative time
            # to eliminate this step, which is linear in the number of events.
            for ev in self.scheduler:
                ev.delay.elapse(self.bpm, now - self.tm)
            self.tm = now
        while self.scheduler and self.scheduler[0].delay.to_ms(self.bpm) <= 0:
            ev = heapq.heappop(self.scheduler)
            delay_ms = ev.delay.to_ms(self.bpm)
            if delay_ms < -10:
                logging.warn('fell behind by', abs(delay_ms), 'ms')
            self._fire_event(ev)
        if self.scheduler:
            return self.scheduler[0].delay.to_ms(self.bpm)

    def _fire_event(self, event):
        next_delay = next(event.data, None)
        if next_delay:
            self._enqueue(event.data, next_delay)

    def loop(self):
        """Run until all events are consumed, sleeping between them."""
        while True:
            delay_until_next = self.tick()
            if not delay_until_next:
                break
            self._sleep(delay_until_next)


def beats_to_ms(bpm, beats):
    return beats * 1000 * 60.0 / bpm


def ms_to_beats(bpm, ms):
    return ms * bpm / (1000 * 60)


class TimePoint:
    """A tempo-aware time point for scheduling an event."""

    def elapse(self, bpm, ms):
        """Decrement this point by the given number of milliseconds."""
        raise NotImplementedError

    def to_ms(self, bpm):
        """Return this time point in milliseconds."""
        raise NotImplementedError


class Beat(TimePoint):
    """A time point measured in beats."""
    def __init__(self, count=1):
        self.count = count

    def elapse(self, bpm, ms):
        self.count -= ms_to_beats(bpm, ms)

    def to_ms(self, bpm):
        return beats_to_ms(bpm, self.count)

    def __str__(self):
        return 'Beat(%f)' % self.count


class Time(TimePoint):
    """A time point measured in milliseconds."""
    def __init__(self, ms):
        self.ms = ms

    def elapse(self, bpm, ms):
        self.ms -= ms

    def to_ms(self, bpm):
        return self.ms

    def __str__(self):
        return 'Time(%f ms)' % self.ms


def _fill_time(beats, shard, *args, **kwargs):
    """Yield from a generator, then yields an extra Beat."""
    total = 0
    for delay in shard(*args, **kwargs):
        total += delay.count
        yield delay
    yield Beat(beats - total)


def measure(beats):
    """Expand a generator to fill a complete measure.

    Args:
      beats: The number of beats in the measure.

    Returns:
      A generator that yields from the original generator, then yields
    one more Beat object that fills the remaining number of beats
    in the measure.
    """
    def wrap(shard):
        return functools.partial(_fill_time, beats, shard)
    return wrap


def forever(shard):
    """Repeat a generator forever."""
    def repeat(*args, **kwargs):
        while True:
            for delay in shard(*args, **kwargs):
                yield delay
    return repeat


@forever
def example():
    print('beat 1')
    yield Beat()
    print('beat 2')
    yield Beat()

@forever
@measure(4)
def example2():
    print('eighth note 1')
    yield Beat(0.5)
    print('eighth note 2')
    # The measure decorator adds an extra 3 beats here.

@forever
def example3():
    print(' ' * 10, 'tick')
    yield Time(333)

def main():
    mta = Mta(60)
    mta.add(example())
    mta.add(example2())
    mta.add(example3())
    mta.loop()

if __name__ == '__main__':
    main()
