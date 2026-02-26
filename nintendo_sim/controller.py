from __future__ import annotations

from dataclasses import dataclass


BUTTON_A = 0
BUTTON_B = 1
BUTTON_SELECT = 2
BUTTON_START = 3
BUTTON_UP = 4
BUTTON_DOWN = 5
BUTTON_LEFT = 6
BUTTON_RIGHT = 7


@dataclass
class Controller:
    state: int = 0
    shift_register: int = 0
    strobe: bool = False

    def set_button(self, button: int, pressed: bool) -> None:
        if pressed:
            self.state |= 1 << button
        else:
            self.state &= ~(1 << button)
        self.state &= 0xFF

    def write(self, value: int) -> None:
        self.strobe = bool(value & 1)
        if self.strobe:
            self.shift_register = self.state

    def read(self) -> int:
        if self.strobe:
            return self.state & 1
        result = self.shift_register & 1
        self.shift_register = ((self.shift_register >> 1) | 0x80) & 0xFF
        return result

