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

import cgi

import pygraphviz as pgv

_TABLE_HTML = """<
<table cellspacing="0" cellborder="0">
 <tr>%s</tr>
 <tr><td colspan="%d">%s</td></tr>
 <tr>%s</tr>
</table>
>"""

class DotPlacer(object):

    def __init__(self):
        self.node_id = 0
        self.node_names = {}
        self.graph = pgv.AGraph(directed=True, ordering='out', ranksep=0.1)

    def _format_arg(self, arg):
        if isinstance(arg, float):
            return '%0.2f' % arg
        return cgi.escape(str(arg))

    def _box_content(self, box):
        return ' '.join([self._format_arg(arg) for arg in box.args])

    def _label(self, box):
        if box.inlet_count():
            inlets = ''.join('<td port="i%d" height="0"></td>' % i
                             for i in range(box.inlet_count()))
        else:
            inlets = '<td></td>'
        if box.outlet_count():
            outlets = ''.join('<td port="o%d" height="0"></td>' % i
                              for i in range(box.outlet_count()))
        else:
            outlets = '<td></td>'
        max_cell_count = max(1, box.inlet_count(), box.outlet_count())
        return _TABLE_HTML % (inlets,
                              max_cell_count, self._box_content(box),
                              outlets)

    def _parse_coord(self, node):
        x, y = node.attr['pos'].split(',')
        return int(x), int(y)

    def _add_nodes(self, boxes):
        # TODO: place all inlet and outlet nodes in their own respective
        # subgraphs so that their left-to-right ordering is preserved.
        # Or just punt and have pdctl place those nodes itself.
        for box in boxes:
            name = 'node%d' % self.node_id
            self.node_id += 1
            self.graph.add_node(name, label=self._label(box), shape='none',
                                fontsize=10)
            self.node_names[box] = name

    def _add_edges(self, boxes):
        for box in boxes:
            for conn in box.outgoing():
                self.graph.add_edge(
                    self.node_names[box], self.node_names[conn.inlet.box],
                    headport='i%d:n' % conn.inlet.idx,
                    tailport='o%d:s' % conn.outlet.idx,
                    arrowhead='tee')

    def place_all(self, boxes):
        self._add_nodes(boxes)
        self._add_edges(boxes)

        # Invert the y-axis to match pd.
        self.graph.layout(prog='dot', args='-y')
        # For debugging:
        #self.graph.draw('out.png')
        return dict(
            (box, self._parse_coord(self.graph.get_node(self.node_names[box])))
            for box in boxes)
