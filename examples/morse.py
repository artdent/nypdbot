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

"""Morse code generator.

This could use a native-pd ADSR envelope, but for demonstration purposes,
it uses one written in Python and driven by Mta.
"""

import logging

import nypdbot
from nypdbot import Time

SPEED = 100  # Length of a dih, in ms
DIHBLANK = Time(SPEED)
DAHBLANK = Time(3 * SPEED)
WORDBLANK = Time(7 * SPEED)

letters = [
    '.-', '-...', '-.-.', '-..', '.', '..-.', '--.', '....', '..', '.---',
    '-.-', '.-..', '--', '-.', '---', '.--.', '--.-', '.-.', '...', '-', '..-',
    '...-', '.--', '-..-', '-.--', '--..']
numbers = [
    '-----', '.----', '..---', '...--', '....-', '.....', '-....', '--...',
    '---..', '----.']
# Mapping of character to morse code encoding
MORSE = dict(
    (chr(i + ord('a')), encoded)
    for i, encoded in enumerate(letters))
MORSE.update(dict(
    (chr(i + ord('0')), encoded)
    for i, encoded in enumerate(numbers)))
MORSE.update({
    '.': '.----',
    ',': '..---',
    '?': '...--'
    })


class Adsr(object):
    """Simple envelope generator."""

    def __init__(self, p, attack, decay, sustain, release):
        self.att = attack
        self.dec = decay
        self.sus = sustain
        self.rel = release

        self.trigger = p.recv()
        self.line = p.line_()
        self.trigger.patch(self.line)

    def _send(self, level, delay):
        self.trigger.send(level, delay)

    def decay(self, level):
        """Yields for the duration of the attack, then sends a decay message."""
        yield Time(self.att)
        self._send(level * self.sus, self.dec)

    def pulse(self, dur, level=1):
        """Sends a complete note of the given duration."""
        self.attack(level)
        for ev in self.decay(level): yield ev
        yield dur
        self.release()

    def attack(self, level=1):
        if level == 0:
            self.rel()
        self._send(level, self.att)

    def release(self):
        self._send(0, self.rel)


class Tapper:

    def __init__(self, p):
        self.env = Adsr(p, attack=20, decay=10, sustain=0.8, release=20)
        self.sound_map = {'.': DIHBLANK, '-': DAHBLANK}

    def out(self):
        return self.env.line

    def letter(self, char):
        for sound in MORSE.get(char.lower(), []):  # Ignore unknown characters
            for ev in self.env.pulse(self.sound_map[sound]):
                yield ev
            yield DIHBLANK
        yield DAHBLANK


def go(phrase, tapper):
    pd.dsp(True)
    for word in phrase.split():
        for char in word:
            for ev in tapper.letter(char):
                yield ev
        yield DAHBLANK
    yield WORDBLANK


def draw(p):
    osc = p.osc_(330)
    tap = Tapper(p)
    amp = p.times_()
    dac = p.dac_()
    osc.patch(amp).patch(dac)
    amp.patch(dac, 0, 1)
    tap.out().patch(amp, 0, 1)
    p.render()
    return tap


def main():
    global pd, scheduler

    logging.getLogger().setLevel(logging.DEBUG)

    pd = nypdbot.Pd()
    scheduler = nypdbot.Mta(120)

    pd.main.clear()
    tap = draw(pd.main)
    scheduler.add(go('Here come dots', tap))
    scheduler.loop()

if __name__ == '__main__':
    main()
