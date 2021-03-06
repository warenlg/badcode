
import collections
import itertools
import typing

import bblfsh

class Snippet:
    def __init__(self,
            uast: bblfsh.Node,
            text: str) -> None:
        self._ser = None
        self._uast = uast
        self._text = text

    @staticmethod
    def from_uast_blob(
            uast: bblfsh.Node,
            blob: str) -> 'Snippet':
        start, end = get_start_end_lines(uast)
        lines = blob.split('\n')
        lines = [l for n, l in enumerate(lines) if n + 1 >= start and n + 1 <= end]
        text = '\n'.join(lines)
        return Snippet(uast, text)

    @property
    def uast(self):
        self._ensure_unser()
        return self._uast
    
    @property
    def text(self):
        return self._text

    def _ensure_ser(self):
        if self._ser is None:
            self._ser = self._uast.SerializeToString()

    def _ensure_unser(self):
        if self._uast is None:
            self._uast = bblfsh.Node()
            self._uast.ParseFromString(self._ser)

    def reset_ser(self):
        if self._uast is not None:
            self._ser = None
        else:
            raise Exception('cannot reset ser without uast')

    def __hash__(self) -> int:
        return uast_hash(self.uast)

    def __eq__(self, other) -> bool:
        return uast_eq(self.uast, other.uast)

    def __getstate__(self):
        self._ensure_ser()
        state = dict(self.__dict__)
        state['_uast'] = None
        return state

    def __setstate__(self, d):
        self._uast = d.get('_uast', None)
        self._ser = d.get('_ser', None)
        self._text = d.get('_text', None)

class Path:
    def __init__(self,
            path: typing.List['Path'],
            node: bblfsh.Node,
            lines: typing.Set[int]) -> None:
        self.path = path
        self.node = node
        self.is_relevant = is_relevant_node(node, lines=lines)
        self._is_relevant_tree = None
        self._children = None
        self._lines = lines
        self._depth = None
        self._size = None

    @property
    def children(self):
        if self._children is None:
            self._children = [Path(
                path=self.path + [self],
                node=c,
                lines=self._lines) for c in self.node.children]
        return self._children

    @property
    def depth(self):
        if self._depth is None:
            if len(self.children) == 0:
                self._depth = 1
            else:
                self._depth = max([c.depth for c in self.children])+1
        return self._depth

    @property
    def size(self):
        if self._size is None:
            if len(self.children) == 0:
                self._size = 1
            else:
                self._size = sum([c.size for c in self.children])+1
        return self._size

    @property
    def is_relevant_tree(self):
        if self._is_relevant_tree is None:
            self._is_relevant_tree = self.__is_relevant_tree()
        return self._is_relevant_tree

    def __is_relevant_tree(self):
        if self.is_relevant:
            return True
        for c in self.children:
            if c.is_relevant_tree:
                return True
        return False

def extract_paths(root: bblfsh.Node, lines: typing.Set[int]) -> typing.Generator[Path,None,None]:
    queue = [Path(path=[], node=root, lines=lines)]
    while len(queue) > 0:
        path = queue.pop()
        if len(path.children) == 0:
            yield path
            continue
        queue.extend(path.children)

def extract_subtrees(
        uast: bblfsh.Node,
        min_depth: int,
        max_depth: int,
        min_size: int,
        max_size: int,
        lines: typing.Iterable[int]) -> typing.Generator[bblfsh.Node,None,None]:
    if not isinstance(lines, set):
        lines = set(lines)

    already_extracted: typing.Set[int] = set([])

    paths = extract_paths(uast, lines=lines)
    for path in paths:
        if path.size > max_size:
            continue
        is_relevant = path.is_relevant
        if is_relevant and path.size >= min_size and path.depth >= min_depth:
            yield path.node
        if max_depth == 1:
            continue
        for depth in range(2, max_depth+1):
            if len(path.path) < depth-1:
                break
            parent = path.path[-1*(depth - 1)]
            if parent.depth > max_depth:
                break
            if parent.size > max_size:
                break
            if parent.size < min_size:
                continue
            if parent.depth < min_depth:
                continue
            is_relevant |= parent.is_relevant
            if is_relevant:
                i = id(parent.node)
                if i in already_extracted:
                    continue
                already_extracted.add(i)
                yield parent.node

def bblfsh_monkey_patch() -> None:
    bblfsh.Node.__hash__ = uast_hash
    bblfsh.Node.__eq__ = uast_eq

def uast_iter(t: bblfsh.Node) -> typing.Generator[bblfsh.Node, None, None]:
    stack = collections.deque()
    stack.append(t)
    while stack:
        n = stack.pop()
        yield n
        stack.extend(n.children)

def uast_hash(a: bblfsh.Node) -> int:
    return hash(tuple(uast_tokens(a, 20)))
    
def uast_types(a: bblfsh.Node, max: int) -> typing.List[str]:
    it = itertools.islice(uast_iter(a), max)
    return [n.internal_type for n in it]

def uast_tokens(a: bblfsh.Node, max: int) -> typing.List[str]:
    it = itertools.islice(uast_iter(a), max)
    return [n.token for n in it]

def uast_eq_node(a: bblfsh.Node, b: bblfsh.Node) -> bool:
    if a.token != b.token:
        return False
    if a.internal_type != b.internal_type:
        return False
    return True

def uast_eq_node_wildcards(a: bblfsh.Node, b: bblfsh.Node) -> bool:
    if a.token != b.token and a.token != 'MATCH_ANY' and b.token != 'MATCH_ANY':
        return False
    if a.internal_type != b.internal_type and a.internal_type != 'MATCH_ANY' and b.internal_type != 'MATCH_ANY':
        return False
    return True

def uast_eq(a: bblfsh.Node, b: bblfsh.Node, eqf=uast_eq_node) -> bool:
    if b is None:
        return False
    for an, bn in itertools.zip_longest(uast_iter(a), uast_iter(b)):
        if an is None or bn is None:
            return False
        if not eqf(an, bn):
            return False
    return True

def uast_eq_wildcards(a: bblfsh.Node, b: bblfsh.Node) -> bool:
    return uast_eq(a, b, eqf=uast_eq_node_wildcards)

def uast_size(n: bblfsh.Node) -> int:
    if len(n.children) == 0:
        return 1
    return 1 + sum([uast_size(x) for x in n.children])

def uast_pretty_format(n: bblfsh.Node, indent=0) -> str:
    s = '%stype: %s, token: %s' % ('. ' * indent, n.internal_type, n.token)
    for c in n.children:
        s += '\n' + uast_pretty_format(c, indent=indent+1)
    return s

def is_relevant_tree(uast: bblfsh.Node, lines: typing.Set[int]) -> bool:
    if is_relevant_node(uast, lines):
        return True
    for child in uast.children:
        if is_relevant_tree(child, lines):
            return True
    return False

def is_relevant_node(uast: bblfsh.Node, lines: typing.Set[int]) -> bool:
    if uast.start_position.line in lines:
        return True
    if uast.end_position.line in lines:
        return True
    if uast.start_position.line >= 1 and uast.end_position.line >= 1:
        for line in lines:
            if line >= uast.start_position.line and line <= uast.end_position.line:
                return True
    return False

def get_start_end_lines(uast: bblfsh.Node) -> typing.Tuple[int, int]:
    start = uast.start_position.line
    end = uast.end_position.line
    for child in uast.children:
        cstart, cend = get_start_end_lines(child)
        if start == 0 or cstart < start:
            start = cstart
        if end == 0 or cend > end:
            end = cend
    return start, end

def filter_node(uast: bblfsh.Node) -> None:
    while len(uast.roles) > 0:
        uast.roles.pop()
    uast.properties.clear()
    for child in list(uast.children):
        if child.internal_type == 'Position':
            uast.children.remove(child)
            continue
        filter_node(child)

def remove_positions(uast: bblfsh.Node) -> None:
    set_zero_position(uast)
    for child in uast.children:
        remove_positions(child)

def set_zero_position(uast: bblfsh.Node) -> None:
    uast.start_position.offset = 0
    uast.start_position.line = 0
    uast.start_position.col = 0
    uast.end_position.offset = 0
    uast.end_position.line = 0
    uast.end_position.col = 0
