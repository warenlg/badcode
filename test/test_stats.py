
import unittest

from bblfsh import Node
from badcode.bblfsh import Snippet
from badcode.stats import Stats

def test_stats_iadd():
    a = Node()
    a.token = 'A'
    a = Snippet(text='A', uast=a)

    s1 = Stats()
    s1.added('repo1', a)
    assert {'added': 1} == s1.totals[a]

    s2 = Stats()
    s2.deleted('repo1', a)
    assert {'deleted': 1} == s2.totals[a]

    s3 = Stats()
    s3 += s1
    s3 += s2

    assert {'added': 1, 'deleted': 1} == s3.totals[a]