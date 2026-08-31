from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from PIL import ImageFont


class DialogueFontError(ValueError):
    pass


@dataclass(frozen=True)
class DialogueFontRun:
    role: str
    text: str
    font: ImageFont.FreeTypeFont


class DialogueFontRegistry:
    """Resolves the authored locale font and verifies its project copy."""

    def __init__(self, core_root: str | Path, registry_path: str | Path | None = None):
        self.core_root = Path(core_root).resolve()
        self.path = (
            self.core_root / 'DIALOGUE' / 'dialogue_fonts.json'
            if registry_path is None
            else Path(registry_path)
        )
        if not self.path.is_file():
            raise DialogueFontError(f'Missing dialogue font registry: {self.path}')
        data = json.loads(self.path.read_text(encoding='utf-8'))
        if data.get('schema') != 'gds_dialogue_font_registry_v1':
            raise DialogueFontError(
                f"Unsupported dialogue font registry schema: {data.get('schema')}"
            )
        fonts = data.get('fonts')
        if not isinstance(fonts, dict) or not fonts:
            raise DialogueFontError('Dialogue font registry has no fonts')
        self.data = data
        self.fonts = {self._locale_key(locale): record for locale, record in fonts.items()}
        self.default_locale = self._locale_key(str(data.get('default_locale', 'en')))
        self.default_font_size_px = int(data.get('default_font_size_px', 9))
        self._font_cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}
        self._verified_paths: set[Path] = set()

    @staticmethod
    def _locale_key(value: str) -> str:
        normalized = value.strip().casefold().replace('_', '-')
        if not normalized:
            raise DialogueFontError('Dialogue locale cannot be empty')
        return normalized.split('-', 1)[0]

    @classmethod
    def normalize_locale(cls, value: str) -> str:
        return cls._locale_key(value)

    def _record(self, locale: str | None) -> tuple[str, dict]:
        locale_key = self._locale_key(locale or self.default_locale)
        record = self.fonts.get(locale_key)
        if record is None:
            raise DialogueFontError(f'No dialogue font registered for locale: {locale_key}')
        return locale_key, record

    def resolve_path(self, locale: str | None = None) -> Path:
        _locale, record = self._record(locale)
        path = (self.core_root / str(record['path'])).resolve()
        if not path.is_relative_to(self.core_root):
            raise DialogueFontError('Dialogue font path escapes the character root')
        if not path.is_file():
            raise DialogueFontError(f'Missing dialogue font: {path}')
        return path

    def metadata(self, locale: str | None = None) -> dict:
        _locale, record = self._record(locale)
        return dict(record)

    def get(self, locale: str | None = None, *, size_px: int | None = None) -> ImageFont.FreeTypeFont:
        locale_key, record = self._record(locale)
        size = self.default_font_size_px if size_px is None else int(size_px)
        if size < 1:
            raise DialogueFontError('Dialogue font size must be >= 1')
        key = (locale_key, size)
        cached = self._font_cache.get(key)
        if cached is not None:
            return cached

        path = self.resolve_path(locale_key)
        if path not in self._verified_paths:
            expected = str(record.get('sha256', '')).casefold()
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if expected and actual != expected:
                raise DialogueFontError(f'Dialogue font hash mismatch: {locale_key}')
            self._verified_paths.add(path)
        try:
            font = ImageFont.truetype(str(path), size)
        except OSError as exc:
            raise DialogueFontError(f'Cannot load dialogue font: {path}') from exc
        self._font_cache[key] = font
        return font

    def get_runs(
        self,
        text: str,
        locale: str | None = None,
        *,
        size_px: int | None = None,
    ) -> tuple[DialogueFontRun, ...]:
        """Resolve one line into locale runs plus the approved ASCII fallback."""
        locale_key, _record = self._record(locale)
        primary = self.get(locale_key, size_px=size_px)
        if locale_key != 'th':
            return (DialogueFontRun(locale_key, text, primary),)

        ascii_font = self.get('en', size_px=size_px)
        runs: list[DialogueFontRun] = []
        for character in text:
            role = 'ascii_fallback' if character.isascii() else 'th'
            if runs and runs[-1].role == role:
                previous = runs[-1]
                runs[-1] = DialogueFontRun(
                    previous.role,
                    previous.text + character,
                    previous.font,
                )
            else:
                runs.append(
                    DialogueFontRun(
                        role,
                        character,
                        ascii_font if role == 'ascii_fallback' else primary,
                    )
                )
        return tuple(runs)
