"""Tests for load_splits: backward-compat 'seeded' mode + new 'stratified' mode."""

from collections import Counter

from fdpo.data.loaders import Example, _stratified_take, load_splits


def _slice_dist(examples):
    return dict(Counter(e.meta.get("slice", "?") for e in examples))


def _label_dist(examples):
    return dict(Counter(e.gold for e in examples))


def _dummy_pool(slices_and_labels):
    """slices_and_labels: {slice_name: (label, count)} -> list[Example]."""
    out = []
    i = 0
    for name, (label, count) in slices_and_labels.items():
        for _ in range(count):
            out.append(Example(id=f"ex_{i}", question=f"q{i}",
                               gold=label, reference=label,
                               meta={"slice": name}))
            i += 1
    return out


def test_stratified_take_preserves_proportions_when_possible():
    import random
    pool = _dummy_pool({"A": ("Yes", 30), "B": ("No", 20), "C": ("No", 10)})
    selected, remainder = _stratified_take(pool, 30, random.Random(0))
    dist = _slice_dist(selected)
    assert sum(dist.values()) == 30
    # 30/60 = 50% -> ~15 from A (50), ~10 from B, ~5 from C
    assert dist["A"] == 15
    assert dist["B"] == 10
    assert dist["C"] == 5
    assert len(remainder) == 30


def test_stratified_take_deterministic_under_same_rng():
    import random
    pool = _dummy_pool({"A": ("Yes", 12), "B": ("No", 8)})
    s1, _ = _stratified_take(pool, 10, random.Random(42))
    s2, _ = _stratified_take(pool, 10, random.Random(42))
    assert [e.id for e in s1] == [e.id for e in s2]


def test_stratified_take_full_pool_returns_all():
    import random
    pool = _dummy_pool({"A": ("Yes", 5), "B": ("No", 5)})
    selected, remainder = _stratified_take(pool, 10, random.Random(0))
    assert len(selected) == 10
    assert remainder == []


def test_legalbench_stratified_test_is_fixed_across_seeds():
    _, e0 = load_splits("legalbench_hearsay", 20, 59, seed=0, split_mode="stratified")
    _, e5 = load_splits("legalbench_hearsay", 20, 59, seed=5, split_mode="stratified")
    _, e42 = load_splits("legalbench_hearsay", 20, 59, seed=42, split_mode="stratified")
    assert sorted(e.id for e in e0) == sorted(e.id for e in e5) == sorted(e.id for e in e42)


def test_legalbench_stratified_train_varies_with_seed():
    t0, _ = load_splits("legalbench_hearsay", 20, 59, seed=0, split_mode="stratified")
    t5, _ = load_splits("legalbench_hearsay", 20, 59, seed=5, split_mode="stratified")
    # Different individual examples chosen across seeds...
    assert sorted(e.id for e in t0) != sorted(e.id for e in t5)
    # ...but same slice proportions preserved.
    assert _slice_dist(t0) == _slice_dist(t5)


def test_legalbench_stratified_covers_every_slice():
    train, test = load_splits("legalbench_hearsay", 40, 59, seed=0, split_mode="stratified")
    expected = {"Non-assertive conduct", "Non-verbal hearsay",
                "Not introduced to prove truth", "Standard hearsay",
                "Statement made in-court"}
    assert set(_slice_dist(train)) == expected
    assert set(_slice_dist(test)) == expected


def test_legalbench_stratified_label_balance_matches_full_dataset():
    """Full dataset is ~57%/43% No/Yes. Both splits should stay near that ratio."""
    train, test = load_splits("legalbench_hearsay", 40, 59, seed=0, split_mode="stratified")
    tr, te = _label_dist(train), _label_dist(test)
    tr_yes_frac = tr.get("Yes", 0) / (tr.get("Yes", 0) + tr.get("No", 0))
    te_yes_frac = te.get("Yes", 0) / (te.get("Yes", 0) + te.get("No", 0))
    assert 0.35 <= tr_yes_frac <= 0.55
    assert 0.35 <= te_yes_frac <= 0.55


def test_seeded_mode_still_varies_test_across_seeds():
    """Backward-compat: the original 'seeded' mode's test set DOES vary per seed."""
    _, e0 = load_splits("legalbench_hearsay", 40, 59, seed=0, split_mode="seeded")
    _, e1 = load_splits("legalbench_hearsay", 40, 59, seed=1, split_mode="seeded")
    assert sorted(e.id for e in e0) != sorted(e.id for e in e1)


def test_stratified_falls_back_to_gold_when_no_slice_meta():
    """Datasets without slice metadata (GSM8K, ARC) should still stratify by gold."""
    import random
    # Simulate: no slice, mixed golds
    pool = [
        Example(id=f"g_{i}", question="q", gold="A" if i < 20 else "B",
                reference="ref", meta={})
        for i in range(30)
    ]
    selected, _ = _stratified_take(pool, 10, random.Random(0))
    dist = _label_dist(selected)
    # 20 A / 10 B -> take 10 total -> ~7 A / ~3 B
    assert dist["A"] + dist["B"] == 10
    assert dist["A"] >= 5   # at least half from majority class
    assert dist["B"] >= 2   # at least a couple from minority class


def test_unknown_split_mode_raises():
    import pytest
    with pytest.raises(ValueError, match="unknown split_mode"):
        load_splits("legalbench_hearsay", 10, 20, 0, split_mode="what")
