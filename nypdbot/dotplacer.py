# Copyright 2012 Jacob Lee.
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
Pure Data object placer that uses graphviz to lay out the patch.
"""

import pygraphviz as pgv


class DotPlacer(object):

    def __init__(self):
        self.node_id = 0
        self.node_names = {}
        self.graph = pgv.AGraph(directed=True, ordering='out', ranksep=0.1)

    def _format_arg(self, arg):
        if isinstance(arg, float):
            return '%0.2f' % arg
        return str(arg)

    def _label(self, box):
        return '%s %s' % (
            box.name,
            ' '.join(self._format_arg(arg) for arg in box.args))

    def _parse_coord(self, node):
        x, y = node.attr['pos'].split(',')
        return int(x), int(y)

    def _add_nodes(self, boxes):
        for box in boxes:
            name = 'node%d' % self.node_id
            self.node_id += 1
            self.graph.add_node(name, label=self._label(box), shape='box',
                                fontsize=10)
            self.node_names[box] = name

    def _add_edges(self, boxes):
        for box in boxes:
            for child in box.children():
                self.graph.add_edge(
                    self.node_names[box], self.node_names[child],
                    arrowType='tee')

    def place_all(self, boxes):
        self._add_nodes(boxes)
        self._add_edges(boxes)

        # Invert the y-axis to match pd.
        self.graph.layout(prog='dot', args='-y')
        return dict(
            (box, self._parse_coord(self.graph.get_node(self.node_names[box])))
            for box in boxes)
