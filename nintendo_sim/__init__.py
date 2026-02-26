"""Nintendo Entertainment System emulator package."""

from .nes import NES
from .rom import Cartridge, load_ines

__all__ = ["NES", "Cartridge", "load_ines"]

