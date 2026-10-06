# -*- coding: utf-8 -*-
"""웹 도우미는 **로컬 config.json 을 만들지 않는다** (stdlib·API 0원).

⭐ 왜: 도우미(agent.exe/커넥터)가 이 파일에서 실제로 읽는 값은 ``EQ_WATERMARK``
하나뿐이다 — 키·모델·QC 임계값·DeepSeek 설정은 전부 **서버(Vercel env)** 에 있고
도우미는 OCR·해설을 하지 않는다. 그런데 ``utils.config`` 가 파일이 없으면 기본값
27개를 써 놓아, 도우미 폴더에 "여기에 API 키를 넣어야 할 것처럼 보이는" config.json 이
생기고 **배포 zip 에까지 섞였다**(2026-08-20 사용자 지적). 더 나쁜 경우: 빌드 폴더에
진짜 키가 든 config.json 이 있으면 그대로 남에게 배포된다.

방어는 **두 겹**이다(하나면 조용히 되돌아간다):
  ① 도우미 진입점이 ``MATHGEN_CONFIG_READONLY=1`` 을 세워 자동 생성을 끈다
  ② ``scripts/build_agent.py`` 가 번들·zip 에 config.json 이 있으면 **빌드 실패**

실행: .venv\\Scripts\\python.exe tests/test_helper_config.py
"""
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

for _s in (sys.stdout, sys.stderr):
    try:                        # cp949 콘솔에서 비ASCII print 가 죽는 것 방지
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

FAILED: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  OK   {label}")
    else:
        FAILED.append(label)
        print(f"  FAIL {label}" + (f" — {detail}" if detail else ""))


_PROBE = r'''
import json, pathlib, sys, tempfile
sys.path.insert(0, r"{root}")
import utils.config as c
d = pathlib.Path(tempfile.mkdtemp())
c.CONFIG_PATH = d / "config.json"
c._config = {{}}
cfg = c._load_config()
c.save_config(cfg)          # 명시 저장도 무시돼야 한다(읽기 전용 모드)
print(json.dumps({{
    "readonly": c.config_readonly(),
    "created": (d / "config.json").exists(),
    "keys": len(cfg),
    "watermark": bool(c.get_eq_watermark()),
}}))
'''


def _probe(env_extra: dict) -> dict:
    import json
    env = dict(os.environ)
    env.pop("MATHGEN_CONFIG_READONLY", None)
    env.update(env_extra)
    out = subprocess.run(
        [sys.executable, "-c", _PROBE.format(root=str(ROOT))],
        capture_output=True, text=True, encoding="utf-8", env=env, cwd=str(ROOT))
    return json.loads(out.stdout.strip().splitlines()[-1])


def main() -> int:
    print("A. 읽기 전용 모드(도우미)")
    r = _probe({"MATHGEN_CONFIG_READONLY": "1"})
    check("config.json 을 만들지 않는다", r["readonly"] and not r["created"])
    check("기본값은 메모리로 전부 제공된다", r["keys"] >= 20, str(r["keys"]))
    check("도우미가 쓰는 EQ_WATERMARK 는 그대로 읽힌다", r["watermark"])

    print("B. 기본 모드(GUI exe) 무회귀")
    g = _probe({})
    check("최초 실행에서 config.json 을 만든다(사용자가 키를 넣는 파일)",
          (not g["readonly"]) and g["created"])

    print("C. 진입점이 실제로 켠다")
    for rel in ("agent.py", "server/connector.py", "server/convert_cli.py"):
        src = (ROOT / rel).read_text(encoding="utf-8")
        m = re.search(r'os\.environ\.setdefault\(\s*"MATHGEN_CONFIG_READONLY"', src)
        check(f"{rel} 이 플래그를 세운다", bool(m))
        if m:
            # utils/core 를 import 하기 **전**이어야 한다 — utils.config 는 import
            # 시점에 파일을 읽으므로, 나중에 세우면 이미 만들어진 뒤다.
            hits = [src.find(pat) for pat in
                    ("\nfrom core", "\nimport core", "\nfrom utils", "\nimport utils")]
            first_core = min([h for h in hits if h >= 0] or [len(src)])
            check(f"{rel} — core/utils import 보다 앞에 있다", m.start() < first_core,
                  f"flag@{m.start()} core@{first_core}")

    print("D. 빌드 게이트가 config.json 을 막는다")
    gate = (ROOT / "scripts" / "build_agent.py")
    check("scripts/build_agent.py 존재", gate.exists())
    if gate.exists():
        g_src = gate.read_text(encoding="utf-8")
        check("금지 목록에 config.json", '"config.json"' in g_src)
        check("zip 안까지 검사한다", "_gate_zip" in g_src and "zipfile" in g_src)
        check("키처럼 생긴 값도 본다", "_KEY_RE" in g_src)
        # 실제로 실패하는지 — 임시 dist 를 만들어 게이트 함수만 돌린다.
        sys.path.insert(0, str(ROOT / "scripts"))
        import importlib
        mod = importlib.import_module("build_agent")
        tmp = Path(tempfile.mkdtemp())
        (tmp / "MathGenHWP").mkdir()
        (tmp / "MathGenHWP" / "config.json").write_text("{}", encoding="utf-8")
        import zipfile
        z = tmp / "t.zip"
        with zipfile.ZipFile(z, "w") as zf:
            zf.writestr("MathGenHWP/config.json", '{"GEMINI_API_KEY": ""}')
        try:
            mod._gate_zip(z)
            check("zip 에 config.json 이 있으면 실패시킨다", False, "통과해버림")
        except SystemExit:
            check("zip 에 config.json 이 있으면 실패시킨다", True)

    print("\n전부 통과" if not FAILED else f"\n{len(FAILED)}건 FAIL:\n  - "
          + "\n  - ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
