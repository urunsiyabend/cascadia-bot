from cascadia_bot.components import Wildlife
from cascadia_bot.scoring import (
    ScoringCards,
    bear_a,
    bear_b,
    bear_c,
    bear_d,
    elk_a,
    elk_b,
    elk_c,
    elk_d,
    family_score,
    fox_a,
    fox_b,
    fox_c,
    fox_d,
    hawk_a,
    hawk_b,
    hawk_c,
    hawk_d,
    intermediate_score,
    majority_bonuses,
    salmon_a,
    salmon_b,
    salmon_c,
    salmon_d,
    salmon_runs,
)

B, E, S, H, F = Wildlife.BEAR, Wildlife.ELK, Wildlife.SALMON, Wildlife.HAWK, Wildlife.FOX


def toks(kind, *cells):
    return {c: kind for c in cells}


def line(n, start=(0, 0), direction=(1, 0)):
    return [(start[0] + direction[0] * i, start[1] + direction[1] * i) for i in range(n)]


# ----------------------------------------------------------------------------- bears


def test_bear_a_pairs():
    two_pairs = toks(B, (0, 0), (1, 0), (5, 0), (6, 0))
    assert bear_a(two_pairs) == 11
    assert bear_a(toks(B, (0, 0), (1, 0), (2, 0))) == 0  # a group of three is not a pair
    five_pairs = toks(B, *[c for i in range(5) for c in ((4 * i, 0), (4 * i + 1, 0))])
    assert bear_a(five_pairs) == 27  # 4+ pairs


def test_bear_b_c_d():
    triple = toks(B, (0, 0), (1, 0), (1, -1))
    assert bear_b(triple) == 10
    assert bear_b(toks(B, *line(4))) == 0
    one_each = toks(B, (0, 0), (5, 0), (6, 0), (10, 0), (11, 0), (12, 0))
    assert bear_c(one_each) == 2 + 5 + 8 + 3
    two_sets = dict(one_each)
    two_sets.update(toks(B, (0, 5), (5, 5), (6, 5), (10, 5), (11, 5), (12, 5)))
    assert bear_c(two_sets) == 2 * (2 + 5 + 8 + 3)
    assert bear_c(toks(B, *line(4))) == 0
    assert bear_d(toks(B, *line(4))) == 13
    assert bear_d(toks(B, *line(5))) == 0
    assert bear_d(toks(B, (0, 0))) == 0


# ----------------------------------------------------------------------------- elk


def test_elk_a_lines():
    assert elk_a(toks(E, *line(4))) == 13
    assert elk_a(toks(E, *line(5))) == 15  # 4 + 1
    assert elk_a(toks(E, *line(7))) == 13 + 9  # 4 + 3
    # rulebook example: a line of two and a line of three = 14
    assert elk_a(toks(E, *line(2), *line(3, start=(0, 5)))) == 14
    # triangle: best is a pair + a single
    assert elk_a(toks(E, (0, 0), (1, 0), (1, -1))) == 7
    # other axes count too
    assert elk_a(toks(E, *line(3, direction=(0, 1)))) == 9
    assert elk_a(toks(E, *line(3, direction=(1, -1)))) == 9


def test_elk_b_shapes():
    assert elk_b(toks(E, (0, 0))) == 2
    assert elk_b(toks(E, (0, 0), (1, 0))) == 5
    assert elk_b(toks(E, (0, 0), (1, 0), (1, -1))) == 9
    assert elk_b(toks(E, (0, 0), (1, 0), (1, -1), (0, 1))) == 13  # diamond
    assert elk_b(toks(E, *line(3))) == 7  # straight line of 3 is not a triangle
    assert elk_b(toks(E, *line(4))) == 10  # two pairs


def test_elk_c_groups():
    assert elk_c(toks(E, *line(1))) == 2
    assert elk_c(toks(E, *line(5))) == 14
    assert elk_c(toks(E, *line(8))) == 28
    assert elk_c(toks(E, *line(10))) == 28


def test_elk_d_rings():
    ring = [(0, 1), (1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1)]
    assert elk_d(toks(E, *ring)) == 21
    assert elk_d(toks(E, *ring[:4])) == 12
    assert elk_d(toks(E, (1, 0), (-1, 0))) == 5  # partial ring with a gap
    assert elk_d(toks(E, (1, 0), (1, -1), (0, -1))) == 8  # curved arc of three


def test_elk_d_straight_line_of_three():
    # three in a straight line never surround one common hex -> best is ring(2)+single
    assert elk_d(toks(E, (0, 0), (1, 0), (2, 0))) == 5 + 2


# ----------------------------------------------------------------------------- salmon


def test_salmon_runs_and_cards():
    run4 = toks(S, *line(4))
    assert salmon_a(run4) == 12
    assert salmon_b(run4) == 11
    assert salmon_c(run4) == 12
    assert salmon_a(toks(S, *line(9))) == 25
    assert salmon_b(toks(S, *line(9))) == 17
    assert salmon_c(toks(S, *line(2))) == 0
    assert salmon_c(toks(S, *line(6))) == 15
    # triangle of three is a valid run
    assert salmon_a(toks(S, (0, 0), (1, 0), (1, -1))) == 8


def test_salmon_branch_excluded():
    # (0,0) touches three salmon -> it belongs to no run; the three arms are single runs
    t = toks(S, (0, 0), (0, 1), (1, -1), (-1, 0))
    runs = salmon_runs(t)
    assert sorted(len(r) for r in runs) == [1, 1, 1]
    assert salmon_a(t) == 6


def test_salmon_d():
    t = toks(S, *line(3))
    t[(0, 1)] = B  # adjacent to (0,0)
    t[(1, 1)] = F  # adjacent to (1,0)
    t[(5, 5)] = H  # far away
    assert salmon_d(t) == 3 + 2
    assert salmon_d(toks(S, *line(2))) == 0  # minimum run of 3


# ----------------------------------------------------------------------------- hawks


def test_hawks_basic():
    t = toks(H, (0, 0), (2, 0))
    assert hawk_a(t) == 5
    assert hawk_b(t) == 5
    assert hawk_c(t) == 3
    assert hawk_d(t) == 0  # nothing between them
    t[(1, 0)] = B
    assert hawk_d(t) == 4


def test_hawks_adjacent_and_blocking():
    t = toks(H, (0, 0), (1, 0), (3, 0))
    assert hawk_a(t) == 2  # only (3,0) is isolated
    assert hawk_b(t) == 0  # one qualifying hawk: card starts at 2
    assert hawk_c(t) == 3  # (1,0)-(3,0); (0,0) is blocked and adjacent pairs don't count
    many = toks(H, *[(3 * i, 0) for i in range(9)])
    assert hawk_a(many) == 26
    assert hawk_b(many) == 28
    assert hawk_c(many) == 3 * 8


def test_hawk_d_matching():
    # hawk - bear - hawk - elk,salmon - hawk : each hawk in at most one pair
    t = toks(H, (0, 0), (2, 0), (5, 0))
    t[(1, 0)] = B
    t[(3, 0)] = E
    t[(4, 0)] = S
    assert hawk_d(t) == 7  # best single pair: (2,0)-(5,0) with elk+salmon
    t[(0, 3)] = H
    t[(0, 1)] = F
    t[(0, 2)] = B
    # (0,0)-(0,3) has fox+bear (7) and (2,0)-(5,0) has 7
    assert hawk_d(t) == 14


# ----------------------------------------------------------------------------- foxes


def _fox_board():
    return {
        (0, 0): F,
        (0, 1): B,
        (1, 0): B,
        (1, -1): E,
        (0, -1): F,
        (-1, 0): S,
    }


def test_fox_cards():
    t = _fox_board()
    assert fox_a(t) == 4 + 3
    assert fox_b(t) == 3
    assert fox_c(t) == 2 + 1
    assert fox_d(t) == 5


def test_fox_b_three_of_a_kind_is_one_pair():
    t = {(0, 0): F, (0, 1): S, (1, 0): S, (1, -1): S, (0, -1): B, (-1, 0): B, (-1, 1): E}
    assert fox_b(t) == 5


def test_fox_d_triple_makes_one_pair():
    t = {(0, 0): F, (1, 0): F, (2, 0): F, (0, 1): B, (1, 1): B}
    assert fox_d(t) == 5


# ----------------------------------------------------------------------------- variants


def test_family_and_intermediate():
    t = {**toks(S, *line(3)), **toks(F, (0, 5), (1, 5)), (9, 9): B}
    assert family_score(t, S) == 9
    assert family_score(t, F) == 5
    assert family_score(t, B) == 2
    assert intermediate_score(t, B) == 0
    assert intermediate_score(t, F) == 5
    assert intermediate_score(toks(E, *line(6)), E) == 12
    assert str(ScoringCards.from_string("family")) == "family"
    assert ScoringCards.from_string("abcda").cards == ("A", "B", "C", "D", "A")


# ----------------------------------------------------------------------------- majorities


def test_majority_bonuses():
    assert majority_bonuses([7]) == [2]
    assert majority_bonuses([6]) == [0]
    assert majority_bonuses([5, 3]) == [2, 0]
    assert majority_bonuses([5, 5]) == [1, 1]
    assert majority_bonuses([8, 5, 3]) == [3, 1, 0]
    assert majority_bonuses([8, 8, 3]) == [2, 2, 0]
    assert majority_bonuses([8, 8, 8, 3]) == [1, 1, 1, 0]
    assert majority_bonuses([8, 5, 5, 3]) == [3, 0, 0, 0]
    assert majority_bonuses([6, 6, 7]) == [0, 0, 3]  # tie for second scores nothing
