"""크롭 편집 다이얼로그.

페이지 이미지 위에 문제 경계 박스(크롭)를 표시하고, 사용자가 드래그로
이동·리사이즈하거나 박스를 추가/삭제할 수 있다. 확인 시 페이지별 최종
CropBox 리스트(정규화 좌표)를 반환한다.
"""
from __future__ import annotations

from PIL import Image

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QImage, QPixmap, QPen, QColor, QBrush, QFont
from PySide6.QtWidgets import (
    QDialog, QGraphicsView, QGraphicsScene, QGraphicsRectItem,
    QGraphicsPixmapItem, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QListWidget, QListWidgetItem, QWidget,
)

from core.crop_detector import CropBox

_HANDLE = 9.0          # 리사이즈 핸들 크기(px, scene 좌표)
_MIN_SIZE = 12.0       # 최소 박스 크기(px)
_KIND_COLOR = {"problem": (220, 40, 40), "figure": (40, 110, 220),
               "table": (30, 170, 70)}


class _CropItem(QGraphicsRectItem):
    """이동·리사이즈 가능한 크롭 박스 (8방향 핸들)."""

    def __init__(self, rect: QRectF, kind: str = "problem", number=None):
        super().__init__(rect)
        self.kind = kind
        self.number = number
        self._handle = None          # 현재 잡은 핸들 위치
        self._press_rect = None
        self._press_pos = None
        self.setFlags(
            QGraphicsRectItem.ItemIsMovable
            | QGraphicsRectItem.ItemIsSelectable
            | QGraphicsRectItem.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)
        r, g, b = _KIND_COLOR.get(kind, (220, 40, 40))
        self._color = QColor(r, g, b)
        self.setPen(QPen(self._color, 2))
        self.setBrush(QBrush(QColor(r, g, b, 28)))

    # ── 핸들 영역 계산 ─────────────────────────────────────
    def _handles(self) -> dict:
        r = self.rect()
        h = _HANDLE
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

    # ── 그리기 ─────────────────────────────────────────────
    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        # 번호 라벨
        if self.number is not None:
            painter.setPen(QPen(self._color))
            f = QFont(); f.setPointSize(11); f.setBold(True)
            painter.setFont(f)
            painter.drawText(self.rect().adjusted(4, 2, 0, 0),
                             Qt.AlignTop | Qt.AlignLeft, str(self.number))
        # 핸들 (선택 시)
        if self.isSelected():
            painter.setPen(QPen(self._color, 1))
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

    def scene_rect(self) -> QRectF:
        """씬 좌표계 기준 박스 사각형(이동 반영)."""
        return self.mapToScene(self.rect()).boundingRect()


class _CropView(QGraphicsView):
    """페이지 이미지 + 크롭 박스. 빈 영역 드래그로 새 박스 생성."""

    def __init__(self, scene):
        super().__init__(scene)
        self.setRenderHints(self.renderHints())
        self.setDragMode(QGraphicsView.NoDrag)
        self._drawing = False
        self._start = None
        self._temp = None
        self.new_box_kind = "problem"

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            item = self.itemAt(event.pos())
            # 픽스맵(배경) 위 빈 영역이면 새 박스 그리기 시작
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
        if self._drawing and self._temp:
            self._drawing = False
            if self._temp.rect().width() < _MIN_SIZE or self._temp.rect().height() < _MIN_SIZE:
                self.scene().removeItem(self._temp)
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
        self.resize(1000, 820)
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

        info = QLabel("빈 곳을 드래그해 박스 추가 · 박스 모서리를 끌어 크기 조절 · "
                      "선택 후 Delete 로 삭제")
        info.setStyleSheet("color:#475467; font-size:12px;")
        root.addWidget(info)

        root.addWidget(self._view, 1)

        # 페이지 네비 + 도구
        bar = QHBoxLayout()
        self._prev_btn = QPushButton("◀ 이전 페이지")
        self._next_btn = QPushButton("다음 페이지 ▶")
        self._page_lbl = QLabel()
        self._prev_btn.clicked.connect(lambda: self._go(-1))
        self._next_btn.clicked.connect(lambda: self._go(1))
        add_btn = QPushButton("＋ 박스 추가")
        del_btn = QPushButton("－ 선택 삭제")
        add_btn.clicked.connect(self._add_box)
        del_btn.clicked.connect(self._delete_selected)
        for wdg in (self._prev_btn, self._page_lbl, self._next_btn):
            bar.addWidget(wdg)
        bar.addStretch(1)
        bar.addWidget(add_btn)
        bar.addWidget(del_btn)
        root.addLayout(bar)

        # 확인/취소
        btns = QHBoxLayout()
        btns.addStretch(1)
        cancel = QPushButton("취소")
        ok = QPushButton("이 영역으로 OCR 진행")
        ok.setDefault(True)
        cancel.clicked.connect(self.reject)
        ok.clicked.connect(self._accept)
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
            item = _CropItem(QRectF(l, t, r - l, bot - t), b.kind, b.number)
            self._scene.addItem(item)
        self._view.fitInView(self._scene.sceneRect(), Qt.KeepAspectRatio)
        self._page_lbl.setText(f"  {idx + 1} / {len(self._pages)} 페이지  ")
        self._prev_btn.setEnabled(idx > 0)
        self._next_btn.setEnabled(idx < len(self._pages) - 1)

    def _save_current(self):
        """현재 씬의 박스를 정규화 좌표로 _pages에 반영."""
        image, _ = self._pages[self._idx]
        w, h = image.size
        boxes = []
        for it in self._scene.items():
            if isinstance(it, _CropItem):
                r = it.scene_rect()
                boxes.append(CropBox(
                    r.left() / w, r.top() / h, r.right() / w, r.bottom() / h,
                    kind=it.kind, number=it.number).clamp())
        # 위→아래, 좌→우 정렬(2단 고려: x를 큰 구간으로 묶어 좌우 우선)
        boxes.sort(key=lambda b: (round(b.x0, 1), b.y0))
        self._pages[self._idx] = (image, boxes)

    def _go(self, delta: int):
        self._save_current()
        self._idx = max(0, min(len(self._pages) - 1, self._idx + delta))
        self._load_page(self._idx)

    def _add_box(self):
        # 화면 중앙에 기본 박스 추가
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

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._pixitem:
            self._view.fitInView(self._scene.sceneRect(), Qt.KeepAspectRatio)

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
        CropBox(0.03, 0.03, 0.50, 0.18, "problem", 8),
        CropBox(0.50, 0.30, 0.98, 0.58, "problem", 13),
    ]
    dlg = CropEditorDialog([(img, init)])
    if dlg.exec():
        print("확정 박스:")
        for b in dlg.result_boxes[0]:
            print(f"  num={b.number} {b.kind} ({b.x0:.2f},{b.y0:.2f},{b.x1:.2f},{b.y1:.2f})")
    else:
        print("취소됨")
