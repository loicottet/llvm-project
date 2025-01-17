#!/usr/bin/env python
#
#===- exploded-graph-rewriter.py - ExplodedGraph dump tool -----*- python -*--#
#
# Part of the LLVM Project, under the Apache License v2.0 with LLVM Exceptions.
# See https://llvm.org/LICENSE.txt for license information.
# SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
#
#===-----------------------------------------------------------------------===#


from __future__ import print_function

import argparse
import collections
import json
import logging
import re


# A helper function for finding the difference between two dictionaries.
def diff_dicts(curr, prev):
    removed = [k for k in prev if k not in curr or curr[k] != prev[k]]
    added = [k for k in curr if k not in prev or curr[k] != prev[k]]
    return (removed, added)


# Represents any program state trait that is a dictionary of key-value pairs.
class GenericMap(object):
    def __init__(self, generic_map):
        self.generic_map = generic_map

    def diff(self, prev):
        return diff_dicts(self.generic_map, prev.generic_map)

    def is_different(self, prev):
        removed, added = self.diff(prev)
        return len(removed) != 0 or len(added) != 0


# A deserialized source location.
class SourceLocation(object):
    def __init__(self, json_loc):
        super(SourceLocation, self).__init__()
        self.line = json_loc['line']
        self.col = json_loc['column']
        self.filename = json_loc['filename'] \
            if 'filename' in json_loc else '(main file)'


# A deserialized program point.
class ProgramPoint(object):
    def __init__(self, json_pp):
        super(ProgramPoint, self).__init__()
        self.kind = json_pp['kind']
        self.tag = json_pp['tag']
        if self.kind == 'Edge':
            self.src_id = json_pp['src_id']
            self.dst_id = json_pp['dst_id']
        elif self.kind == 'Statement':
            self.stmt_kind = json_pp['stmt_kind']
            self.pointer = json_pp['pointer']
            self.pretty = json_pp['pretty']
            self.loc = SourceLocation(json_pp['location']) \
                if json_pp['location'] is not None else None
        elif self.kind == 'BlockEntrance':
            self.block_id = json_pp['block_id']


# A single expression acting as a key in a deserialized Environment.
class EnvironmentBindingKey(object):
    def __init__(self, json_ek):
        super(EnvironmentBindingKey, self).__init__()
        self.stmt_id = json_ek['stmt_id']
        self.pretty = json_ek['pretty']

    def _key(self):
        return self.stmt_id

    def __eq__(self, other):
        return self._key() == other._key()

    def __hash__(self):
        return hash(self._key())


# Deserialized description of a location context.
class LocationContext(object):
    def __init__(self, json_frame):
        super(LocationContext, self).__init__()
        self.lctx_id = json_frame['lctx_id']
        self.caption = json_frame['location_context']
        self.decl = json_frame['calling']
        self.line = json_frame['call_line']

    def _key(self):
        return self.lctx_id

    def __eq__(self, other):
        return self._key() == other._key()

    def __hash__(self):
        return hash(self._key())


# A group of deserialized Environment bindings that correspond to a specific
# location context.
class EnvironmentFrame(object):
    def __init__(self, json_frame):
        super(EnvironmentFrame, self).__init__()
        self.location_context = LocationContext(json_frame)
        self.bindings = collections.OrderedDict(
            [(EnvironmentBindingKey(b),
              b['value']) for b in json_frame['items']]
            if json_frame['items'] is not None else [])

    def diff_bindings(self, prev):
        return diff_dicts(self.bindings, prev.bindings)

    def is_different(self, prev):
        removed, added = self.diff_bindings(prev)
        return len(removed) != 0 or len(added) != 0


# A deserialized Environment.
class Environment(object):
    def __init__(self, json_e):
        super(Environment, self).__init__()
        self.ptr = json_e['pointer']
        self.frames = [EnvironmentFrame(f) for f in json_e['items']]

    def diff_frames(self, prev):
        # TODO: It's difficult to display a good diff when frame numbers shift.
        if len(self.frames) != len(prev.frames):
            return None

        updated = []
        for i in range(len(self.frames)):
            f = self.frames[i]
            prev_f = prev.frames[i]
            if f.location_context == prev_f.location_context:
                if f.is_different(prev_f):
                    updated.append(i)
            else:
                # We have the whole frame replaced with another frame.
                # TODO: Produce a nice diff.
                return None

        # TODO: Add support for added/removed.
        return updated

    def is_different(self, prev):
        updated = self.diff_frames(prev)
        return updated is None or len(updated) > 0


# A single binding key in a deserialized RegionStore cluster.
class StoreBindingKey(object):
    def __init__(self, json_sk):
        super(StoreBindingKey, self).__init__()
        self.kind = json_sk['kind']
        self.offset = json_sk['offset']

    def _key(self):
        return (self.kind, self.offset)

    def __eq__(self, other):
        return self._key() == other._key()

    def __hash__(self):
        return hash(self._key())


# A single cluster of the deserialized RegionStore.
class StoreCluster(object):
    def __init__(self, json_sc):
        super(StoreCluster, self).__init__()
        self.base_region = json_sc['cluster']
        self.bindings = collections.OrderedDict(
            [(StoreBindingKey(b), b['value']) for b in json_sc['items']])

    def diff_bindings(self, prev):
        return diff_dicts(self.bindings, prev.bindings)

    def is_different(self, prev):
        removed, added = self.diff_bindings(prev)
        return len(removed) != 0 or len(added) != 0


# A deserialized RegionStore.
class Store(object):
    def __init__(self, json_s):
        super(Store, self).__init__()
        self.ptr = json_s['pointer']
        self.clusters = collections.OrderedDict(
            [(c['pointer'], StoreCluster(c)) for c in json_s['items']])

    def diff_clusters(self, prev):
        removed = [k for k in prev.clusters if k not in self.clusters]
        added = [k for k in self.clusters if k not in prev.clusters]
        updated = [k for k in prev.clusters if k in self.clusters
                   and prev.clusters[k].is_different(self.clusters[k])]
        return (removed, added, updated)

    def is_different(self, prev):
        removed, added, updated = self.diff_clusters(prev)
        return len(removed) != 0 or len(added) != 0 or len(updated) != 0


# A deserialized program state.
class ProgramState(object):
    def __init__(self, state_id, json_ps):
        super(ProgramState, self).__init__()
        logging.debug('Adding ProgramState ' + str(state_id))

        self.state_id = state_id
        self.store = Store(json_ps['store']) \
            if json_ps['store'] is not None else None
        self.environment = Environment(json_ps['environment']) \
            if json_ps['environment'] is not None else None
        self.constraints = GenericMap(collections.OrderedDict([
            (c['symbol'], c['range']) for c in json_ps['constraints']
        ])) if json_ps['constraints'] is not None else None
        # TODO: Objects under construction.
        # TODO: Dynamic types of objects.
        # TODO: Checker messages.


# A deserialized exploded graph node. Has a default constructor because it
# may be referenced as part of an edge before its contents are deserialized,
# and in this moment we already need a room for predecessors and successors.
class ExplodedNode(object):
    def __init__(self):
        super(ExplodedNode, self).__init__()
        self.predecessors = []
        self.successors = []

    def construct(self, node_id, json_node):
        logging.debug('Adding ' + node_id)
        self.node_id = json_node['node_id']
        self.ptr = json_node['pointer']
        self.points = [ProgramPoint(p) for p in json_node['program_points']]
        self.state = ProgramState(json_node['state_id'],
                                  json_node['program_state']) \
            if json_node['program_state'] is not None else None

        assert self.node_name() == node_id

    def node_name(self):
        return 'Node' + self.ptr


# A deserialized ExplodedGraph. Constructed by consuming a .dot file
# line-by-line.
class ExplodedGraph(object):
    # Parse .dot files with regular expressions.
    node_re = re.compile(
        '^(Node0x[0-9a-f]*) \\[shape=record,.*label="{(.*)\\\\l}"\\];$')
    edge_re = re.compile(
        '^(Node0x[0-9a-f]*) -> (Node0x[0-9a-f]*);$')

    def __init__(self):
        super(ExplodedGraph, self).__init__()
        self.nodes = collections.defaultdict(ExplodedNode)
        self.root_id = None
        self.incomplete_line = ''

    def add_raw_line(self, raw_line):
        if raw_line.startswith('//'):
            return

        # Allow line breaks by waiting for ';'. This is not valid in
        # a .dot file, but it is useful for writing tests.
        if len(raw_line) > 0 and raw_line[-1] != ';':
            self.incomplete_line += raw_line
            return
        raw_line = self.incomplete_line + raw_line
        self.incomplete_line = ''

        # Apply regexps one by one to see if it's a node or an edge
        # and extract contents if necessary.
        logging.debug('Line: ' + raw_line)
        result = self.edge_re.match(raw_line)
        if result is not None:
            logging.debug('Classified as edge line.')
            pred = result.group(1)
            succ = result.group(2)
            self.nodes[pred].successors.append(succ)
            self.nodes[succ].predecessors.append(pred)
            return
        result = self.node_re.match(raw_line)
        if result is not None:
            logging.debug('Classified as node line.')
            node_id = result.group(1)
            if len(self.nodes) == 0:
                self.root_id = node_id
            # Note: when writing tests you don't need to escape everything,
            # even though in a valid dot file everything is escaped.
            node_label = result.group(2).replace('\\l', '') \
                                        .replace('&nbsp;', '') \
                                        .replace('\\"', '"') \
                                        .replace('\\{', '{') \
                                        .replace('\\}', '}') \
                                        .replace('\\\\', '\\') \
                                        .replace('\\|', '|') \
                                        .replace('\\<', '\\\\<') \
                                        .replace('\\>', '\\\\>') \
                                        .rstrip(',')
            logging.debug(node_label)
            json_node = json.loads(node_label)
            self.nodes[node_id].construct(node_id, json_node)
            return
        logging.debug('Skipping.')


# A visitor that dumps the ExplodedGraph into a DOT file with fancy HTML-based
# syntax highlighing.
class DotDumpVisitor(object):
    def __init__(self, do_diffs):
        super(DotDumpVisitor, self).__init__()
        self._do_diffs = do_diffs

    @staticmethod
    def _dump_raw(s):
        print(s, end='')

    @staticmethod
    def _dump(s):
        print(s.replace('&', '&amp;')
               .replace('{', '\\{')
               .replace('}', '\\}')
               .replace('\\<', '&lt;')
               .replace('\\>', '&gt;')
               .replace('\\l', '<br />')
               .replace('|', '\\|'), end='')

    @staticmethod
    def _diff_plus_minus(is_added):
        if is_added is None:
            return ''
        if is_added:
            return '<font color="forestgreen">+</font>'
        return '<font color="red">-</font>'

    def visit_begin_graph(self, graph):
        self._graph = graph
        self._dump_raw('digraph "ExplodedGraph" {\n')
        self._dump_raw('label="";\n')

    def visit_program_point(self, p):
        if p.kind in ['Edge', 'BlockEntrance', 'BlockExit']:
            color = 'gold3'
        elif p.kind in ['PreStmtPurgeDeadSymbols',
                        'PostStmtPurgeDeadSymbols']:
            color = 'red'
        elif p.kind in ['CallEnter', 'CallExitBegin', 'CallExitEnd']:
            color = 'blue'
        elif p.kind in ['Statement']:
            color = 'cyan3'
        else:
            color = 'forestgreen'

        if p.kind == 'Statement':
            if p.loc is not None:
                self._dump('<tr><td align="left" width="0">'
                           '%s:<b>%s</b>:<b>%s</b>:</td>'
                           '<td align="left" width="0"><font color="%s">'
                           '%s</font></td><td>%s</td></tr>'
                           % (p.loc.filename, p.loc.line,
                              p.loc.col, color, p.stmt_kind, p.pretty))
            else:
                self._dump('<tr><td align="left" width="0">'
                           '<i>Invalid Source Location</i>:</td>'
                           '<td align="left" width="0">'
                           '<font color="%s">%s</font></td><td>%s</td></tr>'
                           % (color, p.stmt_kind, p.pretty))
        elif p.kind == 'Edge':
            self._dump('<tr><td width="0"></td>'
                       '<td align="left" width="0">'
                       '<font color="%s">%s</font></td><td align="left">'
                       '[B%d] -\\> [B%d]</td></tr>'
                       % (color, p.kind, p.src_id, p.dst_id))
        else:
            # TODO: Print more stuff for other kinds of points.
            self._dump('<tr><td width="0"></td>'
                       '<td align="left" width="0" colspan="2">'
                       '<font color="%s">%s</font></td></tr>'
                       % (color, p.kind))

    def visit_environment(self, e, prev_e=None):
        self._dump('<table border="0">')

        def dump_location_context(lc, is_added=None):
            self._dump('<tr><td>%s</td>'
                       '<td align="left"><b>%s</b></td>'
                       '<td align="left"><font color="grey60">%s </font>'
                       '%s</td></tr>'
                       % (self._diff_plus_minus(is_added),
                          lc.caption, lc.decl,
                          ('(line %s)' % lc.line) if lc.line is not None
                          else ''))

        def dump_binding(f, b, is_added=None):
            self._dump('<tr><td>%s</td>'
                       '<td align="left"><i>S%s</i></td>'
                       '<td align="left">%s</td>'
                       '<td align="left">%s</td></tr>'
                       % (self._diff_plus_minus(is_added),
                          b.stmt_id, b.pretty, f.bindings[b]))

        frames_updated = e.diff_frames(prev_e) if prev_e is not None else None
        if frames_updated:
            for i in frames_updated:
                f = e.frames[i]
                prev_f = prev_e.frames[i]
                dump_location_context(f.location_context)
                bindings_removed, bindings_added = f.diff_bindings(prev_f)
                for b in bindings_removed:
                    dump_binding(prev_f, b, False)
                for b in bindings_added:
                    dump_binding(f, b, True)
        else:
            for f in e.frames:
                dump_location_context(f.location_context)
                for b in f.bindings:
                    dump_binding(f, b)

        self._dump('</table>')

    def visit_environment_in_state(self, s, prev_s=None):
        self._dump('<tr><td align="left">'
                   '<b>Environment: </b>')
        if s.environment is None:
            self._dump('<i> Nothing!</i>')
        else:
            if prev_s is not None and prev_s.environment is not None:
                if s.environment.is_different(prev_s.environment):
                    self._dump('</td></tr><tr><td align="left">')
                    self.visit_environment(s.environment, prev_s.environment)
                else:
                    self._dump('<i> No changes!</i>')
            else:
                self._dump('</td></tr><tr><td align="left">')
                self.visit_environment(s.environment)

        self._dump('</td></tr>')

    def visit_store(self, s, prev_s=None):
        self._dump('<table border="0">')

        def dump_binding(s, c, b, is_added=None):
            self._dump('<tr><td>%s</td>'
                       '<td align="left">%s</td>'
                       '<td align="left">%s</td>'
                       '<td align="left">%s</td>'
                       '<td align="left">%s</td></tr>'
                       % (self._diff_plus_minus(is_added),
                          s.clusters[c].base_region, b.offset,
                          '(<i>Default</i>)' if b.kind == 'Default'
                          else '',
                          s.clusters[c].bindings[b]))

        if prev_s is not None:
            clusters_removed, clusters_added, clusters_updated = \
                s.diff_clusters(prev_s)
            for c in clusters_removed:
                for b in prev_s.clusters[c].bindings:
                    dump_binding(prev_s, c, b, False)
            for c in clusters_updated:
                bindings_removed, bindings_added = \
                    s.clusters[c].diff_bindings(prev_s.clusters[c])
                for b in bindings_removed:
                    dump_binding(prev_s, c, b, False)
                for b in bindings_added:
                    dump_binding(s, c, b, True)
            for c in clusters_added:
                for b in s.clusters[c].bindings:
                    dump_binding(s, c, b, True)
        else:
            for c in s.clusters:
                for b in s.clusters[c].bindings:
                    dump_binding(s, c, b)

        self._dump('</table>')

    def visit_store_in_state(self, s, prev_s=None):
        self._dump('<tr><td align="left"><b>Store: </b>')
        if s.store is None:
            self._dump('<i> Nothing!</i>')
        else:
            if prev_s is not None and prev_s.store is not None:
                if s.store.is_different(prev_s.store):
                    self._dump('</td></tr><tr><td align="left">')
                    self.visit_store(s.store, prev_s.store)
                else:
                    self._dump('<i> No changes!</i>')
            else:
                self._dump('</td></tr><tr><td align="left">')
                self.visit_store(s.store)
        self._dump('</td></tr>')

    def visit_generic_map(self, m, prev_m=None):
        self._dump('<table border="0">')

        def dump_pair(m, k, is_added=None):
            self._dump('<tr><td>%s</td>'
                       '<td align="left">%s</td>'
                       '<td align="left">%s</td></tr>'
                       % (self._diff_plus_minus(is_added),
                          k, m.generic_map[k]))

        if prev_m is not None:
            removed, added = m.diff(prev_m)
            for k in removed:
                dump_pair(prev_m, k, False)
            for k in added:
                dump_pair(m, k, True)
        else:
            for k in m.generic_map:
                dump_pair(m, k, None)

        self._dump('</table>')

    def visit_generic_map_in_state(self, selector, s, prev_s=None):
        self._dump('<tr><td align="left">'
                   '<b>Ranges: </b>')
        m = getattr(s, selector)
        if m is None:
            self._dump('<i> Nothing!</i>')
        else:
            prev_m = None
            if prev_s is not None:
                prev_m = getattr(prev_s, selector)
                if prev_m is not None:
                    if m.is_different(prev_m):
                        self._dump('</td></tr><tr><td align="left">')
                        self.visit_generic_map(m, prev_m)
                    else:
                        self._dump('<i> No changes!</i>')
            if prev_m is None:
                self._dump('</td></tr><tr><td align="left">')
                self.visit_generic_map(m)
        self._dump('</td></tr>')

    def visit_state(self, s, prev_s):
        self.visit_store_in_state(s, prev_s)
        self._dump('<hr />')
        self.visit_environment_in_state(s, prev_s)
        self._dump('<hr />')
        self.visit_generic_map_in_state('constraints', s, prev_s)

    def visit_node(self, node):
        self._dump('%s [shape=record,label=<<table border="0">'
                   % (node.node_name()))

        self._dump('<tr><td bgcolor="grey"><b>Node %d (%s) - '
                   'State %s</b></td></tr>'
                   % (node.node_id, node.ptr, node.state.state_id
                      if node.state is not None else 'Unspecified'))
        self._dump('<tr><td align="left" width="0">')
        if len(node.points) > 1:
            self._dump('<b>Program points:</b></td></tr>')
        else:
            self._dump('<b>Program point:</b></td></tr>')
        self._dump('<tr><td align="left" width="0">'
                   '<table border="0" align="left" width="0">')
        for p in node.points:
            self.visit_program_point(p)
        self._dump('</table></td></tr>')

        if node.state is not None:
            self._dump('<hr />')
            prev_s = None
            # Do diffs only when we have a unique predecessor.
            # Don't do diffs on the leaf nodes because they're
            # the important ones.
            if self._do_diffs and len(node.predecessors) == 1 \
               and len(node.successors) > 0:
                prev_s = self._graph.nodes[node.predecessors[0]].state
            self.visit_state(node.state, prev_s)
        self._dump_raw('</table>>];\n')

    def visit_edge(self, pred, succ):
        self._dump_raw('%s -> %s;\n' % (pred.node_name(), succ.node_name()))

    def visit_end_of_graph(self):
        self._dump_raw('}\n')


# A class that encapsulates traversal of the ExplodedGraph. Different explorer
# kinds could potentially traverse specific sub-graphs.
class Explorer(object):
    def __init__(self):
        super(Explorer, self).__init__()

    def explore(self, graph, visitor):
        visitor.visit_begin_graph(graph)
        for node in sorted(graph.nodes):
            logging.debug('Visiting ' + node)
            visitor.visit_node(graph.nodes[node])
            for succ in sorted(graph.nodes[node].successors):
                logging.debug('Visiting edge: %s -> %s ' % (node, succ))
                visitor.visit_edge(graph.nodes[node], graph.nodes[succ])
        visitor.visit_end_of_graph()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('filename', type=str)
    parser.add_argument('-v', '--verbose', action='store_const',
                        dest='loglevel', const=logging.DEBUG,
                        default=logging.WARNING,
                        help='enable info prints')
    parser.add_argument('-d', '--diff', action='store_const', dest='diff',
                        const=True, default=False,
                        help='display differences between states')
    args = parser.parse_args()
    logging.basicConfig(level=args.loglevel)

    graph = ExplodedGraph()
    with open(args.filename) as fd:
        for raw_line in fd:
            raw_line = raw_line.strip()
            graph.add_raw_line(raw_line)

    explorer = Explorer()
    visitor = DotDumpVisitor(args.diff)
    explorer.explore(graph, visitor)


if __name__ == '__main__':
    main()
