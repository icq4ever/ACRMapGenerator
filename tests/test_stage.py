import pytest

from acr_map_generator.core.stage import TEMPLATE, StageError, parse_stage

VALID = """
schema = "acr-map-generator/stage"
version = 1

[stage]
title = "Test stage"
display_name = "A – B"
country = "FR"

[route]
roads = ["D 1"]
[[route.waypoints]]
lat = 42.0
lon = 9.0
[[route.waypoints]]
lat = 42.01
lon = 9.01

[export.stage_ir]
id = "test_stage"
"""


def test_valid_minimal_stage():
    cfg = parse_stage(VALID)
    assert cfg.stage.surface == "asphalt"
    assert cfg.terrain.crs == "EPSG:2154"
    assert [v.name for v in cfg.export.stage_ir.variants] == ["full"]
    assert cfg.export.stage_ir.variant_id(cfg.export.stage_ir.variants[0]) == "test_stage"


def test_template_rejected_until_filled():
    with pytest.raises(StageError, match="TODO"):
        parse_stage(TEMPLATE.read_text(encoding="utf-8"))


def test_unknown_key_rejected():
    with pytest.raises(StageError, match="stage.colour"):
        parse_stage(VALID.replace('country = "FR"', 'country = "FR"\ncolour = "red"'))


def test_bad_country_rejected():
    with pytest.raises(StageError, match="stage.country"):
        parse_stage(VALID.replace('"FR"', '"France"'))


def test_one_waypoint_rejected():
    text = VALID.replace("[[route.waypoints]]\nlat = 42.01\nlon = 9.01\n", "")
    with pytest.raises(StageError, match="route.waypoints"):
        parse_stage(text)


@pytest.mark.parametrize(
    "segments, ok",
    [
        ([(1.0, 2.0), (2.0, 3.0)], True),  # touching
        ([(1.0, 2.5), (2.0, 3.0)], False),  # overlapping
    ],
)
def test_surface_segments_overlap(segments, ok):
    extra = "".join(f'\n[[route.surfaces]]\nfrom_km = {a}\nto_km = {b}\nsurface = "gravel"\n' for a, b in segments)
    text = VALID.replace("[export.stage_ir]", extra + "\n[export.stage_ir]")
    if ok:
        assert len(parse_stage(text).route.surfaces) == 2
    else:
        with pytest.raises(StageError, match="overlap"):
            parse_stage(text)


def test_surface_runs():
    from acr_map_generator.core.area import Area
    from acr_map_generator.core.stage import Stage

    text = VALID.replace(
        "[export.stage_ir]", '[[route.surfaces]]\nfrom_km = 1.0\nto_km = 2.0\nsurface = "gravel"\n\n[export.stage_ir]'
    )
    cfg = parse_stage(text)
    area = Area("t", "t", 9.0, 42.0, 9.01, 42.01, "EPSG:2154", 1.0)
    st = Stage("t", cfg, area, TEMPLATE)
    runs = st.surface_runs(0.0, 3000.0)
    assert [(r["from_m"], r["to_m"], r["surface"]) for r in runs] == [
        (0.0, 1000.0, "asphalt"),
        (1000.0, 2000.0, "gravel"),
        (2000.0, 3000.0, "asphalt"),
    ]
