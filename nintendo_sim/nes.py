from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .bus import Bus
from .controller import (
    BUTTON_A,
    BUTTON_B,
    BUTTON_DOWN,
    BUTTON_LEFT,
    BUTTON_RIGHT,
    BUTTON_SELECT,
    BUTTON_START,
    BUTTON_UP,
)
from .rom import Cartridge, load_ines


@dataclass
class NES:
    cartridge: Cartridge
    ppu_backend: str = "auto"

    def __post_init__(self) -> None:
        self.bus = Bus(self.cartridge, ppu_backend=self.ppu_backend)
        self.ppu_backend = self.bus.ppu_backend
        self.bus.reset()

    @classmethod
    def from_rom(cls, rom_path: str | Path, ppu_backend: str = "auto") -> "NES":
        return cls(load_ines(rom_path), ppu_backend=ppu_backend)

    def reset(self) -> None:
        self.bus.reset()

    def step_instruction(self) -> int:
        return self.bus.step()

    def step_frame(self, max_cpu_instructions: int = 1000000, copy_frame: bool = True) -> bytes | bytearray:
        ppu = self.bus.ppu
        step = self.bus.step
        ppu.frame_complete = False
        executed = 0
        while not ppu.frame_complete:
            step()
            executed += 1
            if executed >= max_cpu_instructions:
                raise RuntimeError("Frame execution exceeded instruction limit")
        ppu.frame_complete = False
        if copy_frame:
            return bytes(ppu.frame_rgb)
        return ppu.frame_rgb

    def run_frames(self, count: int) -> None:
        for _ in range(count):
            self.step_frame(copy_frame=False)

    def set_button(self, button: int, pressed: bool, controller: int = 1) -> None:
        target = self.bus.controller1 if controller == 1 else self.bus.controller2
        target.set_button(button, pressed)

    def set_buttons_from_keys(self, keys: dict[str, bool], controller: int = 1) -> None:
        target = self.bus.controller1 if controller == 1 else self.bus.controller2
        target.set_button(BUTTON_A, keys.get("a", False))
        target.set_button(BUTTON_B, keys.get("b", False))
        target.set_button(BUTTON_SELECT, keys.get("select", False))
        target.set_button(BUTTON_START, keys.get("start", False))
        target.set_button(BUTTON_UP, keys.get("up", False))
        target.set_button(BUTTON_DOWN, keys.get("down", False))
        target.set_button(BUTTON_LEFT, keys.get("left", False))
        target.set_button(BUTTON_RIGHT, keys.get("right", False))
