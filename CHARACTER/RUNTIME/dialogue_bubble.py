from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from math import ceil
from pathlib import Path

from PIL import Image, ImageDraw

from .character_assets import CharacterAssetResolutionError
from .dialogue_font import DialogueFontError, DialogueFontRegistry, DialogueFontRun
from .frame_renderer import CharacterFrameRenderer
from .frame_rules import FrameRuleError, resolve_frame_rule


class DialogueBubbleError(ValueError):
    pass


@dataclass(frozen=True)
class TextMetrics:
    text: str
    locale: str
    font_size_px: int
    advance_width_raw_px: float
    advance_width_px: int
    ink_height_px: int
    font_bbox: tuple[int, int, int, int]
    runs: tuple[tuple[str, str, float, tuple[int, int, int, int]], ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            'text': self.text,
            'locale': self.locale,
            'font_size_px': self.font_size_px,
            'advance_width_raw_px': self.advance_width_raw_px,
            'advance_width_px': self.advance_width_px,
            'ink_height_px': self.ink_height_px,
            'font_bbox': list(self.font_bbox),
            'runs': [
                {
                    'role': role,
                    'text': text,
                    'advance_width_raw_px': advance,
                    'bbox_at_baseline': list(bbox),
                }
                for role, text, advance, bbox in self.runs
            ],
        }


@dataclass(frozen=True)
class BubblePreset:
    bubble_id: str
    name: str
    crop_box: tuple[int, int, int, int]
    image: Image.Image
    tail_tip_local_px: tuple[int, int] | None
    tail_start_y: int
    safe_rect: tuple[int, int, int, int]
    excluded: bool = False

    @property
    def width(self) -> int:
        return self.image.width

    @property
    def height(self) -> int:
        return self.image.height

    @property
    def size_px(self) -> tuple[int, int]:
        return self.image.size


@dataclass(frozen=True)
class BubbleLayout:
    bubble_id: str
    text: str
    locale: str
    font_size_px: int
    text_width_px: int
    ink_height_px: int
    safe_rect: tuple[int, int, int, int]
    text_bbox: tuple[int, int, int, int]
    text_origin: tuple[int, int]
    fit: bool

    def as_dict(self) -> dict[str, object]:
        return {
            'bubble_id': self.bubble_id,
            'text': self.text,
            'locale': self.locale,
            'font_size_px': self.font_size_px,
            'text_width_px': self.text_width_px,
            'ink_height_px': self.ink_height_px,
            'safe_rect': list(self.safe_rect),
            'text_bbox': list(self.text_bbox),
            'text_origin': list(self.text_origin),
            'fit': self.fit,
        }


@dataclass(frozen=True)
class BubbleSelection:
    preset: BubblePreset
    layout: BubbleLayout
    attempts: tuple[BubbleLayout, ...]

    @property
    def bubble_id(self) -> str:
        return self.preset.bubble_id

    @property
    def image(self) -> Image.Image:
        return self.preset.image


@dataclass(frozen=True)
class DialogueBubbleRenderResult:
    bubble_id: str
    text: str
    image: Image.Image
    layout: BubbleLayout
    bubble_top_left: tuple[int, int]
    bubble_tail_global: tuple[int, int]
    head_anchor: tuple[int, int]
    actor_top_left: tuple[int, int] | None = None
    frame_id: str | None = None
    frame_bob_y: int = 0

    @property
    def bubble_size(self) -> tuple[int, int]:
        return self.image.size

    @property
    def text_layout(self) -> dict[str, object]:
        return self.layout.as_dict()


class DialogueBubbleRenderer:
    """Fixed whole-crop fukidashi_base renderer for one-line dialogue.

    The current implementation deliberately owns presentation only. It does not
    choose a conversation partner, reserve a path, or mutate actor state.
    """

    ASSET_ID = 'dialogue.fukidashi_base'

    def __init__(self, core_root: str | Path):
        self.core_root = Path(core_root).resolve()
        registry_path = self.core_root / 'DIALOGUE' / 'bubble_presets.json'
        if not registry_path.is_file():
            raise DialogueBubbleError(f'Missing dialogue bubble registry: {registry_path}')
        data = json.loads(registry_path.read_text(encoding='utf-8'))
        if data.get('schema') != 'gds_dialogue_bubble_registry_v1':
            raise DialogueBubbleError(
                f"Unsupported dialogue bubble registry schema: {data.get('schema')}"
            )
        self.data = data
        self.image_path = self._resolve_relative(str(data['source_asset']['path']))
        self.source_image = self._load_source_image()
        self.fonts = DialogueFontRegistry(
            self.core_root,
            self._resolve_relative(str(data['text_layout']['font_registry'])),
        )
        self.text_layout_config = dict(data['text_layout'])
        self._presets = self._load_presets(data)
        self.allowed_bubble_ids = tuple(data['allowed_bubble_ids'])
        self.excluded_bubble_ids = tuple(data['excluded_bubble_ids'])
        self.selection_order = list(data['selection']['order'])
        self._validate_selection_policy()
        self._frame_renderer = CharacterFrameRenderer(self.core_root)

    def _resolve_relative(self, relative: str) -> Path:
        path = (self.core_root / relative).resolve()
        if not path.is_relative_to(self.core_root):
            raise DialogueBubbleError(f'Dialogue path escapes the character root: {relative}')
        return path

    def _load_source_image(self) -> Image.Image:
        if not self.image_path.is_file():
            raise DialogueBubbleError(f'Missing dialogue bubble asset: {self.image_path}')
        expected = str(self.data['source_asset']['sha256']).casefold()
        actual = hashlib.sha256(self.image_path.read_bytes()).hexdigest()
        if actual != expected:
            raise DialogueBubbleError('Dialogue bubble asset hash mismatch')
        with Image.open(self.image_path) as image:
            result = image.convert('RGBA')
        expected_size = tuple(self.data['source_asset']['dimensions_px'])
        if result.size != expected_size:
            raise DialogueBubbleError(
                f'Dialogue bubble asset must be {expected_size}, got {result.size}'
            )
        return result

    def _load_presets(self, data: dict) -> dict[str, BubblePreset]:
        presets: dict[str, BubblePreset] = {}
        for record in data.get('presets', []):
            bubble_id = str(record['bubble_id'])
            if bubble_id in presets:
                raise DialogueBubbleError(f'Duplicate dialogue bubble: {bubble_id}')
            x, y, width, height = (int(value) for value in record['crop_box'])
            if x < 0 or y < 0 or width < 1 or height < 1:
                raise DialogueBubbleError(f'Invalid crop box for {bubble_id}')
            if x + width > self.source_image.width or y + height > self.source_image.height:
                raise DialogueBubbleError(f'Crop box escapes source asset for {bubble_id}')
            image = self.source_image.crop((x, y, x + width, y + height))
            if image.size != tuple(record['size_px']):
                raise DialogueBubbleError(f'Crop size mismatch for {bubble_id}')
            safe_rect = tuple(int(value) for value in record['safe_rect'])
            x0, y0, x1, y1 = safe_rect
            if not (0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height):
                raise DialogueBubbleError(f'Invalid safe_rect for {bubble_id}')
            tail = record.get('tail_tip_local_px')
            tail_tuple = None if tail is None else (int(tail[0]), int(tail[1]))
            if tail_tuple is not None and not (
                0 <= tail_tuple[0] < width and 0 <= tail_tuple[1] < height
            ):
                raise DialogueBubbleError(f'Invalid tail tip for {bubble_id}')
            presets[bubble_id] = BubblePreset(
                bubble_id=bubble_id,
                name=str(record['name']),
                crop_box=(x, y, width, height),
                image=image,
                tail_tip_local_px=tail_tuple,
                tail_start_y=int(record['tail_start_y']),
                safe_rect=safe_rect,
                excluded=bool(record.get('excluded', False)),
            )
        return presets

    def _validate_selection_policy(self) -> None:
        if len(self.allowed_bubble_ids) != len(set(self.allowed_bubble_ids)):
            raise DialogueBubbleError('Duplicate allowed dialogue bubble ID')
        if len(self.excluded_bubble_ids) != len(set(self.excluded_bubble_ids)):
            raise DialogueBubbleError('Duplicate excluded dialogue bubble ID')
        if len(self.selection_order) != len(set(self.selection_order)):
            raise DialogueBubbleError('Duplicate dialogue bubble selection ID')
        if set(self.allowed_bubble_ids) & set(self.excluded_bubble_ids):
            raise DialogueBubbleError('Allowed and excluded bubble IDs overlap')
        if set(self.allowed_bubble_ids) | set(self.excluded_bubble_ids) != set(self._presets):
            raise DialogueBubbleError('Bubble registry IDs do not match allowed/excluded IDs')
        if set(self.selection_order) != set(self.allowed_bubble_ids):
            raise DialogueBubbleError('Bubble selection order does not match allowed IDs')
        for bubble_id in self.allowed_bubble_ids:
            if self._presets[bubble_id].excluded:
                raise DialogueBubbleError(f'Allowed bubble is marked excluded: {bubble_id}')
        for bubble_id in self.excluded_bubble_ids:
            if not self._presets[bubble_id].excluded:
                raise DialogueBubbleError(f'Excluded bubble is not marked excluded: {bubble_id}')

    def list_bubbles(self) -> list[str]:
        return list(self.allowed_bubble_ids)

    def get_bubble(self, bubble_id: str) -> BubblePreset:
        try:
            preset = self._presets[str(bubble_id)]
        except KeyError as exc:
            raise DialogueBubbleError(f'Unknown dialogue bubble: {bubble_id}') from exc
        if preset.excluded:
            raise DialogueBubbleError(f'Dialogue bubble {bubble_id} is excluded from the active scope')
        return preset

    def resolve_asset_path(self, asset_id: str) -> Path:
        normalized = str(asset_id).strip()
        if normalized == self.ASSET_ID:
            return self.image_path
        if normalized == 'dialogue.font.en':
            return self.fonts.resolve_path('en')
        if normalized == 'dialogue.font.th':
            return self.fonts.resolve_path('th')
        raise DialogueBubbleError(f'Unknown dialogue asset: {asset_id}')

    @staticmethod
    def _validate_text(text: str) -> str:
        if not isinstance(text, str):
            raise DialogueBubbleError('Dialogue text must be a string')
        if not text:
            raise DialogueBubbleError('Dialogue text cannot be empty')
        if '\n' in text or '\r' in text:
            raise DialogueBubbleError('Dialogue text must be one line; wrapping is disabled')
        return text

    def measure_text(
        self,
        text: str,
        *,
        locale: str = 'en',
        font_size_px: int | None = None,
    ) -> TextMetrics:
        text = self._validate_text(text)
        try:
            runs = self.fonts.get_runs(text, locale, size_px=font_size_px)
        except DialogueFontError as exc:
            raise DialogueBubbleError(str(exc)) from exc
        run_records: list[tuple[str, str, float, tuple[int, int, int, int]]] = []
        advance_raw = 0.0
        min_top: int | None = None
        max_bottom: int | None = None
        for run in runs:
            advance = float(run.font.getlength(run.text))
            bbox = tuple(int(value) for value in run.font.getbbox(run.text, anchor='ls'))
            advance_raw += advance
            min_top = bbox[1] if min_top is None else min(min_top, bbox[1])
            max_bottom = bbox[3] if max_bottom is None else max(max_bottom, bbox[3])
            run_records.append((run.role, run.text, advance, bbox))
        if min_top is None or max_bottom is None:
            raise DialogueBubbleError('Dialogue text produced no font runs')
        bbox = (0, min_top, int(ceil(advance_raw)), max_bottom)
        return TextMetrics(
            text=text,
            locale=self.fonts.normalize_locale(locale),
            font_size_px=int(runs[0].font.size),
            advance_width_raw_px=advance_raw,
            advance_width_px=int(ceil(advance_raw)),
            ink_height_px=int(max_bottom - min_top),
            font_bbox=bbox,
            runs=tuple(run_records),
        )

    def _layout(
        self,
        preset: BubblePreset,
        text: str,
        metrics: TextMetrics,
        runs: tuple[DialogueFontRun, ...],
    ) -> BubbleLayout:
        x0, y0, x1, y1 = preset.safe_rect
        tail_x = (
            preset.tail_tip_local_px[0]
            if preset.tail_tip_local_px is not None
            else preset.width // 2
        )
        x = round(tail_x - metrics.advance_width_px / 2)
        y_top = y0 + max(0, ((y1 - y0) - metrics.ink_height_px) // 2)
        baseline_y = y_top - metrics.font_bbox[1]
        boxes: list[tuple[int, int, int, int]] = []
        cursor = float(x)
        for run in runs:
            run_x = int(round(cursor))
            bbox = run.font.getbbox(run.text, anchor='ls')
            boxes.append((
                run_x + int(bbox[0]),
                baseline_y + int(bbox[1]),
                run_x + int(bbox[2]),
                baseline_y + int(bbox[3]),
            ))
            cursor += run.font.getlength(run.text)
        drawn_bbox = (
            min(box[0] for box in boxes),
            min(box[1] for box in boxes),
            max(box[2] for box in boxes),
            max(box[3] for box in boxes),
        )
        fit = (
            drawn_bbox[0] >= x0
            and drawn_bbox[1] >= y0
            and drawn_bbox[2] <= x1
            and drawn_bbox[3] <= y1
        )
        return BubbleLayout(
            bubble_id=preset.bubble_id,
            text=text,
            locale=metrics.locale,
            font_size_px=metrics.font_size_px,
            text_width_px=metrics.advance_width_px,
            ink_height_px=metrics.ink_height_px,
            safe_rect=preset.safe_rect,
            text_bbox=drawn_bbox,
            text_origin=(x, baseline_y),
            fit=fit,
        )

    def select_bubble(
        self,
        text: str,
        *,
        locale: str = 'en',
        font_size_px: int | None = None,
        preferred_bubble_id: str | None = None,
    ) -> BubbleSelection:
        text = self._validate_text(text)
        metrics = self.measure_text(text, locale=locale, font_size_px=font_size_px)
        try:
            runs = self.fonts.get_runs(text, locale, size_px=metrics.font_size_px)
        except DialogueFontError as exc:
            raise DialogueBubbleError(str(exc)) from exc
        attempts: list[BubbleLayout] = []
        # ``preferred_bubble_id`` is a compatibility/presentation hint from
        # the scheduler.  Bubble shape is never randomized or forced by that
        # hint: the registry order remains the authoritative smallest-fitting
        # rule, so BB1/BB2/BB3/BB4/BB6 are selected solely from rendered text.
        if preferred_bubble_id is not None and str(preferred_bubble_id) not in self.allowed_bubble_ids:
            raise DialogueBubbleError(
                f'Unknown or excluded preferred dialogue bubble: {preferred_bubble_id}'
            )
        order = list(self.selection_order)
        for bubble_id in order:
            preset = self.get_bubble(bubble_id)
            layout = self._layout(preset, text, metrics, runs)
            attempts.append(layout)
            if layout.fit:
                return BubbleSelection(preset, layout, tuple(attempts))
        # The authored office catalogue contains longer lines than the
        # original 9px review copy.  Keep the no-wrap/no-overflow contract by
        # stepping the font down only when the caller did not explicitly pin
        # a size.  Extremely long text (for example a 100-character probe)
        # still fails instead of being clipped.
        if font_size_px is None:
            # A few of the author-approved office lines are long even for
            # BB1.  Step down to the smallest readable development size so
            # every enabled catalog row remains renderable without wrapping
            # or clipping.  Explicit font sizes still remain strict.
            for fallback_size in (8, 7, 6, 5, 4):
                try:
                    fallback_metrics = self.measure_text(
                        text, locale=locale, font_size_px=fallback_size
                    )
                    fallback_runs = self.fonts.get_runs(
                        text, locale, size_px=fallback_metrics.font_size_px
                    )
                except DialogueFontError as exc:
                    raise DialogueBubbleError(str(exc)) from exc
                for bubble_id in order:
                    preset = self.get_bubble(bubble_id)
                    layout = self._layout(
                        preset, text, fallback_metrics, fallback_runs
                    )
                    attempts.append(layout)
                    if layout.fit:
                        return BubbleSelection(preset, layout, tuple(attempts))
        raise DialogueBubbleError(
            f'Dialogue text {text!r} cannot fit any allowed bubble at font size '
            f'{metrics.font_size_px}px (maximum safe width is {max(self._presets[i].safe_rect[2] - self._presets[i].safe_rect[0] for i in self.allowed_bubble_ids)}px)'
        )

    def _draw_selection(
        self,
        selection: BubbleSelection,
        runs: tuple[DialogueFontRun, ...],
    ) -> Image.Image:
        output = selection.preset.image.copy()
        draw = ImageDraw.Draw(output)
        cursor = float(selection.layout.text_origin[0])
        baseline_y = selection.layout.text_origin[1]
        for run in runs:
            run_x = int(round(cursor))
            draw.text(
                (run_x, baseline_y),
                run.text,
                font=run.font,
                anchor='ls',
                fill=tuple(self.text_layout_config['text_color_rgba']),
            )
            cursor += run.font.getlength(run.text)
        return output

    def render_bubble(
        self,
        text: str,
        *,
        head_anchor: tuple[int, int] = (0, 0),
        actor_top_left: tuple[int, int] | None = None,
        frame_id: str | None = None,
        frame_bob_y: int = 0,
        locale: str = 'en',
        font_size_px: int | None = None,
        preferred_bubble_id: str | None = None,
    ) -> DialogueBubbleRenderResult:
        selection = self.select_bubble(
            text,
            locale=locale,
            font_size_px=font_size_px,
            preferred_bubble_id=preferred_bubble_id,
        )
        try:
            runs = self.fonts.get_runs(
                text,
                locale,
                size_px=selection.layout.font_size_px,
            )
        except DialogueFontError as exc:
            raise DialogueBubbleError(str(exc)) from exc
        output = self._draw_selection(selection, runs)
        anchor_x, anchor_y = (int(head_anchor[0]), int(head_anchor[1]))
        tail = selection.preset.tail_tip_local_px
        tail_x, tail_y = tail if tail is not None else (selection.preset.width // 2, selection.preset.height - 1)
        vertical_offset = int(self.text_layout_config['vertical_offset_from_actor_frame_top_px'])
        bubble_top_left = (anchor_x - tail_x, anchor_y + vertical_offset)
        bubble_tail_global = (bubble_top_left[0] + tail_x, bubble_top_left[1] + tail_y)
        return DialogueBubbleRenderResult(
            bubble_id=selection.bubble_id,
            text=text,
            image=output,
            layout=selection.layout,
            bubble_top_left=bubble_top_left,
            bubble_tail_global=bubble_tail_global,
            head_anchor=(anchor_x, anchor_y),
            actor_top_left=actor_top_left,
            frame_id=frame_id,
            frame_bob_y=int(frame_bob_y),
        )

    def _frame_bob_y(self, frame_id: str, seen: set[str] | None = None) -> int:
        seen = set() if seen is None else seen
        if frame_id in seen:
            raise DialogueBubbleError(f'Frame registry cycle at {frame_id}')
        seen.add(frame_id)
        try:
            rule = resolve_frame_rule(self._frame_renderer.frame_registry, frame_id)
        except FrameRuleError as exc:
            raise DialogueBubbleError(str(exc)) from exc
        if rule.get('kind') == 'derived':
            source = rule.get('source_frame_id')
            if not isinstance(source, str):
                raise DialogueBubbleError(f'Derived frame has no source: {frame_id}')
            return self._frame_bob_y(source, seen)
        split = rule.get('split_body')
        return int(split.get('shift_y', 0)) if isinstance(split, dict) else 0

    def _frame_head_anchor_x(self, character_id: str, frame_id: str, seen: set[str] | None = None) -> int:
        seen = set() if seen is None else seen
        if frame_id in seen:
            raise DialogueBubbleError(f'Frame registry cycle at {frame_id}')
        seen.add(frame_id)
        try:
            rule = resolve_frame_rule(self._frame_renderer.frame_registry, frame_id)
        except FrameRuleError as exc:
            raise DialogueBubbleError(str(exc)) from exc
        if rule.get('kind') == 'derived':
            source = rule.get('source_frame_id')
            if not isinstance(source, str):
                raise DialogueBubbleError(f'Derived frame has no source: {frame_id}')
            source_anchor = self._frame_head_anchor_x(character_id, source, seen)
            return int(self._frame_renderer.canvas[0] - 1 - source_anchor)

        try:
            resolved = self._frame_renderer.assets.resolve(character_id)
            face = self._frame_renderer._load_rgba(resolved['face'])
        except CharacterAssetResolutionError as exc:
            raise DialogueBubbleError(str(exc)) from exc
        sx, sy, width, height = rule['face']['src']
        crop = face.crop((sx, sy, sx + width, sy + height))
        bbox = crop.getchannel('A').getbbox()
        if bbox is None:
            raise DialogueBubbleError(f'Frame face has no visible alpha: {frame_id}')
        dx = self._frame_renderer.origin[0] + rule['face']['dst'][0]
        left = dx + bbox[0]
        right = dx + bbox[2] - 1
        return int((left + right + 1) // 2)

    def render_for_character(
        self,
        character_id: str,
        frame_id: str,
        text: str,
        *,
        actor_top_left: tuple[int, int] = (0, 0),
        locale: str = 'en',
        font_size_px: int | None = None,
        preferred_bubble_id: str | None = None,
    ) -> DialogueBubbleRenderResult:
        actor_x, actor_y = (int(actor_top_left[0]), int(actor_top_left[1]))
        anchor_x = actor_x + self._frame_head_anchor_x(character_id, frame_id)
        bob_y = self._frame_bob_y(frame_id)
        return self.render_bubble(
            text,
            head_anchor=(anchor_x, actor_y + bob_y),
            actor_top_left=(actor_x, actor_y),
            frame_id=frame_id,
            frame_bob_y=bob_y,
            locale=locale,
            font_size_px=font_size_px,
            preferred_bubble_id=preferred_bubble_id,
        )
