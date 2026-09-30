"""Regenerate the Opus reference from the actual vendored engine contract."""
import ast
import inspect
import json
from pathlib import Path
from engine_path import ensure_on_path

ensure_on_path()
import elementary
import core.figure_scene as figure_scene
from core.figure_scene import StyleProfile, compile_figure_spec
from graph_scene import CONTRACT, FIELDS

# graph-1 설명(CONTRACT)은 사람이 쓴 글이고 받는 칸의 정본은 FIELDS 다. 칸을 늘리고 설명을 빠뜨리면
# 모델은 「엔진에 그런 기능이 없다」로 읽는다(v2 의 `curvature` 가 그랬다 — 아래 `_v2_fields`).
# 그래서 설명이 모자라면 카탈로그를 만들지 않는다(2026-09-21 axisBreaks 를 넣으며).
_undescribed = sorted(set(FIELDS) - set(CONTRACT['fields']))
if _undescribed:
    raise SystemExit(f'build_catalog: graph-1 CONTRACT 에 설명이 없는 칸: {_undescribed}')


def _v2_fields() -> dict[str, list[str]]:
    """**엔진이 실제로 받는 v2 필드** — 설명 글이 아니라 강제하는 코드에서 읽는다.

    🔴 종전에는 v2 계약으로 `compile_figure_spec` 의 docstring 만 실었다. docstring 은
       사람이 쓴 요약이라 `dimensions.curvature`·`labels.dx/dy/position`·`arcs.dash` 가
       **빠져 있었고**, 모델은 그것을 「엔진에 그런 기능이 없다」로 읽고 재작도를
       거절했다(2026-09-14 — 47초를 쓰고 「치수 곡선의 휨과 라벨 위치를 조절하는 기능이
       없어」). 엔진은 그 키들을 다 받는다. **설명서에만 없었다.**

    그래서 `_strict_keys(obj, allowed, path)` 호출을 소스 AST 에서 직접 읽는다.
    허용 목록을 여기 손으로 한 벌 더 적으면, 엔진이 키를 늘릴 때 이 목록만 조용히 낡는다.

    ⚠️ **못 읽으면 죽는다.** 빈 목록을 내고 초록으로 끝나면 모델에게 「받는 필드 0개」를
       알리는 거짓 계약이 된다 — 그건 docstring 이 빠뜨린 것보다 나쁘다.
    """
    tree = ast.parse(inspect.getsource(figure_scene))
    parents: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node

    def ancestors(node: ast.AST):
        while node in parents:
            node = parents[node]
            yield node

    def fail(call: ast.Call, why: str) -> SystemExit:
        return SystemExit(f"build_catalog: _strict_keys at figure_scene.py:{call.lineno}: {why}")

    def allowed_keys(arg: ast.AST, call: ast.Call) -> set[str]:
        if isinstance(arg, ast.Set):
            return {elt.value for elt in arg.elts
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str)}
        if isinstance(arg, ast.Name):
            function = next((n for n in ancestors(call) if isinstance(n, ast.FunctionDef)), None)
            for stmt in ast.walk(function) if function else ():
                if not (isinstance(stmt, ast.Assign) and any(
                        isinstance(t, ast.Name) and t.id == arg.id for t in stmt.targets)):
                    continue
                if isinstance(stmt.value, ast.Set):
                    return allowed_keys(stmt.value, call)
                if function.name == "_style_from_spec":
                    # StyleProfile 필드에서 계산된다 — 소스 글자가 아니라 엔진의 실제 값을 쓴다.
                    return {f for f in StyleProfile.__dataclass_fields__ if f != "name"}
        raise fail(call, "cannot read the allowed-key set")

    def point_kind(call: ast.Call) -> str | None:
        """점 허용 목록은 `if kind == "raw":` 같은 갈래 안에 있다 — 그 갈래 이름을 붙인다."""
        for node in ancestors(call):
            test = getattr(node, "test", None) if isinstance(node, ast.If) else None
            if (isinstance(test, ast.Compare) and isinstance(test.left, ast.Name)
                    and test.left.id == "kind" and len(test.ops) == 1
                    and isinstance(test.ops[0], ast.Eq)
                    and isinstance(test.comparators[0], ast.Constant)):
                return str(test.comparators[0].value)
        return None

    def section(arg: ast.AST, call: ast.Call) -> str:
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            name = arg.value
        elif isinstance(arg, ast.JoinedStr):
            text = "".join(v.value if isinstance(v, ast.Constant) else "{}" for v in arg.values)
            # "segments.{}" → "segments" · "{}.arc" 는 영역 경계 조각 안의 호다.
            name = "regions.boundary.arc" if text == "{}.arc" else text.split(".{}")[0]
        else:
            raise fail(call, "cannot read the path argument")
        if name == "points":
            # 세 갈래를 합치면 «원 위의 점에 x 를 줘도 된다»로 읽힌다 — 따로 적는다.
            kind = point_kind(call)
            if kind is None:
                raise fail(call, "point kind branch not found")
            name = f"points:{kind}"
        return name

    calls = [node for node in ast.walk(tree)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
             and node.func.id == "_strict_keys"]
    fields: dict[str, list[str]] = {}
    for call in calls:
        if len(call.args) != 3:
            raise fail(call, f"expected 3 arguments, got {len(call.args)}")
        key = section(call.args[2], call)
        keys = sorted(allowed_keys(call.args[1], call))
        if not keys:
            raise fail(call, "allowed-key set is empty")
        if key in fields:
            raise fail(call, f"section {key!r} read twice — naming would merge two objects")
        fields[key] = keys
    if not calls:
        raise SystemExit("build_catalog: no _strict_keys calls found — the engine validator moved")
    return dict(sorted(fields.items()))


catalog = {
    'graph-1': CONTRACT,
    'curveGraph_contract': 'curves quadratic uses {type:"quadratic",a,p,q,label?} for y=a(x-p)^2+q, NEVER b/c; inverse uses {type:"inverse",k,label?}. lines uses slope/yIntercept/label and cannot be horizontal; marks is [[x,y],...] integers on graph. For annotated curves, horizontal segments, inscribed shapes or custom labels use graph-1 instead.',
    'v2': inspect.getdoc(compile_figure_spec),
    'v2_fields': _v2_fields(),
    'v2_fields_note': (
        'v2_fields lists EVERY field the v2 engine accepts for each object, read from the '
        'validator itself. A field not listed is rejected. A field listed IS supported even '
        'when the v2 prose above omits it. dimensions.curvature bends the dashed measurement '
        'bow. labels.dx/dy offset a label from its point and labels.position picks its side '
        '("auto" by default, or a compass side such as "NW"). arcs use "dash", never "dashed"; '
        'segments accept either. points:raw is {x,y} or [x,y]; points:on_circle and '
        'points:intersection are constructed from other objects. Leave style unset unless '
        'the original clearly differs.'
    ),
    'v2_example': {
        'version': 2,
        'points': {'A': [50, 30], 'B': [50, 210], 'C': [290, 210], 'value3': [30, 120]},
        'segments': {'AB': ['A', 'B'], 'BC': ['B', 'C'], 'CA': ['C', 'A']},
        'angles': {'rightB': {'vertex': 'B', 'points': ['A', 'C'], 'right': True}},
        'labels': {'A': 'A', 'B': 'B', 'C': 'C', 'value3': {'text': '3', 'dx': 0, 'dy': 0}},
    },
    'elementary': {
        k: {'required': sorted(elementary.KIND_FIELDS[k]),
            'optional': sorted(elementary.OPTIONAL.get(k, set())),
            'help': inspect.getdoc(fn) or ''}
        for k, fn in elementary._RENDER.items()
    },
}
Path(__file__).with_name('engine-catalog.json').write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding='utf-8')
print(f'Engine catalog: {len(catalog["elementary"])} elementary kinds + FigureSpec v2 '
      f'({len(catalog["v2_fields"])} objects read from the validator)')
