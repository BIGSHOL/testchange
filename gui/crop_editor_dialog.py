"""크롭 편집 다이얼로그.

페이지 이미지 위에 문제 경계 박스(크롭)를 표시하고, 사용자가 드래그로
이동·리사이즈하거나 박스를 추가/삭제할 수 있다. 확인 시 페이지별 최종
CropBox 리스트(정규화 좌표)를 반환한다.

UX(mathg-gen Step1.5 참고):
- 박스마다 좌상단에 "{번호} · {유형}" 배지 — 항상 화면 고정 크기로 또렷이 표시.
- 리사이즈 핸들·배지는 줌과 무관하게 **화면 고정 크기**(이미지 픽셀이 아니라
  화면 픽셀 기준) — 페이지를 축소해도 작아져 안 보이거나 못 잡는 문제 해결.
- 마우스 휠로 줌(커서 기준), 스크롤바로 패닝, '전체 보기'로 리셋.
- class 색상: 문제=파랑, 그림=녹색, 표=주황, 작품=보라(mathg-gen 동일).
"""
from __future__ import annotations

from PIL import Image

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QImage, QPixmap, QPen, QColor, QBrush, QFont, QPainterPath
from PySide6.QtWidgets import (
    QDialog, QGraphicsView, QGraphicsScene, QGraphicsRectItem,
    QGraphicsPixmapItem, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QApplication,
)

from core.crop_detector import CropBox

_HANDLE_PX = 11.0      # 리사이즈 핸들 — 화면 px(줌 무관 고정)
_BADGE_PX = 13.0       # 배지 글자 크기 — 화면 px(줌 무관 고정)
_MIN_SIZE = 8.0        # 최소 박스 크기(scene px)

# class 색상(mathg-gen EditableCropBox 동일)
_KIND_COLOR = {
    "problem": (14, 165, 233),   # 파랑
    "figure": (16, 185, 129),    # 녹색
    "table": (249, 115, 22),     # 주황
    "artwork": (168, 85, 247),   # 보라
}
_KIND_LABEL = {"figure": "그림", "table": "표", "artwork": "작품"}


def _box_label(kind: str, qtype: str, number) -> str:
    """배지 텍스트: "{번호} · {유형}"."""
    num = str(number) if number is not None else "?"
    if kind == "problem":
        sub = {"choice": "객관", "essay": "서술"}.get(qtype, "문제")
    else:
        sub = _KIND_LABEL.get(kind, "문제")
    return f"{num} · {sub}"


class _CropItem(QGraphicsRectItem):
    """이동·리사이즈 가능한 크롭 박스 (8방향 핸들 · 화면 고정 크기 UI)."""

    def __init__(self, rect: QRectF, kind: str = "problem", number=None, qtype: str = ""):
        super().__init__(rect)
        self.kind = kind
        self.number = number
        self.qtype = qtype
        self._handle = None
        self._press_rect = None
        self._press_pos = None
        self.setFlags(
            QGraphicsRectItem.ItemIsMovable
            | QGraphicsRectItem.ItemIsSelectable
            | QGraphicsRectItem.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)
        r, g, b = _KIND_COLOR.get(kind, _KIND_COLOR["problem"])
        self._color = QColor(r, g, b)
        self.setPen(QPen(self._color, 2))
        self.setBrush(QBrush(QColor(r, g, b, 24)))

    # ── 화면 고정 크기 환산 ────────────────────────────────
    def _view_scale(self) -> float:
        """현재 뷰의 scene→화면 배율(줌). 핸들·배지를 화면 px 고정으로 그리기 위함."""
        sc = self.scene()
        if sc and sc.views():
            m = sc.views()[0].transform().m11()
            if m > 0:
                return m
        return 1.0

    # ── 핸들 영역(scene 단위, 화면 고정 크기 환산) ─────────
    def _handles(self) -> dict:
        r = self.rect()
        h = _HANDLE_PX / self._view_scale()   # scene 단위지만 화면상 _HANDLE_PX
        cx, cy = r.center().x(), r.center().y()
        return {
            "tl": QRectF(r.left() - h/2, r.top() - h/2, h, h),
            "tr": QRectF(r.right() - h/2, r.top() - h/2, h, h),
            "bl": QRectF(r.left() - h/2, r.bottom() - h/2, h, h),
            "br": QRectF(r.right() - h/2, r.bottom() - h/2, h, h),
            "t": QRectF(cx - h/2, r.top() - h/2, h, h),
            "b": QRectF(cx - h/2, r.bottom() - h/2, h, h),
            "l": QRectF(r.left() - h/2, cy - h/2, h, h),
            "r": QRectF(r.right() - h/2, cy - h/2, h, h),
        }

    def _handle_at(self, pos: QPointF):
        for name, rect in self._handles().items():
            if rect.contains(pos):
                return name
        return None

    def shape(self) -> QPainterPath:
        """히트 영역 = 박스 + (선택 시) 핸들 영역. 핸들이 박스 밖으로 나가도
        모든 방향에서 잡히도록 path 에 핸들 사각형을 더한다(좌상단만 잡히던 문제 해결).
        """
        path = QPainterPath()
        path.addRect(self.rect())
        if self.isSelected():
            for hr in self._handles().values():
                path.addRect(hr)
        return path

    # ── 그리기 ─────────────────────────────────────────────
    def paint(self, painter, option, widget=None):
        # 박스 본체를 직접 그린다(super().paint() 의 기본 '선택 점선'을 쓰지 않음 —
        # 확대된 boundingRect 에 점선이 그려져 실제 박스와 어긋나 보이던 문제 해결).
        painter.setPen(self.pen())
        painter.setBrush(self.brush())
        painter.drawRect(self.rect())
        inv = 1.0 / self._view_scale()    # scene 단위로 환산된 화면 px
        r = self.rect()

        # 번호+유형 배지 (좌상단, 항상 표시, 화면 고정 크기)
        label = _box_label(self.kind, self.qtype, self.number)
        f = QFont()
        f.setPixelSize(max(1, int(_BADGE_PX * inv)))
        f.setBold(True)
        painter.setFont(f)
        fm = painter.fontMetrics()
        pad = 4 * inv
        tw = fm.horizontalAdvance(label) + pad * 2
        th = fm.height() + pad
        badge = QRectF(r.left(), r.top() - th, tw, th)   # 박스 위쪽에 얹기
        if badge.top() < 0:                              # 페이지 상단이면 박스 안쪽으로
            badge.moveTop(r.top())
        painter.fillRect(badge, self._color)
        painter.setPen(QPen(QColor(255, 255, 255)))
        painter.drawText(badge, Qt.AlignCenter, label)

        # 핸들 (선택 시, 화면 고정 크기)
        if self.isSelected():
            painter.setPen(QPen(self._color, 1.2 * inv))
            painter.setBrush(QBrush(QColor(255, 255, 255)))
            for rect in self._handles().values():
                painter.drawRect(rect)

    def hoverMoveEvent(self, event):
        name = self._handle_at(event.pos())
        cursors = {
            "tl": Qt.SizeFDiagCursor, "br": Qt.SizeFDiagCursor,
            "tr": Qt.SizeBDiagCursor, "bl": Qt.SizeBDiagCursor,
            "t": Qt.SizeVerCursor, "b": Qt.SizeVerCursor,
            "l": Qt.SizeHorCursor, "r": Qt.SizeHorCursor,
        }
        self.setCursor(cursors.get(name, Qt.SizeAllCursor))
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event):
        self._handle = self._handle_at(event.pos())
        if self._handle:
            self._press_rect = QRectF(self.rect())
            self._press_pos = event.pos()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._handle:
            self._resize(event.pos())
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._handle:
            self._handle = None
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def _resize(self, pos: QPointF):
        r = QRectF(self._press_rect)
        d = pos - self._press_pos
        h = self._handle
        if "l" in h:
            r.setLeft(r.left() + d.x())
        if "r" in h:
            r.setRight(r.right() + d.x())
        if "t" in h:
            r.setTop(r.top() + d.y())
        if "b" in h:
            r.setBottom(r.bottom() + d.y())
        if r.width() < _MIN_SIZE:
            r.setWidth(_MIN_SIZE)
        if r.height() < _MIN_SIZE:
            r.setHeight(_MIN_SIZE)
        self.prepareGeometryChange()
        self.setRect(r.normalized())
        self.update()

    def boundingRect(self) -> QRectF:
        # 배지·핸들이 박스 밖으로 약간 나가므로 여유를 둬 잔상 방지.
        m = (_HANDLE_PX + _BADGE_PX * 2) / self._view_scale()
        return self.rect().adjusted(-m, -m, m, m)

    def scene_rect(self) -> QRectF:
        return self.mapToScene(self.rect()).boundingRect()


class _CropView(QGraphicsView):
    """페이지 이미지 + 크롭 박스. 빈 영역 드래그로 새 박스 생성 · 휠 줌."""

    def __init__(self, scene):
        super().__init__(scene)
        self.setRenderHints(self.renderHints())
        self.setDragMode(QGraphicsView.NoDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._drawing = False
        self._start = None
        self._temp = None
        self.new_box_kind = "problem"

    def wheelEvent(self, event):
        # 휠 줌(커서 기준). 핸들·배지는 화면 고정 크기라 줌해도 또렷.
        factor = 1.2 if event.angleDelta().y() > 0 else 1 / 1.2
        self.scale(factor, factor)
        event.accept()

    def mousePressEvent(self, event):
        # 중간 버튼 = 패닝(손 도구)
        if event.button() == Qt.MiddleButton:
            self.setDragMode(QGraphicsView.ScrollHandDrag)
            fake = type(event)(event.type(), event.position(), Qt.LeftButton,
                               Qt.LeftButton, event.modifiers())
            super().mousePressEvent(fake)
            return
        if event.button() == Qt.LeftButton:
            item = self.itemAt(event.pos())
            if isinstance(item, QGraphicsPixmapItem) or item is None:
                self._drawing = True
                self._start = self.mapToScene(event.pos())
                self._temp = _CropItem(QRectF(self._start, self._start),
                                       kind=self.new_box_kind)
                self.scene().addItem(self._temp)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drawing and self._temp:
            cur = self.mapToScene(event.pos())
            self._temp.setRect(QRectF(self._start, cur).normalized())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MiddleButton:
            super().mouseReleaseEvent(event)
            self.setDragMode(QGraphicsView.NoDrag)
            return
        if self._drawing and self._temp:
            self._drawing = False
            if (self._temp.rect().width() < _MIN_SIZE
                    or self._temp.rect().height() < _MIN_SIZE):
                self.scene().removeItem(self._temp)
            else:
                self._temp.setSelected(True)
            self._temp = None
            event.accept()
            return
        super().mouseReleaseEvent(event)


def _pil_to_qpixmap(image: Image.Image) -> QPixmap:
    img = image.convert("RGBA")
    data = img.tobytes("raw", "RGBA")
    qimg = QImage(data, img.width, img.height, QImage.Format_RGBA8888)
    return QPixmap.fromImage(qimg.copy())


class CropEditorDialog(QDialog):
    """페이지별 크롭 박스를 편집한다.

    pages: [(PIL.Image, [CropBox])] — 페이지 이미지와 초기 검출 박스.
    확인 시 self.result_boxes: list[list[CropBox]] (페이지별).
    """

    def __init__(self, pages: list[tuple[Image.Image, list[CropBox]]], parent=None):
        super().__init__(parent)
        self.setWindowTitle("문제 영역(크롭) 검수 · 수정")
        # 화면(작업 영역)에 맞춰 크기 제한 — 큰 고정 크기로 하단 버튼이 잘리던 문제 방지.
        # 시험지는 세로형이라 너무 넓을 필요 없음(좌우 여백 낭비) → 세로 우선 비율.
        screen = self.screen() or QApplication.primaryScreen()
        avail = screen.availableGeometry() if screen else None
        if avail:
            w = min(900, int(avail.width() * 0.9))
            h = min(940, int(avail.height() * 0.9))
            self.resize(w, h)
            self.setMinimumSize(min(560, w), min(420, h))
            # 화면 중앙 배치
            self.move(avail.center().x() - w // 2, avail.center().y() - h // 2)
        else:
            self.resize(900, 900)
            self.setMinimumSize(560, 420)
        self._pages = pages
        self._idx = 0
        self.result_boxes: list[list[CropBox]] | None = None
        self._scene = QGraphicsScene(self)
        self._view = _CropView(self._scene)
        self._pixitem: QGraphicsPixmapItem | None = None
        self._setup_ui()
        self._load_page(0)

    def _setup_ui(self):
        root = QVBoxLayout(self)

        info = QLabel("휠=확대/축소 · 가운데버튼 드래그=이동 · 빈 곳 드래그=박스 추가 · "
                      "박스 선택 후 모서리 핸들=크기조절, Delete=삭제")
        info.setStyleSheet("color:#475467; font-size:12px;")
        info.setWordWrap(True)   # 좁은 창에서 가로 폭 강제 방지
        root.addWidget(info)

        root.addWidget(self._view, 1)

        # 페이지 네비 + 줌 + 도구 — 좁은 화면에서도 한 줄에 들어가도록 컴팩트하게.
        bar = QHBoxLayout()
        bar.setSpacing(4)
        self._prev_btn = QPushButton("◀")
        self._next_btn = QPushButton("▶")
        self._page_lbl = QLabel()
        self._prev_btn.clicked.connect(lambda: self._go(-1))
        self._next_btn.clicked.connect(lambda: self._go(1))
        zoom_in = QPushButton("＋")
        zoom_out = QPushButton("－")
        zoom_fit = QPushButton("맞춤")
        zoom_in.setToolTip("확대"); zoom_out.setToolTip("축소")
        zoom_in.clicked.connect(lambda: self._view.scale(1.25, 1.25))
        zoom_out.clicked.connect(lambda: self._view.scale(0.8, 0.8))
        zoom_fit.clicked.connect(self._fit)
        add_btn = QPushButton("＋박스")
        del_btn = QPushButton("삭제")
        add_btn.setToolTip("박스 추가"); del_btn.setToolTip("선택 박스 삭제")
        add_btn.clicked.connect(self._add_box)
        del_btn.clicked.connect(self._delete_selected)
        for b in (self._prev_btn, self._next_btn, zoom_out, zoom_in, zoom_fit):
            b.setFixedWidth(44)
        for b in (add_btn, del_btn):
            b.setFixedWidth(62)
        bar.addWidget(self._prev_btn)
        bar.addWidget(self._page_lbl)
        bar.addWidget(self._next_btn)
        bar.addStretch(1)
        for wdg in (zoom_out, zoom_in, zoom_fit, add_btn, del_btn):
            bar.addWidget(wdg)
        root.addLayout(bar)

        # 확인/취소 — 항상 보이도록 하단 고정. OK 버튼 라벨 단축.
        btns = QHBoxLayout()
        btns.setSpacing(6)
        cancel = QPushButton("취소")
        ok = QPushButton("이 영역으로 OCR ▶")
        ok.setDefault(True)
        ok.setMinimumHeight(34)
        cancel.clicked.connect(self.reject)
        ok.clicked.connect(self._accept)
        btns.addStretch(1)
        btns.addWidget(cancel)
        btns.addWidget(ok)
        root.addLayout(btns)

    # ── 페이지 로드/저장 ───────────────────────────────────
    def _load_page(self, idx: int):
        self._scene.clear()
        self._pixitem = None
        image, boxes = self._pages[idx]
        pm = _pil_to_qpixmap(image)
        self._pixitem = self._scene.addPixmap(pm)
        self._pixitem.setZValue(-1)
        self._scene.setSceneRect(QRectF(pm.rect()))
        w, h = image.size
        for b in boxes:
            l, t, r, bot = b.to_pixels(w, h)
            item = _CropItem(QRectF(l, t, r - l, bot - t), b.kind, b.number, b.qtype)
            self._scene.addItem(item)
        self._fit()
        empties = sum(1 for (_i, bx) in self._pages if not bx)
        warn = "  ⚠ 빈 페이지는 자동 건너뜀" if not boxes else ""
        self._page_lbl.setText(f"  {idx + 1} / {len(self._pages)} 페이지"
                               f" · 박스 {len(boxes)}개{warn}  ")
        self._prev_btn.setEnabled(idx > 0)
        self._next_btn.setEnabled(idx < len(self._pages) - 1)

    def _fit(self):
        if self._pixitem:
            self._view.fitInView(self._scene.sceneRect(), Qt.KeepAspectRatio)

    def _save_current(self):
        image, _ = self._pages[self._idx]
        w, h = image.size
        boxes = []
        for it in self._scene.items():
            if isinstance(it, _CropItem):
                r = it.scene_rect()
                boxes.append(CropBox(
                    r.left() / w, r.top() / h, r.right() / w, r.bottom() / h,
                    kind=it.kind, number=it.number, qtype=it.qtype).clamp())
        boxes.sort(key=lambda b: (round(b.x0, 1), b.y0))
        self._pages[self._idx] = (image, boxes)

    def _go(self, delta: int):
        self._save_current()
        self._idx = max(0, min(len(self._pages) - 1, self._idx + delta))
        self._load_page(self._idx)

    def _add_box(self):
        rect = self._scene.sceneRect()
        w, h = rect.width(), rect.height()
        item = _CropItem(QRectF(w * 0.3, h * 0.4, w * 0.4, h * 0.15), "problem")
        self._scene.addItem(item)
        item.setSelected(True)

    def _delete_selected(self):
        for it in list(self._scene.selectedItems()):
            if isinstance(it, _CropItem):
                self._scene.removeItem(it)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self._delete_selected()
        else:
            super().keyPressEvent(event)

    def _accept(self):
        self._save_current()
        self.result_boxes = [boxes for (_img, boxes) in self._pages]
        self.accept()


# ── 스모크 테스트 ─────────────────────────────────────────
if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    path = sys.argv[1] if len(sys.argv) > 1 else r"D:\시험지 한글화\data\original_page_2.png"
    img = Image.open(path).convert("RGB")
    init = [
        CropBox(0.03, 0.03, 0.50, 0.18, "problem", 8, "choice"),
        CropBox(0.50, 0.30, 0.98, 0.58, "problem", 13, "essay"),
    ]
    dlg = CropEditorDialog([(img, init)])
    if dlg.exec():
        print("확정 박스:")
        for b in dlg.result_boxes[0]:
            print(f"  num={b.number} {b.kind}/{b.qtype} "
                  f"({b.x0:.2f},{b.y0:.2f},{b.x1:.2f},{b.y1:.2f})")
    else:
        print("취소됨")
