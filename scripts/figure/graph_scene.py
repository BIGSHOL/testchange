"""Annotated textbook graphs: deterministic curves plus finite segments and labels.

The upstream curveGraph accepts only whole lines and integer marks. This adapter
adds the finite segments/polygons used by inscribed-shape exam questions.

Ported from Mathgen scripts/figure/graph_scene.py (2026-09-14). Rendering uses
the existing identical core; local additions reject unknown/malformed fields
instead of silently drawing a partial spec.
"""
import math
import re

HANGUL = re.compile('[%s-%s%s-%s%s-%s]' % tuple(map(chr, (0x1100, 0x11FF, 0x3130, 0x318F, 0xAC00, 0xD7AF))))

CONTRACT = {
    'version': 'graph-1',
    'coordinates': 'Mathematical x right, y UP. Explicit xRange/yRange, each [min,max]. No eval/code.',
    'fields': {
        'xRange': 'required [min,max]', 'yRange': 'required [min,max]',
        'width': 'optional 240..640 default 520', 'height': 'optional 200..640 default 460',
        'axes': 'optional boolean default true; arrows + x,y labels only, NO automatic ticks or O label',
        'curves': 'list of {coefficients:[a,b,c,...],domain:[xmin,xmax]} for polynomial a*x^n+b*x^(n-1)+...; OR {type:"inverse",k:number,domain:[xmin,xmax]}; optional dashed:boolean',
        'segments': 'list of {from:[x,y],to:[x,y],dashed?:boolean,arrow?:boolean}; finite visible segments only',
        'polygons': 'list of {points:[[x,y],...],fill?:"#eeeeee",dashed?:boolean}; optional shading',
        'circles': 'list of {center:[x,y],radius:number,dashed?:boolean}; a geometric circle in DATA units (stretches to an ellipse when x/y scales differ) — never use it for printed dots; use points',
        'points': 'list of {at:[x,y],radius?:pixels 1..6 default 3,open?:boolean}; small printed dots at graph points (vertices, endpoints, intersections) in fixed screen pixels, filled black or open (white inside)',
        'labels': 'list of {at:[x,y],text:string,dx?:pixels,dy?:pixels,size?:pixels,anchor?:"start"|"middle"|"end"}; only printed labels; math can use $...$ LaTeX and is typeset as vector glyphs. Korean text cannot be typeset: write a label containing Korean as plain text without $ (e.g. "x(초)")',
        'axisBreaks': 'list of {at:[x,y],axis?:"x"|"y",size?:pixels 10..24 default 14}; the printed wavy ∿ axis-break mark (물결선) ON an axis line where the axis skips values (e.g. between O and the first tick of a scatter plot whose data start far from 0). at = centre of the mark placed ON that axis line (same y as the x-axis line, same x as the y-axis line); axis = which axis it cuts, default "x"; size = its length along the axis in fixed screen pixels. The engine draws a smooth wave and blanks the axis line under it — never imitate it with short segments or curves',
    },
    'example': {'version':'graph-1','xRange':[-4,4],'yRange':[-2,11],
        'curves':[{'coefficients':[-1,0,9],'domain':[-3.4,3.4]}],
        'segments':[{'from':[-2,5],'to':[2,5]}],
        'labels':[{'at':[0,9],'text':'9','dx':-16,'dy':-3}, {'at':[-3,0],'text':'−3','dy':22},
            {'at':[3,0],'text':'3','dy':22},{'at':[0,0],'text':'O','dx':-16,'dy':22},
            {'at':[1.5,9],'text':'y = 9 − x²','dx':22,'dy':-8}]},
}

# 엔진이 받는 칸 — **정본**. 모델에게 가는 설명(CONTRACT['fields'])은 사람이 쓴 글이라 따로 논다.
# build_catalog.py 가 둘을 견줘, 여기 있는데 설명에 없는 칸이 있으면 카탈로그를 안 만든다(설명서에만 없는 기능).
FIELDS = {
    'curves': {'coefficients', 'domain', 'type', 'k', 'dashed'},
    'segments': {'from', 'to', 'dashed', 'arrow'},
    'polygons': {'points', 'fill', 'dashed'},
    'circles': {'center', 'radius', 'dashed'},
    'points': {'at', 'radius', 'open'},
    'labels': {'at', 'text', 'dx', 'dy', 'size', 'anchor'},
    'axisBreaks': {'at', 'axis', 'size'},
}

# 축 생략 물결(∿) — 원장님 2026-09-21 «물결 기호는 넣어». 산점도처럼 자료가 0 에서 멀리 시작하면 교과서는
# 원점과 첫 눈금 사이 축에 물결을 넣는다. 종전에는 칸이 없어 짧은 선분 둘로 「∧」 를 흉내 냈다.
# 모양은 모두 **물결 길이(size, 화면 픽셀)에 비례**한다 — 그래프 눈금과 무관한 표식이라 `points` 반지름처럼 픽셀이다.
BREAK_SIZE = 14    # 기본 길이(픽셀) — 원장님 산점도(440×400)에서 12·14·16 을 견줘 물결 높이(8.4)가 눈금 숫자 높이와 맞는 14
BREAK_AMP = 0.3    # 마루·골 높이 / 길이
BREAK_EASE = 0.5   # 끝과 가운데의 조절점 거리 / 반길이 — 축에서 평평하게 떠나 매끄럽게 이어진다
BREAK_STUB = 0.25  # 양 끝 곧은 꼬리 / 길이 — 흰 채움의 닫는 줄을 축 띠 밑으로 민다(아래 주석)
BREAK_MIN = 10     # 이보다 작으면 마루가 낮아 닫는 줄이 1.7 축 띠를 못 덮는다 — 크기 6 은 0.43px 틈(계산).
                   # 10~24 에서 틈 0.004px 이하. 10 보다 작은 물결은 획 굵기에 묻혀 ∿ 로 읽히지도 않는다


def _cubic_head(p0, p1, p2, p3, t):
    """삼차 베지에를 t 에서 잘라 **앞 조각**의 네 점(드 카스텔조)."""
    def lerp(a, b):
        return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
    a, b = lerp(p0, p1), lerp(p1, p2)
    d = lerp(a, b)
    return p0, a, d, lerp(d, lerp(b, lerp(p2, p3)))


def axis_break_path(cx, cy, axis, size, width):
    """축 생략 물결 — **흰 채움 + 검은 획의 `<path>` 한 요소**. (cx, cy) 는 물결 가운데(화면 좌표).

    물결은 축에서 평평하게 떠나 한쪽으로 마루, 가운데서 축을 건너 반대쪽으로 골, 다시 축으로 평평하게 돌아온다(∿).
    삼차 베지에 둘로 긋는다 — 이음매마다 접선이 이어져 꺾인 데가 없다.

    그 자리의 축 선은 **같은 요소의 흰 채움**이 가린다. 흰 바탕을 따로 깔면 편집기가 보이지 않는 요소를 하나 더
    센다(v2 바탕 rect 가 «사각형 1번»이던 2026-09-19 함정) — 물결만 지우면 축에 까닭 모를 틈이 남는다.
    채움은 획을 긋지 않는 **암묵의 닫는 줄**로 영역을 만든다(열린 하위 경로는 끝→시작으로 닫혀 칠해진다):
    - 앞 하위 경로: 왼쪽 꼬리 → 마루 → 가운데 → 골 바닥. 닫는 줄(골 바닥 → 꼬리 끝)이 축 띠 **밑**을 지나
      마루와 함께 왼쪽 반의 축 띠를 감싼다. 꼬리가 짧으면 닫는 줄이 물결 끝에서 띠를 스쳐 틈이 남는다.
    - 뒤 하위 경로: 그것을 가운데 기준 180° 돌린 것(오른쪽 반). 돈 것이라 감는 방향이 같아 겹쳐도 비지 않는다.
    꼬리는 축 위에 겹쳐 그어져(굵기가 축과 같다) 보이지 않고, 축 밖에 놓이면 「—∿—」 로 선다.
    """
    h = size / 2
    lift = 9 * BREAK_AMP * size / 4          # 조절점 높이 — 곡선 꼭대기가 정확히 BREAK_AMP·size 가 된다
    ease = BREAK_EASE * h
    stub = BREAK_STUB * size
    ux, uy = (1.0, 0.0) if axis == 'x' else (0.0, -1.0)   # 축 방향(화면)
    nx, ny = uy, -ux                                      # 마루 쪽 — x축이면 위, y축이면 왼쪽
    rise = ((-h, 0), (-h + ease, 0), (-ease, lift), (0, 0))
    fall = _cubic_head((0, 0), (ease, -lift), (h - ease, 0), (h, 0), 1 / 3)   # 가운데 → 골 바닥

    def half(sign):
        xy = [f'{cx + sign * (s * ux + v * nx):.2f} {cy + sign * (s * uy + v * ny):.2f}'
              for s, v in ((-h - stub, 0), *rise, *fall[1:])]
        return f'M {xy[0]} L {xy[1]} C {xy[2]} {xy[3]} {xy[4]} C {xy[5]} {xy[6]} {xy[7]}'

    return (f'<path d="{half(1)} {half(-1)}" fill="#fff" stroke="#000" '
            f'stroke-width="{width:g}" stroke-linejoin="round"/>')


def render_graph(spec):
    from core.figure_svg import line as engine_line, curve_path, txt
    fields = FIELDS
    if not isinstance(spec, dict) or spec.get('version') != 'graph-1':
        raise ValueError('graph-1 도형 스펙이 필요합니다.')
    if set(spec) - {'version', 'xRange', 'yRange', 'width', 'height', 'axes', *fields}:
        raise ValueError('지원하지 않는 그래프 필드가 있습니다.')
    if 'axes' in spec and not isinstance(spec['axes'], bool):
        raise ValueError('axes는 참/거짓이어야 합니다.')
    def num(v):
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or abs(v) > 10000:
            raise ValueError('그래프 좌표는 유한한 수여야 합니다.')
        return float(v)
    def point(value):
        if not isinstance(value, list) or len(value) != 2: raise ValueError('그래프 점은 [x,y]여야 합니다.')
        return num(value[0]), num(value[1])
    xlo, xhi = point(spec.get('xRange')); ylo, yhi = point(spec.get('yRange'))
    if xhi <= xlo or yhi <= ylo: raise ValueError('그래프 좌표 범위가 올바르지 않습니다.')
    w = min(640, max(240, num(spec.get('width', 520)))); h = min(640, max(200, num(spec.get('height', 460))))
    pad = 48
    def screen(p):
        x,y = point(p)
        return (pad+(x-xlo)/(xhi-xlo)*(w-2*pad), h-pad-(y-ylo)/(yhi-ylo)*(h-2*pad))
    def xy(p): return ' '.join(f'{v:.3f}' for v in screen(p))
    def style(obj): return ' stroke-dasharray="6 4"' if obj.get('dashed') else ''
    def items(key):
        value=spec.get(key,[])
        if not isinstance(value,list) or len(value)>100 or any(not isinstance(i,dict) for i in value): raise ValueError(f'{key}는 최대 100개의 객체 목록이어야 합니다.')
        for item in value:
            if set(item) - fields[key]: raise ValueError(f'{key}에 지원하지 않는 필드가 있습니다.')
            for flag in ('dashed', 'arrow', 'open'):
                if flag in item and not isinstance(item[flag], bool): raise ValueError(f'{flag}는 참/거짓이어야 합니다.')
        return value
    out=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:g} {h:g}" width="{w:g}" height="{h:g}">']
    def line(a,b,obj=None,sw=1.7):
        obj=obj or {}; x1,y1=screen(a);x2,y2=screen(b)
        out.append(engine_line((x1,y1),(x2,y2),w=sw,dash='6 4' if obj.get('dashed') else None))
        if obj.get('arrow'):
            length=math.hypot(x2-x1,y2-y1)
            if length>0:
                ux=(x2-x1)/length;uy=(y2-y1)/length
                points=f'{x2:.3f},{y2:.3f} {x2-8*ux+3*uy:.3f},{y2-8*uy-3*ux:.3f} {x2-8*ux-3*uy:.3f},{y2-8*uy+3*ux:.3f}'
                out.append(f'<polygon points="{points}" fill="#111"/>')
    if spec.get('axes',True):
        if ylo<=0<=yhi: line([xlo,0],[xhi,0],{'arrow':True},1.4)
        if xlo<=0<=xhi: line([0,ylo],[0,yhi],{'arrow':True},1.4)
    for polygon in items('polygons'):
        points=polygon.get('points',[])
        if not isinstance(points,list) or not 3<=len(points)<=100: raise ValueError('다각형은 3~100개 점이 필요합니다.')
        fill=polygon.get('fill','none')
        if fill!='none' and (not isinstance(fill,str) or len(fill)!=7 or not fill.startswith('#') or any(c not in '0123456789abcdefABCDEF' for c in fill[1:])): raise ValueError('채우기 색은 #RRGGBB여야 합니다.')
        out.append(f'<polygon points="{" ".join(xy(p) for p in points)}" fill="{fill}" stroke="#111" stroke-width="1.7"{style(polygon)}/>')
    for curve in items('curves'):
        lo,hi=point(curve.get('domain',[xlo,xhi]));lo=max(lo,xlo);hi=min(hi,xhi)
        if hi <= lo: raise ValueError('곡선 구간은 그래프 범위 안의 증가하는 구간이어야 합니다.')
        coeff=curve.get('coefficients')
        if curve.get('type') not in (None, 'polynomial', 'inverse'):
            raise ValueError('지원하지 않는 곡선 종류입니다.')
        if (curve.get('type') == 'inverse' and coeff is not None) or (curve.get('type') != 'inverse' and 'k' in curve):
            raise ValueError('다항식과 반비례 곡선 필드를 섞을 수 없습니다.')
        if curve.get('type')=='inverse':
            k=num(curve.get('k'))
            def fn(x): return k/x if abs(x)>1e-8 else math.nan
        else:
            if not isinstance(coeff,list) or not 1<=len(coeff)<=8: raise ValueError('다항식 계수 목록이 필요합니다.')
            coeff=[num(c) for c in coeff]
            def fn(x):
                value=0
                for c in coeff: value=value*x+c
                return value
        runs=[];points=[]
        for i in range(401):
            x=lo+(hi-lo)*i/400;y=fn(x)
            if curve.get('type') == 'inverse' and i > 0 and x > 0 and lo+(hi-lo)*(i-1)/400 < 0:
                if len(points)>1:runs.append(points)
                points=[]
            if not math.isfinite(y) or not ylo<=y<=yhi:
                if len(points)>1:runs.append(points)
                points=[];continue
            points.append(screen([x,y]))
        if len(points)>1:runs.append(points)
        for points in runs:out.append(curve_path(points,w=2,dash='6 4' if curve.get('dashed') else None))
    for segment in items('segments'): line(segment.get('from'),segment.get('to'),segment)
    for circle in items('circles'):
        cx,cy=screen(circle.get('center'));r=num(circle.get('radius'))
        if r<=0:raise ValueError('원의 반지름은 양수여야 합니다.')
        out.append(f'<ellipse cx="{cx:.3f}" cy="{cy:.3f}" rx="{r/(xhi-xlo)*(w-2*pad):.3f}" ry="{r/(yhi-ylo)*(h-2*pad):.3f}" fill="none" stroke="#111" stroke-width="1.7"{style(circle)}/>')
    # 축 생략 물결 — 선(축·선분·곡선) **뒤**라 그 자리의 축을 가리고, 점·글자 **앞**이라 그것들은 안 가린다.
    # 굵기는 밑의 축과 같게 — 자동 축(0 위, 1.4) 이면 1.4, 아니면 선분 축(1.7). 다르면 이음매에 턱이 진다.
    for mark in items('axisBreaks'):
        at=mark.get('at')
        try:
            if not isinstance(at,list) or len(at)!=2: raise ValueError
            bx,by=point(at)
        except ValueError:
            raise ValueError('물결의 자리(at)는 유한한 [x,y]여야 합니다.') from None
        axis=mark.get('axis','x')
        if axis not in ('x','y'):raise ValueError('물결이 끊는 축(axis)은 "x" 또는 "y"여야 합니다.')
        size=mark.get('size',BREAK_SIZE)
        if isinstance(size,bool) or not isinstance(size,(int,float)) or not BREAK_MIN<=size<=24:
            raise ValueError(f'물결의 크기(size)는 {BREAK_MIN}~24 픽셀이어야 합니다.')
        on_auto=spec.get('axes',True) and (by==0 and ylo<=0<=yhi if axis=='x' else bx==0 and xlo<=0<=xhi)
        out.append(axis_break_path(*screen(at),axis,float(size),1.4 if on_auto else 1.7))
    # 꺾인점·끝점의 인쇄된 점 — 반지름은 화면 픽셀이다. 2026-09-18 운영: 이 칸이 없어 모델이 circles(데이터
    # 단위)로 점을 흉내 냈고, x 0~180·y 0~4 그래프에서 세로로 긴 타원이 섰다(다른 모델은 점을 빼먹었다).
    for dot in items('points'):
        px,py=screen(dot.get('at'));r=num(dot.get('radius',3))
        if not 1<=r<=6:raise ValueError('점의 반지름은 1~6 픽셀이어야 합니다.')
        fill,stroke=('#fff',' stroke="#111" stroke-width="1.4"') if dot.get('open') else ('#111','')
        out.append(f'<circle cx="{px:.3f}" cy="{py:.3f}" r="{r:g}" fill="{fill}"{stroke}/>')
    labels=items('labels')
    if spec.get('axes',True):
        if ylo<=0<=yhi: labels=labels+[{'at':[xhi,0],'text':'x','dx':4,'dy':23}]
        if xlo<=0<=xhi: labels=labels+[{'at':[0,yhi],'text':'y','dx':-13,'dy':-8}]
    for label in labels:
        x,y=screen(label.get('at'));x+=num(label.get('dx',0));y+=num(label.get('dy',0));size=min(48,max(10,num(label.get('size',20))))
        text=label.get('text','')
        if not isinstance(text,str) or len(text)>100:raise ValueError('그래프 라벨은 100자 이하여야 합니다.')
        # 한글은 TeX 글꼴에 글리프가 없어 조판을 건너뛰고 원문 <text> 로 나간다 — `$x$(초)` 의 `$` 까지(2026-09-18 운영).
        if HANGUL.search(text):text=re.sub(r'\$([^$]*)\$',r'\1',text)
        anchor=label.get('anchor','middle')
        if anchor not in ('start','middle','end'):raise ValueError('라벨 정렬 값이 올바르지 않습니다.')
        out.append(txt(x,y,text,fs=size,anc=anchor))
    return ''.join(out)+'</svg>'
