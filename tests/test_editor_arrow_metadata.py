"""편집기와 공유하는 화살표 메타데이터. 모양·라벨·보안 경계는 유지한다."""
import sys
from pathlib import Path
import xml.etree.ElementTree as ET
import importlib
import io
import json

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "figure"))
from elementary import _arrow_down, _arrow_up, _arrow_right
from figure_assets import _dim_arrow
from graph_scene import render_graph
from core.figure_quality import sanitize_svg, SvgSecurityError

def root(body):
    return ET.fromstring(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 100">{body}</svg>')

@pytest.mark.parametrize("body", [_arrow_down(20, 10, 80), _arrow_up(20, 80, 10), _arrow_right(10, 180, 30)])
def test_connectors_share_one_group(body):
    group = list(root(body))[0]
    assert group.attrib["data-arrow"] == "end"
    assert [node.tag.split("}")[-1] for node in group] == ["line", "polygon"]
    clean = sanitize_svg(ET.tostring(root(body), encoding="unicode"))
    assert 'data-arrow="end"' in clean

def test_dimension_keeps_label_separate():
    svg = root(_dim_arrow(10, 60, 180, 30, "10"))
    group, label = list(svg)
    assert group.attrib["data-arrow"] == "both"
    assert len(group) == 3
    assert label.text == "10"

def test_graph_vectors_and_metadata_security():
    svg = render_graph({"version": "graph-1", "xRange": [0, 4], "yRange": [0, 4], "axes": False, "segments": [{"from": [1, 1], "to": [3, 3], "arrow": True}]})
    clean = sanitize_svg(svg)
    groups = [node for node in ET.fromstring(clean).iter() if node.attrib.get("data-arrow") == "end"]
    assert len(groups) == 1 and len(groups[0]) == 2
    with pytest.raises(SvgSecurityError):
        sanitize_svg(svg.replace('data-arrow="end"', 'data-arrow="javascript:alert(1)"'))

@pytest.mark.parametrize("module_name,function,args,baseline", [
    ("elementary", "_arrow_down", (20, 10, 80), "down"),
    ("elementary", "_arrow_up", (20, 80, 10), "up"),
    ("elementary", "_arrow_right", (10, 180, 30), "right"),
    ("figure_assets", "_dim_arrow", (10, 60, 180, 30, "10"), "dimension"),
    *[("graph_scene", "render_graph", ({"version": "graph-1", "xRange": [0, 4], "yRange": [0, 4], "axes": False, "segments": [{"from": [1, 1], "to": end, "arrow": True}]},), name) for end, name in [([3, 1], "horizontal"), ([1, 3], "vertical"), ([3, 3], "diagonal")]],
])
def test_arrow_pixels_match_previous_revision(module_name, function, args, baseline):
    from core.figure_svg import svg_to_png_bytes
    from PIL import Image, ImageChops
    module = importlib.import_module(module_name)
    # 19a4bde의 실제 렌더 출력을 고정했다. git 없이도 이전 모양과 비교한다.
    before = json.loads((ROOT / "tests" / "fixtures" / "editor_arrow_baselines.json").read_text(encoding="utf-8"))[baseline]
    after = getattr(module, function)(*args)
    if function != "render_graph":
        after = ET.tostring(root(after), encoding="unicode")
    images = [Image.open(io.BytesIO(svg_to_png_bytes(svg, 260))).convert("RGBA") for svg in [before, after]]
    assert ImageChops.difference(*images).getbbox() is None
