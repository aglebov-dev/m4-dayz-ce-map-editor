"""Вьюпорт карты: сцена в пикселях полного зума (1 px = 1 м + поля), зум колесом, пан мышью."""
from __future__ import annotations

from collections import OrderedDict

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush, QColor, QImage, QPainter, QPalette, QPen, QPixmap,
)
from PySide6.QtWidgets import QGraphicsEllipseItem, QGraphicsScene, QGraphicsView

# клик = нажатие и отпускание почти в одном месте; больше — это пан
CLICK_SLOP_PX = 4

from core.tiles import TileMeta, iter_zoom_tiles
from ui.buildings_item import BuildingsItem, ClustersItem
from ui.shape_item import GRAB_PX, ShapeItem
from ui.territories_item import TerritoriesItem
from ui.zone_labels_item import ZoneLabelsItem

# задник: один низкодетальный уровень на весь мир, чтобы при пане не было серых дыр
BASE_ZOOM = 3
# LRU-кэш пиксмапов тайлов, шт. (256×256 ARGB ≈ 256 КБ → ~128 МБ максимум)
PIXMAP_CACHE_CAP = 512
# запас видимой области под подгрузку, доли вьюпорта с каждой стороны
PREFETCH = 0.25

MIN_SCALE = 0.02
MAX_SCALE = 8.0
# поля прокрутки вокруг карты (доля от её размера): пан работает даже при полном отдалении
PAN_MARGIN_FRAC = 0.75


class MapView(QGraphicsView):
    cursor_world = Signal(float, float)     # мировые координаты под курсором
    clicked_world = Signal(float, float)
    region_selected = Signal(float, float, float, float)   # x0, z0, x1, z1 (метры)
    region_cleared = Signal()
    stroke_started = Signal()               # ЛКМ нажата в режиме кисти
    paint_world = Signal(float, float)      # мазок кисти в мировой точке
    stroke_finished = Signal()              # ЛКМ отпущена — мазок закончен
    shape_committed = Signal(str, list)     # (kind, точки в мировых метрах) — залить
    shape_state = Signal(bool)              # есть ли контур, который можно применить

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setRenderHints(QPainter.SmoothPixmapTransform)
        # NoDrag всегда: пан делаем вручную (и ЛКМ, и ПКМ), чтобы Qt не подменял курсор
        # «рукой». Курсор везде обычный — по просьбе владельца.
        self.setDragMode(QGraphicsView.NoDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        # Скроллбары не показываем: пан делаем вручную через setValue (диапазон есть за счёт
        # полей PAN_MARGIN и без видимой полосы). Иначе у границы вписывания скроллбары
        # мигают, меняют размер вьюпорта и карта «дёргается» между двумя состояниями.
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setMouseTracking(True)
        # фон за пределами мира — в тон окна приложения
        self.setBackgroundBrush(self.palette().color(QPalette.ColorRole.Window))
        self._meta: TileMeta | None = None
        self._world_size = 15360
        self._tile_items: dict[tuple[int, int, int], object] = {}   # (z,x,y) -> item
        self._pixmap_cache: OrderedDict[tuple[int, int, int], QPixmap] = OrderedDict()
        self._update_scheduled = False
        # именованные оверлеи: key -> {"pixmap", "item", "visible", "z", "opacity"}
        self._overlays: dict[str, dict] = {}
        self._marker: QGraphicsEllipseItem | None = None
        self._marker_world: tuple[float, float] | None = None
        self._border = None
        # слои зданий: key -> {"x","z","color","idx","item","visible"}
        self._bld_layers: dict[str, dict] = {}
        self._bld_clusters: ClustersItem | None = None   # общий слой кластеров
        # территории животных: key -> {"x","z","r","color","item","visible"}
        self._terr_layers: dict[str, dict] = {}
        self._terr_opacity = 1.0
        self._bld_opacity = 1.0
        self._bld_selected: int | None = None    # глобальный индекс выделенного
        # подписи зон выбранного слоя: сами данные + состояние тогла
        self._zone_labels: ZoneLabelsItem | None = None
        self._zone_labels_args: tuple | None = None   # (zones, cell_size, color)
        self._zone_labels_visible = True
        self._zone_selected: int | None = None
        # выделение области: режим рамки + текущий прямоугольник (мировые метры)
        self._select_mode = False
        self._sel_item = None
        self._sel_world: tuple[float, float, float, float] | None = None
        self._sel_press = None                   # точка начала рамки в сцене
        self._pan_press = None                   # ПКМ-пан: прошлая точка на экране
        self._lpan_last = None                   # ЛКМ-пан (обычный режим): прошлая точка
        # кисть: режим, радиус в метрах, курсор-кружок и признак «мазок идёт»
        self._brush_mode = False
        self._brush_radius = 50.0
        self._brush_cursor = None
        self._painting = False
        # инструмент рисования: brush | rect | ellipse | polygon | lasso
        self._tool = "brush"
        self._shape = None                       # ShapeItem: контур-превью
        self._drag_handle = -1                   # какую ручку тащим (-1 — никакую)
        self._drag_from = None                   # точка сцены для переноса фигуры
        # ПКМ занята паном — контекстное меню на карте не нужно
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        # "merged" — единые кружки (v2); "per-layer" — каждый слой в своём кружке (v1)
        self.cluster_mode = "merged"
        self._content = None                     # QRectF карты (сцена шире на поля пана)
        # «режим вписывания»: пока пользователь не зумил, карта следует за размером окна.
        # Надёжнее геометрической проверки: стартовый fit до show() мог пройти при неверном
        # размере вьюпорта — тогда карта «съезжала» в левый верхний угол до первого зума.
        self._auto_fit = True

    # ---------- загрузка подложки ----------

    def clear_map(self):
        self.scene().clear()                     # уносит и оверлеи — пересоздадим
        self._meta = None
        self._tile_items.clear()
        self._pixmap_cache.clear()
        for ov in self._overlays.values():
            ov["item"] = None
        self._marker = None
        self._border = None
        self._bld_clusters = None
        for tl in self._terr_layers.values():
            tl["item"] = None
        self._zone_labels = None                 # пересоберём в _apply_overlays
        self._sel_item = None
        self._shape = None                       # контур принадлежал прошлой карте
        self._brush_cursor = None
        for bl in self._bld_layers.values():
            bl["item"] = None

    def load_tiles(self, meta: TileMeta):
        """Подложка из пирамиды: статичный задник BASE_ZOOM + стриминг видимых тайлов."""
        self.clear_map()
        self._meta = meta
        self._world_size = meta.world_size
        base = min(BASE_ZOOM, meta.max_zoom)
        k = meta.scale_at(base)                      # во сколько раз растянуть тайлы
        for x, y, path in iter_zoom_tiles(meta, base):
            pm = QPixmap(path)
            if pm.isNull():
                continue
            item = self.scene().addPixmap(pm)
            item.setScale(k)
            item.setPos(x * meta.tile_size * k, y * meta.tile_size * k)
            item.setZValue(-1)                       # всегда под стримингом, не выгружается
        self.set_content_rect(meta.width, meta.height)
        self._apply_overlays()
        self.fit_all()
        self._schedule_tiles_update()

    # ---------- стриминг тайлов ----------

    def _schedule_tiles_update(self):
        """Коалесцирует шквал событий пана/зума в одно обновление на итерацию цикла."""
        if self._update_scheduled or not self._meta:
            return
        self._update_scheduled = True
        QTimer.singleShot(0, self._update_tiles)

    def _update_tiles(self):
        self._update_scheduled = False
        meta = self._meta
        if not meta:
            return
        zoom = meta.zoom_for_scale(self.transform().m11())
        needed: set[tuple[int, int, int]] = set()
        if zoom > min(BASE_ZOOM, meta.max_zoom):     # ниже задник и так покрывает всё
            r = self.mapToScene(self.viewport().rect()).boundingRect()
            dx, dy = r.width() * PREFETCH, r.height() * PREFETCH
            r = r.adjusted(-dx, -dy, dx, dy).intersected(self.scene().sceneRect())
            needed = {(zoom, x, y)
                      for x, y in meta.tiles_in_rect(zoom, r.left(), r.top(),
                                                     r.right(), r.bottom())}
        for key in needed - self._tile_items.keys():
            pm = self._tile_pixmap(key)
            if pm is None:
                continue
            z, x, y = key
            k = meta.scale_at(z)
            item = self.scene().addPixmap(pm)
            item.setScale(k)
            item.setPos(x * meta.tile_size * k, y * meta.tile_size * k)
            self._tile_items[key] = item
        for key in self._tile_items.keys() - needed:  # невидимые и чужие уровни — долой
            self.scene().removeItem(self._tile_items.pop(key))

    def _tile_pixmap(self, key: tuple[int, int, int]) -> QPixmap | None:
        cached = self._pixmap_cache.get(key)
        if cached is not None:
            self._pixmap_cache.move_to_end(key)
            return cached
        z, x, y = key
        pm = QPixmap(self._meta.tile_path(z, x, y))
        if pm.isNull():
            return None
        self._pixmap_cache[key] = pm
        while len(self._pixmap_cache) > PIXMAP_CACHE_CAP:
            self._pixmap_cache.popitem(last=False)
        return pm

    def load_image(self, path: str, world_size: int):
        """Подложка из одного файла-картинки: растягиваем на квадрат мира (без полей)."""
        self.clear_map()
        self._world_size = world_size
        pm = QPixmap(path)
        if pm.isNull():
            return False
        item = self.scene().addPixmap(pm)
        item.setScale(world_size / max(1, pm.width()))
        self.set_content_rect(world_size, world_size)
        self._apply_overlays()
        self.fit_all()
        return True

    # ---------- оверлеи (тиры, usage-слои, ...) ----------

    def set_overlay(self, key: str, pixmap: QPixmap | None, z: int = 10,
                    opacity: float = 0.45):
        """Именованный оверлей на квадрат мира (с тайлами — внутри полей). None — убрать."""
        old = self._overlays.pop(key, None)
        if old and old["item"]:
            self.scene().removeItem(old["item"])
        if pixmap is None:
            return
        visible = old["visible"] if old else True
        self._overlays[key] = {"pixmap": pixmap, "item": None, "visible": visible,
                               "z": z, "opacity": opacity}
        self._apply_one(key)

    def set_overlay_visible(self, key: str, b: bool):
        ov = self._overlays.get(key)
        if not ov:
            return
        ov["visible"] = b
        if ov["item"]:
            ov["item"].setVisible(b)

    def set_overlay_opacity(self, v: float, prefix: str = ""):
        """Прозрачность оверлеев, чьи ключи начинаются с prefix ('' — все)."""
        for key, ov in self._overlays.items():
            if key.startswith(prefix):
                ov["opacity"] = v
                if ov["item"]:
                    ov["item"].setOpacity(v)

    def clear_overlays(self):
        for key in list(self._overlays):
            self.set_overlay(key, None)

    def patch_overlay(self, key: str, x_px: int, y_px: int, rgba):
        """Перерисовать КУСОК оверлея (мазок кисти): пересборка всей плоскости
        4096² на каждое движение мыши не успевала бы за курсором."""
        ov = self._overlays.get(key)
        if not ov:
            return
        h, w = rgba.shape[:2]
        img = QImage(rgba.data, w, h, w * 4, QImage.Format.Format_RGBA8888).copy()
        p = QPainter(ov["pixmap"])
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        p.drawImage(x_px, y_px, img)             # Source: патч замещает, а не смешивается
        p.end()
        if ov["item"]:
            ov["item"].setPixmap(ov["pixmap"])

    def _apply_one(self, key: str):
        ov = self._overlays[key]
        if ov["item"]:
            self.scene().removeItem(ov["item"])
        margin = self._meta.margin if self._meta else 0
        item = self.scene().addPixmap(ov["pixmap"])
        item.setZValue(ov["z"])                  # поверх подложки и стриминга
        item.setScale(self._world_size / max(1, ov["pixmap"].width()))
        item.setPos(margin, margin)
        item.setOpacity(ov["opacity"])
        item.setVisible(ov["visible"])
        ov["item"] = item

    def _apply_overlays(self):
        for key in self._overlays:
            self._apply_one(key)
        if self._marker_world:
            self.set_marker(*self._marker_world)
        for key in self._bld_layers:
            self._apply_buildings(key)
        for key in self._terr_layers:
            self._apply_territory(key)
        self._apply_zone_labels()
        self._apply_selection()
        self.add_border()

    # ---------- выделение области ----------

    def set_select_mode(self, on: bool):
        """Режим рамки: ЛКМ тянет выделение вместо пана. Пан остаётся на ПКМ.
        Курсор не меняем — обычной стрелки достаточно во всех режимах."""
        self._select_mode = on

    def set_region(self, x0: float, z0: float, x1: float, z1: float):
        """Выделить мировой прямоугольник (метры) программно."""
        x0, x1 = sorted((x0, x1))
        z0, z1 = sorted((z0, z1))
        w = self._world_size
        self._sel_world = (max(0.0, x0), max(0.0, z0), min(w, x1), min(w, z1))
        self._apply_selection()

    def clear_region(self):
        self._sel_world = None
        self._apply_selection()

    def region(self) -> tuple[float, float, float, float] | None:
        return self._sel_world

    def _apply_selection(self):
        from PySide6.QtCore import QRectF
        if self._sel_item:
            self.scene().removeItem(self._sel_item)
            self._sel_item = None
        if not self._sel_world:
            return
        x0, z0, x1, z1 = self._sel_world
        margin = self._meta.margin if self._meta else 0
        rect = QRectF(margin + x0, margin + (self._world_size - z1),
                      max(1.0, x1 - x0), max(1.0, z1 - z0))
        pen = QPen(QColor(255, 255, 255), 2, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)                    # 2 px на экране при любом зуме
        self._sel_item = self.scene().addRect(rect, pen,
                                              QBrush(QColor(255, 255, 255, 30)))
        self._sel_item.setZValue(44)             # под рамкой карты и маркером

    # ---------- кисть ----------

    def set_brush_mode(self, on: bool):
        """Режим кисти: ЛКМ рисует по активному слою. Пан остаётся на ПКМ.
        Взаимоисключение с режимом рамки держит окно. Курсор не меняем — обычная
        стрелка; кружок размера кисти показываем поверх неё (это элемент сцены)."""
        self._brush_mode = on
        if on:
            self.setFocus()                      # иначе Enter/Esc до нас не дойдут
        else:
            self.cancel_shape()                  # контур принадлежал режиму рисования
        self._update_brush_cursor(None)

    def set_tool(self, tool: str):
        """Инструмент режима рисования. Смена инструмента бросает недоделанный контур."""
        if tool != self._tool:
            self.cancel_shape()
        self._tool = tool
        self._update_brush_cursor(None)          # кружок кисти — только у кисти

    def tool(self) -> str:
        return self._tool

    # ---------- фигуры (контур с ручками, заливка по Enter) ----------

    def cancel_shape(self):
        if self._shape:
            self.scene().removeItem(self._shape)
            self._shape = None
        self._drag_handle = -1
        self._drag_from = None
        self.shape_state.emit(False)

    def commit_shape(self):
        """Enter: залить контур. Линию (вырожденный контур) не применяем."""
        s = self._shape
        if not s or s.building or s.is_degenerate():
            return
        self.shape_committed.emit(s.kind, s.world_points())
        self.cancel_shape()

    def has_shape(self) -> bool:
        return bool(self._shape and not self._shape.building
                    and not self._shape.is_degenerate())

    def _new_shape(self, kind: str, pts):
        self.cancel_shape()
        self._shape = ShapeItem(kind, pts, self._world_size,
                                self._meta.margin if self._meta else 0)
        self.scene().addItem(self._shape)
        return self._shape

    def keyPressEvent(self, ev):
        if ev.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.commit_shape()
            return
        if ev.key() == Qt.Key.Key_Escape:
            self.cancel_shape()
            return
        super().keyPressEvent(ev)

    def set_brush_radius(self, r_m: float):
        self._brush_radius = max(1.0, r_m)
        if self._brush_cursor:
            self._update_brush_cursor(self._brush_cursor.pos())

    def _update_brush_cursor(self, pos):
        """Кружок под курсором в РЕАЛЬНОМ размере кисти (в метрах сцены)."""
        if not self._brush_mode or self._tool != "brush" or pos is None:
            if self._brush_cursor:
                self.scene().removeItem(self._brush_cursor)
                self._brush_cursor = None
            return
        r = self._brush_radius
        if self._brush_cursor is None:
            pen = QPen(QColor(255, 255, 255), 1)
            pen.setCosmetic(True)
            self._brush_cursor = self.scene().addEllipse(
                QRectF(-r, -r, 2 * r, 2 * r), pen, QBrush(QColor(255, 255, 255, 40)))
            self._brush_cursor.setZValue(60)     # поверх всего: это курсор
        self._brush_cursor.setRect(QRectF(-r, -r, 2 * r, 2 * r))
        self._brush_cursor.setPos(pos)

    # ---------- подписи зон (слой, выбранный в панели «Зоны») ----------

    def set_zone_labels(self, zones, cell_size: float, color: tuple[int, int, int]):
        """Подписи зон одного слоя; zones=None — убрать."""
        self._zone_labels_args = None if zones is None else (zones, cell_size, color)
        self._zone_selected = None
        self._apply_zone_labels()

    def set_zone_labels_visible(self, b: bool):
        self._zone_labels_visible = b
        if self._zone_labels:
            self._zone_labels.setVisible(b)

    def set_zone_labels_color(self, color: tuple[int, int, int]):
        if not self._zone_labels_args:
            return
        zones, cell_size, _ = self._zone_labels_args
        self._zone_labels_args = (zones, cell_size, color)
        if self._zone_labels:
            self._zone_labels.set_color(color)

    def set_selected_zone(self, index: int | None):
        """Подсветить подпись зоны (клик по строке в панели «Зоны»)."""
        self._zone_selected = index
        if self._zone_labels:
            self._zone_labels.set_selected(index)

    def _apply_zone_labels(self):
        if self._zone_labels:
            self.scene().removeItem(self._zone_labels)
            self._zone_labels = None
        if not self._zone_labels_args:
            return
        zones, cell_size, color = self._zone_labels_args
        item = ZoneLabelsItem(zones, cell_size, self._world_size,
                              self._meta.margin if self._meta else 0, color)
        item.setZValue(40)                       # над оверлеями и зданиями, под маркером
        item.setVisible(self._zone_labels_visible)
        item.set_selected(self._zone_selected)
        self.scene().addItem(item)
        self._zone_labels = item

    # ---------- здания (несколько слоёв: все / по флагам) ----------

    def set_buildings(self, key: str, x, z, color: tuple[int, int, int], indices=None):
        """Слой точек зданий. indices — глобальные индексы инстансов (для выделения).
        x=None — убрать слой."""
        old = self._bld_layers.pop(key, None)
        if old and old["item"]:
            self.scene().removeItem(old["item"])
        if x is None:
            self._rebuild_clusters()
            return
        visible = old["visible"] if old else False
        self._bld_layers[key] = {"x": x, "z": z, "color": color, "idx": indices,
                                 "item": None, "visible": visible}
        self._apply_buildings(key)

    def clear_buildings(self):
        self._bld_selected = None
        for key in list(self._bld_layers):
            self.set_buildings(key, None, None, (0, 0, 0))

    def set_buildings_visible(self, key: str, b: bool):
        bl = self._bld_layers.get(key)
        if not bl:
            return
        bl["visible"] = b
        if bl["item"]:
            bl["item"].setVisible(b)
        self._rebuild_clusters()

    def set_buildings_color(self, key: str, color: tuple[int, int, int]):
        bl = self._bld_layers.get(key)
        if not bl:
            return
        bl["color"] = color
        if bl["item"]:
            bl["item"].set_color(color)
        self._rebuild_clusters()

    def set_buildings_opacity(self, v: float):
        """Общая прозрачность всех слоёв зданий (слайдер секции «Объекты»)."""
        self._bld_opacity = v
        for bl in self._bld_layers.values():
            if bl["item"]:
                bl["item"].setOpacity(v)
        if self._bld_clusters:
            self._bld_clusters.setOpacity(v)

    def set_selected_building(self, index: int | None):
        """Подсветить отметку здания ВО ВСЕХ слоях, где оно есть (глобальный индекс)."""
        self._bld_selected = index
        for bl in self._bld_layers.values():
            if bl["item"]:
                bl["item"].set_selected(self._local_selected(bl))
        self._rebuild_clusters()

    def _local_selected(self, bl: dict) -> int | None:
        """Глобальный выделенный индекс -> позиция в подслое (или None)."""
        i = self._bld_selected
        if i is None or bl["idx"] is None:
            return None
        import numpy as np
        pos = np.flatnonzero(bl["idx"] == i)
        return int(pos[0]) if len(pos) else None

    def _apply_buildings(self, key: str):
        bl = self._bld_layers[key]
        if bl["item"]:
            self.scene().removeItem(bl["item"])
        margin = self._meta.margin if self._meta else 0
        item = BuildingsItem(bl["x"], bl["z"], self._world_size, margin, bl["color"],
                             per_layer_clusters=(self.cluster_mode == "per-layer"))
        item.setZValue(30)
        item.setVisible(bl["visible"])
        item.setOpacity(self._bld_opacity)
        item.set_selected(self._local_selected(bl))
        self.scene().addItem(item)
        bl["item"] = item
        self._rebuild_clusters()

    def _rebuild_clusters(self):
        """Общий слой кластеров: уникальные здания ВИДИМЫХ слоёв, без дублей."""
        import numpy as np
        if self.cluster_mode != "merged":        # per-layer: слои рисуют кружки сами
            if self._bld_clusters:
                self.scene().removeItem(self._bld_clusters)
                self._bld_clusters = None
            return
        if self._bld_clusters is None:
            self._bld_clusters = ClustersItem(self._world_size,
                                              self._meta.margin if self._meta else 0)
            self._bld_clusters.setZValue(32)
            self._bld_clusters.setOpacity(self._bld_opacity)
            self.scene().addItem(self._bld_clusters)
        xs, zs, ids = [], [], []
        for bl in self._bld_layers.values():
            if bl["visible"] and len(bl["x"]):
                xs.append(bl["x"])
                zs.append(bl["z"])
                ids.append(bl["idx"] if bl["idx"] is not None
                           else np.arange(len(bl["x"])))
        if not xs:
            self._bld_clusters.set_data(np.empty(0), np.empty(0), None)
            return
        all_ids = np.concatenate(ids)
        uniq, first = np.unique(all_ids, return_index=True)
        ux = np.concatenate(xs)[first]
        uz = np.concatenate(zs)[first]
        sel = None
        if self._bld_selected is not None:
            pos = np.flatnonzero(uniq == self._bld_selected)
            sel = int(pos[0]) if len(pos) else None
        self._bld_clusters.set_data(ux, uz, sel)

    def add_border(self):
        """Рамка по краю карты: видно, где кончаются данные, а не просто тёмное море."""
        if self._border:
            self.scene().removeItem(self._border)
        base = self._content if self._content is not None else self.scene().sceneRect()
        r = base.adjusted(0.5, 0.5, -0.5, -0.5)
        pen = QPen(QColor(255, 255, 255, 110))
        pen.setCosmetic(True)                    # 1 px на экране при любом зуме
        self._border = self.scene().addRect(r, pen, QBrush(Qt.BrushStyle.NoBrush))
        self._border.setZValue(45)

    # ---------- территории животных (круги слоями) ----------

    def set_territory(self, key: str, x, z, r, color: tuple[int, int, int]):
        """Слой кругов территории. x=None — убрать слой."""
        old = self._terr_layers.pop(key, None)
        if old and old["item"]:
            self.scene().removeItem(old["item"])
        if x is None:
            return
        visible = old["visible"] if old else False
        self._terr_layers[key] = {"x": x, "z": z, "r": r, "color": color,
                                  "item": None, "visible": visible}
        self._apply_territory(key)

    def clear_territories(self):
        for key in list(self._terr_layers):
            self.set_territory(key, None, None, None, (0, 0, 0))

    def set_territory_visible(self, key: str, b: bool):
        tl = self._terr_layers.get(key)
        if not tl:
            return
        tl["visible"] = b
        if tl["item"]:
            tl["item"].setVisible(b)

    def set_territory_color(self, key: str, color: tuple[int, int, int]):
        tl = self._terr_layers.get(key)
        if not tl:
            return
        tl["color"] = color
        if tl["item"]:
            tl["item"].set_color(color)

    def set_territory_opacity(self, v: float):
        self._terr_opacity = v
        for tl in self._terr_layers.values():
            if tl["item"]:
                tl["item"].setOpacity(v)

    def _apply_territory(self, key: str):
        tl = self._terr_layers[key]
        if tl["item"]:
            self.scene().removeItem(tl["item"])
        margin = self._meta.margin if self._meta else 0
        item = TerritoriesItem(tl["x"], tl["z"], tl["r"], self._world_size, margin,
                               tl["color"])
        item.setZValue(35)                       # над оверлеями, под маркером/фигурами
        item.setOpacity(self._terr_opacity)
        item.setVisible(tl["visible"])
        self.scene().addItem(item)
        tl["item"] = item

    # ---------- маркер инспектируемой точки ----------

    def set_marker(self, x: float, z: float):
        """Кружок в мировой точке; размер не зависит от зума."""
        if self._marker:
            self.scene().removeItem(self._marker)
        margin = self._meta.margin if self._meta else 0
        m = QGraphicsEllipseItem(-6, -6, 12, 12)
        m.setPen(QPen(QColor(255, 255, 255), 2))
        m.setBrush(QColor(255, 64, 64, 160))
        m.setZValue(50)
        m.setFlag(m.GraphicsItemFlag.ItemIgnoresTransformations)
        m.setPos(margin + x, margin + (self._world_size - z))
        self.scene().addItem(m)
        self._marker = m
        self._marker_world = (x, z)

    def clear_marker(self):
        if self._marker:
            self.scene().removeItem(self._marker)
        self._marker = None
        self._marker_world = None

    def set_content_rect(self, w: float, h: float):
        """Прямоугольник карты (0,0,w,h); сцена получает поля вокруг для свободного пана."""
        from PySide6.QtCore import QRectF
        self._content = QRectF(0, 0, w, h)
        pad = max(w, h) * PAN_MARGIN_FRAC
        self.scene().setSceneRect(-pad, -pad, w + 2 * pad, h + 2 * pad)

    def fit_all(self):
        rect = self._content if self._content is not None else self.scene().sceneRect()
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
        self._auto_fit = True                    # карта вписана — следуем за размером окна
        self._schedule_tiles_update()

    def zoom_to_world(self, x0: float, z0: float, x1: float, z1: float,
                      pad_frac: float = 0.3, max_scale: float = 2.0):
        """Показать мировой прямоугольник (x, z в метрах) с полями вокруг."""
        from PySide6.QtCore import QRectF
        margin = self._meta.margin if self._meta else 0
        left = margin + x0
        top = margin + (self._world_size - z1)
        rect = QRectF(left, top, max(1.0, x1 - x0), max(1.0, z1 - z0))
        pad = max(rect.width(), rect.height()) * pad_frac
        rect = rect.adjusted(-pad, -pad, pad, pad)
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
        s = self.transform().m11()
        if s > max_scale:                        # крошечная зона — не зумим до пикселей
            self.scale(max_scale / s, max_scale / s)
        self._auto_fit = False                   # прицельный зум — окно больше не вписывает
        self._schedule_tiles_update()

    def fit_all_deferred(self):
        """fit после того, как окно получит реальные размеры (при загрузке до show)."""
        QTimer.singleShot(0, self.fit_all)

    def showEvent(self, ev):
        super().showEvent(ev)
        if not getattr(self, "_shown_once", False):
            self._shown_once = True
            self.fit_all_deferred()

    # ---------- координаты ----------

    def _scene_to_world(self, sp) -> tuple[float, float]:
        if self._meta:
            return self._meta.px_to_world(sp.x(), sp.y())
        return sp.x(), self._world_size - sp.y()

    # ---------- события ----------

    def wheelEvent(self, ev):
        factor = 1.25 if ev.angleDelta().y() > 0 else 0.8
        cur = self.transform().m11()
        if MIN_SCALE <= cur * factor <= MAX_SCALE:
            self.scale(factor, factor)
            self._auto_fit = False               # пользователь зумит — окно больше не вписывает
            self._schedule_tiles_update()

    def scrollContentsBy(self, dx, dy):
        super().scrollContentsBy(dx, dy)
        self._schedule_tiles_update()

    def resizeEvent(self, ev):
        """Вьюпорт изменился (разворот окна, открытие/закрытие панелей, ПЕРВЫЙ показ после
        загрузки до show). В режиме вписывания (`_auto_fit`, пока пользователь не зумил)
        держим карту вписанной и после ресайза — масштаб следует за окном. Это же чинит
        стартовый «съезд» в левый верхний угол: первый корректный размер приходит именно
        сюда, и мы перевписываем. Если пользователь приближён — зум не трогаем."""
        super().resizeEvent(ev)
        if self._auto_fit and self._content is not None:
            self.fit_all()
        self._schedule_tiles_update()

    def mouseMoveEvent(self, ev):
        sp = self.mapToScene(ev.position().toPoint())
        wx, wz = self._scene_to_world(sp)
        self.cursor_world.emit(wx, wz)
        if self._pan_press is not None:          # ПКМ-пан: тащим вьюпорт за курсором
            self._pan_press = self._pan_by(ev.position().toPoint(), self._pan_press)
            return
        if self._lpan_last is not None:          # ЛКМ-пан в обычном режиме
            self._lpan_last = self._pan_by(ev.position().toPoint(), self._lpan_last)
            return
        if self._brush_mode and self._tool != "brush":
            if self._shape_move(sp):
                return
        elif self._brush_mode:
            self._update_brush_cursor(sp)
            if self._painting:                   # мазок с протяжкой
                self.paint_world.emit(wx, wz)
                return
        if self._sel_press is not None:          # тянем рамку — рисуем на лету
            x0, z0 = self._sel_press
            self.set_region(x0, z0, wx, wz)
            return
        super().mouseMoveEvent(ev)

    def mousePressEvent(self, ev):
        # ПКМ панорамирует ВСЕГДА, в любом режиме: навигацию терять нельзя
        if ev.button() == Qt.MouseButton.RightButton:
            self._pan_press = ev.position().toPoint()
            ev.accept()
            return
        if ev.button() == Qt.MouseButton.LeftButton:
            self._press_pos = ev.position().toPoint()
            if self._brush_mode and self._tool != "brush":
                self._shape_press(self.mapToScene(ev.position().toPoint()))
                return
            if self._brush_mode:
                self._painting = True
                wx, wz = self._scene_to_world(
                    self.mapToScene(ev.position().toPoint()))
                self.stroke_started.emit()       # чтобы линия не тянулась с прошлого места
                self.paint_world.emit(wx, wz)    # клик без движения — тоже мазок
                return
            if self._select_mode:
                self._sel_press = self._scene_to_world(
                    self.mapToScene(ev.position().toPoint()))
                return                           # пан не начинаем
            self._lpan_last = ev.position().toPoint()   # обычный режим: ЛКМ панорамирует
            return
        super().mousePressEvent(ev)

    def _lod(self) -> float:
        return self.transform().m11()

    def _shape_press(self, sp):
        """ЛКМ в режиме фигур: ручка → тянем её; внутри → двигаем фигуру; иначе — новая."""
        s = self._shape
        if s and not s.building:
            i = s.handle_at(sp, self._lod())
            if i >= 0:
                self._drag_handle = i
                return
            if s.contains_point(sp):
                self._drag_from = sp
                return
        if self._tool == "polygon":
            if s and s.building:
                # клик в первую вершину замыкает контур; иначе — очередная вершина
                first = s.points[0]
                grab = GRAB_PX / max(self._lod(), 1e-6)
                if (len(s.points) >= 3 and abs(sp.x() - first.x()) <= grab
                        and abs(sp.y() - first.y()) <= grab):
                    s.building = False
                    s.cursor = None
                    s.update()
                    self.shape_state.emit(self.has_shape())
                else:
                    s.add_point(sp)
                return
            s = self._new_shape("polygon", [sp])
            s.building = True
            return
        if self._tool == "lasso":
            s = self._new_shape("polygon", [sp])
            s.building = True
            self._drag_handle = -2               # -2: набираем траекторию свободной рукой
            return
        self._new_shape(self._tool, [sp, sp])    # rect / ellipse: тянем второй угол
        self._drag_handle = 4                    # правый-нижний угол

    def _shape_move(self, sp) -> bool:
        """True — событие съедено (идёт правка контура)."""
        s = self._shape
        if not s:
            return False
        if self._drag_handle == -2:              # лассо: копим точки траектории
            if not s.points or (abs(sp.x() - s.points[-1].x())
                                + abs(sp.y() - s.points[-1].y())) > 2.0 / max(
                                    self._lod(), 1e-6):
                s.add_point(sp)
            return True
        if self._drag_handle >= 0:
            s.move_handle(self._drag_handle, sp)
            return True
        if self._drag_from is not None:
            s.move_by(sp.x() - self._drag_from.x(), sp.y() - self._drag_from.y())
            self._drag_from = sp
            return True
        if s.building and s.kind == "polygon":   # «резиновая» линия к курсору
            s.cursor = sp
            s.update()
        return False

    def _shape_release(self) -> bool:
        s = self._shape
        if not s:
            return False
        if self._drag_handle == -2:              # лассо отпущено — контур замкнулся
            s.building = False
            s.cursor = None
            s.update()
        self._drag_handle = -1
        self._drag_from = None
        self.shape_state.emit(self.has_shape())
        return True

    def _pan_by(self, pos, last):
        """Сдвинуть вьюпорт на разницу pos-last; вернуть pos как новую опору."""
        d = pos - last
        self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - d.x())
        self.verticalScrollBar().setValue(self.verticalScrollBar().value() - d.y())
        return pos

    def mouseReleaseEvent(self, ev):
        """В режиме рамки — выделение; иначе clicked_world, если мышь не уехала (пан)."""
        if ev.button() == Qt.MouseButton.RightButton and self._pan_press is not None:
            self._pan_press = None
            ev.accept()
            return
        if (ev.button() == Qt.MouseButton.LeftButton
                and getattr(self, "_press_pos", None) is not None):
            delta = ev.position().toPoint() - self._press_pos
            self._press_pos = None
            self._lpan_last = None               # ЛКМ-пан обычного режима завершён
            if self._brush_mode and self._tool != "brush":
                self._shape_release()
                return
            if self._painting:                   # мазок закончен -> один шаг истории
                self._painting = False
                self.stroke_finished.emit()
                return
            if self._sel_press is not None:
                self._sel_press = None
                if delta.manhattanLength() <= CLICK_SLOP_PX:
                    self.clear_region()          # клик без протяжки — снять выделение
                    self.region_cleared.emit()
                elif self._sel_world:
                    self.region_selected.emit(*self._sel_world)
                return
            if delta.manhattanLength() <= CLICK_SLOP_PX:
                sp = self.mapToScene(ev.position().toPoint())
                wx, wz = self._scene_to_world(sp)
                self.clicked_world.emit(wx, wz)
        super().mouseReleaseEvent(ev)
