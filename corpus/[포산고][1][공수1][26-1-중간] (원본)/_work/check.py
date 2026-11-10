# -*- coding: utf-8 -*-
"""렌더 결과 검사: 게이트(.hwp→.hwpx XML) + 쪽 PNG + 메타란 대조.

사용자가 한글을 열어 둔 채로도 돌릴 수 있게 **Hwp 프로세스를 이름으로 죽이지 않는다**
(자동화로 뜬 고아 인스턴스만 정리 — core.hwp_com.automation_hwp_pids).
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")
from core.hwp_com import automation_hwp_pids, hwp_pids, reap_hwp  # noqa: E402

before = hwp_pids() - automation_hwp_pids()          # 사용자가 연 한글(건드리면 안 되는 것)
reap_hwp(automation_hwp_pids())
hwp = sorted((HERE / "out").glob("*_변환.hwp"))[-1]
r = subprocess.run([sys.executable, str(ROOT / ".testkit" / "_s26_gates.py"), str(hwp)],
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
print((r.stdout + r.stderr)[-2600:])
hwpx = hwp.with_name(hwp.stem + "__gate.hwpx")
for old in (HERE / "out").glob("pg_*.png"):
    old.unlink()
r2 = subprocess.run([sys.executable, str(ROOT / "scripts" / "render_to_png.py"), str(hwpx), str(HERE / "out" / "pg")],
                    capture_output=True, text=True, encoding="utf-8", errors="replace")
print((r2.stdout + r2.stderr)[-600:])
r3 = subprocess.run([sys.executable, str(HERE / "_work" / "check_meta.py")],
                    capture_output=True, text=True, encoding="utf-8", errors="replace")
print((r3.stdout + r3.stderr)[-1800:])
alive = hwp_pids()
print("사용자 한글 프로세스 보존:", sorted(before), "→", "OK" if before <= alive else f"사라짐 {sorted(before - alive)}")
