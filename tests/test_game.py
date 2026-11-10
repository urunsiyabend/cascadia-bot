import random
from collections import Counter

import pytest

from cascadia_bot import Board, Game, GameConfig, IllegalAction, NatureWipe, Placement, WipeOverpopulation
from cascadia_bot.bots import make_bot
from cascadia_bot.components import HABITAT_TILES, STARTER_TILES, TILE_BY_ID, Habitat, Wildlife
from cascadia_bot.runner import play_game
from cascadia_bot.scoring import CARD_LETTERS, ScoringCards


def total_tokens(g: Game) -> int:
    return (
        len(g.bag)
        + len(g.set_aside)
        + len(g.removed_tokens)
        + sum(len(b.tokens) for b in g.boards)
        + sum(t is not None for t in g.display_tokens)
    )


# ----------------------------------------------------------------------------- components


def test_component_counts():
    assert len(HABITAT_TILES) == 85
    assert sum(t.keystone for t in HABITAT_TILES) == 25
    assert len(STARTER_TILES) == 5 and all(len(s) == 3 for s in STARTER_TILES)
    # every wildlife appears on the same number of tiles, every habitat equally often
    assert set(Counter(w for t in HABITAT_TILES for w in t.wildlife).values()) == {32}
    assert set(Counter(h for t in HABITAT_TILES for h in t.habitats).values()) == {29}
    pairs = Counter(frozenset(t.habitats) for t in HABITAT_TILES if not t.keystone)
    assert len(pairs) == 10 and set(pairs.values()) == {6}


def test_tile_edges_rotation():
    tile = next(t for t in HABITAT_TILES if t.code == "FPbe")
    e0 = tile.edges(0)
    assert e0 == (Habitat.FOREST,) * 3 + (Habitat.PRAIRIE,) * 3
    assert tile.edges(1) == e0[-1:] + e0[:-1]
    keystone = next(t for t in HABITAT_TILES if t.keystone)
    assert keystone.rotations() == (0,)


# ----------------------------------------------------------------------------- corridors


def test_corridor_requires_matching_edges():
    b = Board()
    forest = next(t for t in HABITAT_TILES if t.code == "FFb")
    fp = next(t for t in HABITAT_TILES if t.code == "FPbe")
    b._put_tile((0, 0), forest, 0)
    # (1,0) is direction 1 from (0,0); the new tile's edge 4 faces back.
    b.place_tile((1, 0), fp, 2)  # forest on edges 2,3,4 -> edge 4 is forest
    assert b.largest_corridor(Habitat.FOREST) == 2
    b2 = Board()
    b2._put_tile((0, 0), forest, 0)
    b2.place_tile((1, 0), fp, 5)  # forest on 5,0,1 -> edge 4 is prairie
    assert b2.largest_corridor(Habitat.FOREST) == 1
    assert b2.largest_corridor(Habitat.PRAIRIE) == 1


def test_incremental_corridor_matches_full_recompute():
    rng = random.Random(7)
    for seed in range(5):
        b = Board.with_starter(seed % 5)
        tiles = list(HABITAT_TILES)
        rng.shuffle(tiles)
        for tile in tiles[:25]:
            pos = rng.choice(sorted(b.frontier()))
            rot = rng.choice(tile.rotations())
            predicted = b.corridor_sizes_after(pos, tile, rot)
            b.place_tile(pos, tile, rot)
            for h, size in predicted.items():
                assert b.largest_corridor(h) == size


# ----------------------------------------------------------------------------- game flow


@pytest.mark.parametrize("players", [1, 2, 3, 4])
def test_every_player_gets_twenty_turns(players):
    bots = [make_bot("random", seed=i) for i in range(players)]
    res = play_game(bots, GameConfig(num_players=players, seed=players))
    g = res.game
    assert g.game_over
    assert g.turns_taken == [20] * players
    assert all(len(b.tiles) == 23 for b in g.boards)
    assert total_tokens(g) == 100


def test_initial_setup():
    g = Game(GameConfig(num_players=3, seed=1))
    assert len(g.tile_stack) == 63 - 4
    assert len(set(g.starter_indices)) == 3
    assert all(b.nature_tokens == 0 for b in g.boards)
    assert all(len(b.tiles) == 3 for b in g.boards)
    assert total_tokens(g) == 100
    assert g.cards.mode == "standard"


def _game_with_display(tokens, nature=0, seed=0):
    g = Game(GameConfig(num_players=2, seed=seed, cards=ScoringCards()))
    g.bag.extend(t for t in g.display_tokens if t is not None)
    for t in tokens:
        g.bag.remove(t)
    g.display_tokens = list(tokens)
    g.board.nature_tokens = nature
    g.overpopulation_wipe_used = False
    return g


def test_optional_overpopulation_wipe_once_per_turn():
    B, E = Wildlife.BEAR, Wildlife.ELK
    g = _game_with_display([B, B, B, E])
    assert g.can_wipe_overpopulation()
    g.apply_pre_action(WipeOverpopulation())
    assert g.display_tokens[3] == E
    assert len(g.set_aside) >= 3
    assert not g.can_wipe_overpopulation()
    with pytest.raises(IllegalAction):
        g.apply_pre_action(WipeOverpopulation())
    assert total_tokens(g) == 100


def test_four_of_a_kind_is_wiped_automatically():
    H = Wildlife.HAWK
    g = _game_with_display([H, H, H, H])
    g._resolve_four_of_a_kind()
    assert len(set(g.display_tokens)) > 1
    assert total_tokens(g) == 100


def test_nature_token_actions():
    B, E, S, F = Wildlife.BEAR, Wildlife.ELK, Wildlife.SALMON, Wildlife.FOX
    g = _game_with_display([B, E, S, F], nature=2)
    with pytest.raises(IllegalAction):
        g.apply_pre_action(NatureWipe(()))
    g.apply_pre_action(NatureWipe((0, 2)))
    assert g.board.nature_tokens == 1
    assert len(g.set_aside) == 2
    # mixed draft costs the last nature token
    pos = sorted(g.board.frontier())[0]
    p = Placement(0, 1, pos, 0, None)
    g.apply_placement(p)
    assert g.boards[0].nature_tokens == 0
    assert g.set_aside == []
    assert total_tokens(g) == 100


def test_mixed_draft_needs_nature_token():
    g = Game(GameConfig(num_players=2, seed=3))
    g.board.nature_tokens = 0
    pos = sorted(g.board.frontier())[0]
    with pytest.raises(IllegalAction):
        g.apply_placement(Placement(0, 1, pos, 0, None))


def test_illegal_tile_and_token_positions():
    g = Game(GameConfig(num_players=2, seed=4))
    with pytest.raises(IllegalAction):
        g.apply_placement(Placement(0, 0, (50, 50), 0, None))
    with pytest.raises(IllegalAction):
        g.apply_placement(Placement(0, 0, (0, 0), 0, None))  # occupied
    tile = g.display_tiles[0]
    tok = g.display_tokens[0]
    pos = sorted(g.board.frontier())[0]
    if tok not in tile.wildlife:
        with pytest.raises(IllegalAction):
            g.apply_placement(Placement(0, 0, pos, 0, pos))


def test_keystone_gives_nature_token():
    g = Game(GameConfig(num_players=2, seed=5))
    board = g.board
    key_pos = next(p for p, pt in board.tiles.items() if pt.tile.keystone)
    wildlife = next(iter(board.tiles[key_pos].tile.wildlife))
    g.bag.append(g.display_tokens[0])
    g.bag.remove(wildlife)
    g.display_tokens[0] = wildlife
    pos = sorted(board.frontier())[0]
    g.apply_placement(Placement(0, 0, pos, 0, key_pos))
    assert g.boards[0].nature_tokens == 1


def test_solo_display_discard_and_slide():
    g = Game(GameConfig(num_players=1, seed=9))
    before_tiles = list(g.display_tiles)
    before_toks = list(g.display_tokens)
    pos = sorted(g.board.frontier())[0]
    g.apply_placement(Placement(1, 1, pos, 0, None))
    # slot 3 was discarded, slots 0 and 2 slid to 2 and 3
    assert g.display_tiles[2:] == [before_tiles[0], before_tiles[2]]
    assert g.display_tokens[2:] == [before_toks[0], before_toks[2]]
    assert len(g.removed_tokens) == 1
    assert len(g.tile_stack) == 43 - 4 - 2


def test_determinize_hides_future():
    g = Game(GameConfig(num_players=2, seed=11))
    d = g.determinize(random.Random(0))
    assert len(d.tile_stack) == len(g.tile_stack)
    visible = {pt.tile.id for b in g.boards for pt in b.tiles.values()} | {t.id for t in g.display_tiles}
    assert not visible & {t.id for t in d.tile_stack}
    pos = sorted(d.board.frontier())[0]
    d.apply_placement(Placement(0, 0, pos, 0, None))
    assert g.turn == 0 and len(g.boards[0].tiles) == 3


@pytest.mark.parametrize("mode", ["family", "intermediate"])
def test_variants_play(mode):
    bots = [make_bot("greedy", seed=1), make_bot("random", seed=2)]
    res = play_game(bots, GameConfig(num_players=2, seed=1, cards=ScoringCards(mode=mode)))
    assert res.cards == mode


def test_all_cards_full_games_with_bots():
    rng = random.Random(0)
    specs = ["random", "greedy", "heuristic"]
    for i in range(6):
        cards = ScoringCards(cards=tuple(rng.choice(CARD_LETTERS) for _ in range(5)))
        bots = [make_bot(s, seed=i) for s in specs]
        res = play_game(bots, GameConfig(num_players=3, seed=i, cards=cards))
        assert res.game.turns_taken == [20, 20, 20]
        assert all(s.total >= 0 for s in res.scores)


def test_lookahead_bot_runs():
    bots = [make_bot("lookahead:top_k=2,samples=1,depth=1", seed=0), make_bot("greedy", seed=1)]
    res = play_game(bots, GameConfig(num_players=2, seed=0))
    assert res.game.game_over


def test_tile_by_id_lookup():
    assert all(TILE_BY_ID[t.id] is t for t in HABITAT_TILES)


def test_majority_estimator():
    from cascadia_bot.bots.evaluation import MajorityEstimator

    g = Game(GameConfig(num_players=3, seed=2))
    est = MajorityEstimator(g, weight=1.0, ramp=False)
    est.sizes = {h: [4, 5, 3] for h in Habitat}
    est.base = {h: [1, 3, 0] for h in Habitat}  # player 0 is second -> 1 point
    assert est.delta({Habitat.FOREST: 5}) == 1  # tie for first: 2 each
    assert est.delta({Habitat.FOREST: 6}) == 2  # sole first: 3
    assert est.delta({Habitat.FOREST: 4, Habitat.RIVER: 6}) == 2
    ramped = MajorityEstimator(g, weight=1.0, ramp=True)
    assert ramped.factor == pytest.approx(1 / 20)
    off = MajorityEstimator(Game(GameConfig(num_players=2, seed=2, habitat_majority=False)), 1.0)
    assert off.delta({Habitat.FOREST: 50}) == 0


def test_majority_denial():
    from cascadia_bot.bots.evaluation import MajorityEstimator

    g = Game(GameConfig(num_players=3, seed=2))
    est = MajorityEstimator(g, weight=1.0, ramp=False, denial=1.0, denial_target="mean")
    est.sizes = {h: [4, 5, 3] for h in Habitat}
    est.base = {h: [1, 3, 0] for h in Habitat}
    # overtaking: me 1 -> 3 (+2), player 1: 3 -> 1 (-2), player 2 unchanged -> mean -1
    assert est.delta({Habitat.FOREST: 6}) == 2 + 1
    est.leader = 1  # only the leader's loss counts
    assert est.delta({Habitat.FOREST: 6}) == 2 + 2
    # tying the leader: me +1, leader 3 -> 2
    assert est.delta({Habitat.FOREST: 5}) == 1 + 1


def test_bag_counts_match_hidden_bag():
    from cascadia_bot.bots.probability import bag_counts

    bots = [make_bot("greedy", seed=0), make_bot("greedy", seed=1)]
    g = Game(GameConfig(num_players=2, seed=8))
    for _ in range(15):
        assert bag_counts(g) == {w: g.bag.count(w) for w in Wildlife}
        g.apply_placement(bots[g.current_player].choose_placement(g))


def test_availability_and_expected_best():
    from cascadia_bot.bots.probability import expected_best, next_turn_availability

    g = Game(GameConfig(num_players=2, seed=8))
    avail = next_turn_availability(g)
    assert all(0.0 < p < 1.0 for p in avail.values())
    gains = {w: 0 for w in Wildlife}
    gains[Wildlife.BEAR] = 6
    gains[Wildlife.ELK] = 4
    a = {w: 0.0 for w in Wildlife}
    a[Wildlife.BEAR] = 0.5
    a[Wildlife.ELK] = 1.0
    assert expected_best(gains, a) == pytest.approx(0.5 * 6 + 0.5 * 4)


def test_mcts_bot_plays_legal_moves():
    bots = [make_bot("mcts:iterations=12,top_k=3", seed=0), make_bot("heuristic", seed=1)]
    res = play_game(bots, GameConfig(num_players=2, seed=0))
    assert res.game.turns_taken == [20, 20]
    solo = play_game([make_bot("mcts:time_limit=0.01,top_k=2", seed=0)], GameConfig(num_players=1, seed=0))
    assert solo.game.game_over


def test_fast_evaluation_matches_full_recompute():
    """TokenGainCache / CorridorProbe shortcuts must equal brute-force scoring."""
    from cascadia_bot.bots.evaluation import (
        MajorityEstimator,
        TokenGainCache,
        best_habitat_rotations,
        habitat_gain,
    )
    from cascadia_bot.scoring import wildlife_total

    rng = random.Random(3)
    for i in range(6):
        cards = ScoringCards(cards=tuple(rng.choice(CARD_LETTERS) for _ in range(5)))
        g = Game(GameConfig(num_players=3, seed=i, cards=cards))
        bots = [make_bot("random", seed=i + k) for k in range(3)]
        while not g.game_over:
            b = g.board
            gains = TokenGainCache(b, cards)
            base = wildlife_total(b.tokens, cards)
            for w in Wildlife:
                for pos in [p for p in b.tiles if p not in b.tokens][:6]:
                    t = dict(b.tokens)
                    t[pos] = w
                    assert gains.gain(w, pos) == wildlife_total(t, cards) - base
            corridors = b.largest_corridors()
            maj = MajorityEstimator(g, 1.0, True)
            for pos in sorted(b.frontier())[:5]:
                for tile in rng.sample(HABITAT_TILES, 3):
                    assert b.probe().sizes_after(pos, tile, 1) == b.corridor_sizes_after(pos, tile, 1)
                    vals = {r: habitat_gain(b, corridors, pos, tile, r, maj) for r in tile.rotations()}
                    best = max(vals.values())
                    got, rots = best_habitat_rotations(b.probe(), pos, tile, maj)
                    assert got == pytest.approx(best)
                    assert sorted(rots) == sorted(r for r, v in vals.items() if abs(v - best) < 1e-9)
            g.apply_placement(bots[g.current_player].choose_placement(g))


@pytest.mark.parametrize(
    "spec",
    [
        "mce:playouts=6,top_k=3",
        "mce:playouts=6,top_k=3,allocation=ucb",
        "mce:time_limit=0.01,top_k=2,allocation=uniform,opponents=random,reward=own",
        "mce:playouts=4,top_k=2,horizon=1",
    ],
)
def test_mce_bot_variants(spec):
    res = play_game([make_bot(spec, seed=0), make_bot("greedy", seed=1)], GameConfig(num_players=2, seed=0))
    assert res.game.turns_taken == [20, 20]


def test_train_value_and_learned_bots(tmp_path):
    from cascadia_bot.bots.features import LinearValue, game_features
    from cascadia_bot.train_value import main as train_main

    out = tmp_path / "v.json"
    assert train_main(["--games", "12", "--out", str(out), "--holdout", "0.25"]) == 0
    model = LinearValue.load(out)
    assert "bias" in model.weights and model.meta["players"] == 2
    g = Game(GameConfig(num_players=2, seed=1))
    assert isinstance(model.predict(game_features(g, 0)), float)
    bots = [make_bot(f"value:model={out}", seed=0), make_bot(f"mce:horizon=1,playouts=4,top_k=2,evaluator=learned,model={out}", seed=1)]
    res = play_game(bots, GameConfig(num_players=2, seed=2))
    assert res.game.turns_taken == [20, 20]


def test_selfplay_stats(tmp_path, capsys):
    from cascadia_bot.selfplay_stats import main as stats_main

    out = tmp_path / "g.jsonl"
    assert stats_main(["greedy", "--games", "3", "--out", str(out)]) == 0
    assert len(out.read_text().splitlines()) == 3
    assert "winner minus loser" in capsys.readouterr().out


@pytest.mark.parametrize("replan", ["ev", "always", "never"])
def test_plan_bot(replan):
    bot = make_bot(f"plan:replan={replan},samples=2,check_every=5", seed=0)
    res = play_game([bot, make_bot("greedy", seed=1)], GameConfig(num_players=2, seed=3))
    assert res.game.turns_taken == [20, 20]
    assert bot.plan_log and bot.plan_log[0][0] == 0
    if replan == "never":
        assert len(bot.plan_log) == 1


def test_mce_win_reward():
    from cascadia_bot.bots.mce import MCEBot

    bot = make_bot("mce:reward=win,playouts=4,top_k=2,horizon=1", seed=0)
    res = play_game([bot, make_bot("greedy", seed=1)], GameConfig(num_players=2, seed=4))
    assert res.game.turns_taken == [20, 20]
    assert isinstance(bot, MCEBot)
    g = res.game  # game over: exact 1 / 0.5 / 0
    p = bot._win_probability(g, 0)
    totals = [s.total for s in g.scores()]
    assert p == (1.0 if totals[0] > totals[1] else 0.5 if totals[0] == totals[1] else 0.0)
