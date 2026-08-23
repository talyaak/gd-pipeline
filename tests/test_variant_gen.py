from pathlib import Path

from pipeline.nodes.variant_gen import _generate_variants

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_transform_matching_nothing_is_flagged_no_op():
    # known_good_game.html contains no "baseSpeed = 200" etc., so the difficulty
    # transform's literal string replacements match nothing.
    base_html = _read("known_good_game.html")
    variants = _generate_variants(base_html, {}, [{"type": "difficulty", "name": "easy"}])
    assert variants[0]["no_op"] is True


def test_transform_that_matches_is_not_flagged_no_op():
    # known_good_game.html does contain 0x00ff00, which the palette transform rewrites.
    base_html = _read("known_good_game.html")
    variants = _generate_variants(base_html, {}, [{"type": "palette", "name": "neon"}])
    assert variants[0]["no_op"] is False
