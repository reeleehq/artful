"""Round-trips of every optional panel field through the Markdown and HTML exports."""

from __future__ import annotations

from lacing import MemoryStore, TimeInterval

from artful import (
    PanelBody,
    PanelImage,
    Storyboard,
    from_markdown,
    load_storyboard,
    save_storyboard,
    to_html,
    to_markdown,
)
from artful.store import StoryboardMetaBody


def _full_panel():
    return PanelBody(
        panel_id="p1",
        shot_id="s01",
        images=(
            PanelImage(path="a.png", caption="local"),
            PanelImage(url="https://x/b.png", caption="remote"),
            PanelImage(artifact_id="ab" * 32, caption="stored"),
        ),
        caption="Thor at the piano",
        framing="medium",
        camera="static",
        shot_size="MS",
        angle="LOW",
        movement="PAN",
        transition_in="fade",
        notes="keep it dim",
    )


def _sb():
    return Storyboard(
        title="T", asset_id="asset-1", panels=(_full_panel(),), style="noir", aspect="9:16"
    )


def test_markdown_round_trip_keeps_every_field():
    sb = _sb()
    iv = {"p1": TimeInterval.from_seconds(1, 3)}
    back, back_iv = from_markdown(to_markdown(sb, iv))
    assert (back.title, back.asset_id, back.style, back.aspect) == (
        "T",
        "asset-1",
        "noir",
        "9:16",
    )
    p = back.panels[0]
    assert p.shot_id == "s01"
    assert (p.framing, p.camera, p.shot_size, p.angle, p.movement) == (
        "medium",
        "static",
        "MS",
        "LOW",
        "PAN",
    )
    assert p.transition_in == "fade" and p.notes == "keep it dim"
    assert p.caption == "Thor at the piano"
    kinds = [(i.path, i.url, i.artifact_id) for i in p.images]
    assert kinds == [
        ("a.png", None, None),
        (None, "https://x/b.png", None),
        (None, None, "ab" * 32),
    ]
    assert back_iv["p1"].start == iv["p1"].start


def test_markdown_unknown_taxonomy_values_are_dropped():
    text = to_markdown(_sb()).replace("shot_size: MS", "shot_size: NOPE").replace(
        "angle: LOW", "angle: NOPE"
    ).replace("movement: PAN", "movement: NOPE")
    p = from_markdown(text)[0].panels[0]
    assert p.shot_size is None and p.angle is None and p.movement is None


def test_html_contains_all_panel_details():
    html = to_html(_sb(), {"p1": TimeInterval.from_seconds(1, 3)})
    for needle in (
        "panel p1",
        "[1.00..3.00]s",
        "shot <code>s01</code>",
        "medium",
        "static",
        "MS",
        "LOW",
        "PAN",
        "transition: fade",
        "Thor at the piano",
        "notes: keep it dim",
        'src="a.png"',
        'src="https://x/b.png"',
    ):
        assert needle in html
    assert html.rstrip().endswith("</html>")


def test_html_panel_without_image_and_locked_cut_hidden():
    sb = Storyboard(
        asset_id="a",
        panels=(PanelBody(panel_id="p", movement="LOCKED", transition_in="cut"),),
    )
    html = to_html(sb)
    assert "(no image)" in html and "LOCKED" not in html and "transition:" not in html


def test_html_escapes_text():
    sb = Storyboard(
        asset_id="a", panels=(PanelBody(panel_id="p", caption="<script>&"),)
    )
    html = to_html(sb)
    assert "<script>" not in html and "&lt;script&gt;&amp;" in html


def test_storyboard_panel_lookup():
    sb = _sb()
    assert sb.panel("p1").shot_id == "s01"
    assert sb.panel("missing") is None


def test_stored_meta_is_ignored_on_unrelated_asset_and_round_trips():
    store = MemoryStore()
    save_storyboard(_sb(), store, panel_intervals={"p1": TimeInterval.from_seconds(0, 1)})
    got = load_storyboard(store, asset_id="asset-1")
    assert (got.title, got.style, got.aspect) == ("T", "noir", "9:16")
    other = load_storyboard(store, asset_id="nothing")
    assert other.panels == ()


def test_meta_body_is_frozen_and_forbids_extras():
    import pytest

    m = StoryboardMetaBody(title="x")
    with pytest.raises(Exception):
        m.title = "y"
    with pytest.raises(Exception):
        StoryboardMetaBody(bogus=1)


def _foreign_annotation(tier, body_schema_uri="annot://schema/other/v1"):
    import uuid

    from lacing import Annotation, NodeRef
    from artful.store import make_prov

    return Annotation(
        id=uuid.uuid4(),
        tier=tier,
        reference=NodeRef(scene_path="a/b", interval=TimeInterval.from_seconds(0, 1)),
        body={},
        body_schema_uri=body_schema_uri,
        provenance=make_prov("agent:t", "user:t"),
    )


def test_load_skips_annotations_that_are_not_media_refs_or_not_storyboard_bodies():
    from artful.store import _DEFAULT_TIER

    store = MemoryStore()
    store.add(_foreign_annotation(_DEFAULT_TIER))
    save_storyboard(_sb(), store, panel_intervals={"p1": TimeInterval.from_seconds(0, 1)})
    # a same-tier, same-asset annotation with some other body schema is ignored too
    from lacing import Annotation, MediaRef
    import uuid
    from artful.store import make_prov

    store.add(
        Annotation(
            id=uuid.uuid4(),
            tier=_DEFAULT_TIER,
            reference=MediaRef(asset_id="asset-1", interval=TimeInterval.from_seconds(0, 1)),
            body={},
            body_schema_uri="annot://schema/other/v1",
            provenance=make_prov("agent:t", "user:t"),
        )
    )
    got = load_storyboard(store, asset_id="asset-1")
    assert [p.panel_id for p in got.panels] == ["p1"]


def test_shot_schedule_lookup_skips_non_media_refs():
    from artful.shot_schedule import SHOT_SCHEDULE_BODY_SCHEMA_URI, SHOT_SCHEDULE_TIER, load_shot_schedule

    store = MemoryStore()
    store.add(_foreign_annotation(SHOT_SCHEDULE_TIER, SHOT_SCHEDULE_BODY_SCHEMA_URI))
    assert load_shot_schedule(store, asset_id="a") is None
