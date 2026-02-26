#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from nintendo_sim.controller import (
    BUTTON_A,
    BUTTON_B,
    BUTTON_DOWN,
    BUTTON_LEFT,
    BUTTON_RIGHT,
    BUTTON_SELECT,
    BUTTON_START,
    BUTTON_UP,
)
from nintendo_sim.nes import NES


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run NES ROMs")
    parser.add_argument("rom", type=Path, help="Path to .nes ROM")
    parser.add_argument("--headless-frames", type=int, default=0, help="Run headless for N frames and exit")
    parser.add_argument("--scale", type=int, default=3, help="Window scale for interactive mode")
    return parser.parse_args()


def _headless(nes: NES, frames: int) -> int:
    nes.run_frames(frames)
    return 0


def _interactive(nes: NES, scale: int) -> int:
    try:
        import pygame
    except ImportError as exc:
        print("pygame is required for interactive mode. Install dependencies first.", file=sys.stderr)
        print(f"Import error: {exc}", file=sys.stderr)
        return 1

    pygame.init()
    try:
        window = pygame.display.set_mode((256 * scale, 240 * scale))
        pygame.display.set_caption("Nintendo Sim")
        clock = pygame.time.Clock()
        target_size = window.get_size()
        frame_buffer = nes.bus.ppu.frame_rgb
        frame_surface = pygame.image.frombuffer(frame_buffer, (256, 240), "RGB")
        scaled_surface = pygame.transform.scale(frame_surface, target_size) if scale != 1 else None
        running = True
        tap_latch_frames = 2
        key_to_button = {
            pygame.K_z: BUTTON_A,
            pygame.K_k: BUTTON_A,
            pygame.K_x: BUTTON_B,
            pygame.K_j: BUTTON_B,
            pygame.K_RSHIFT: BUTTON_SELECT,
            pygame.K_LSHIFT: BUTTON_SELECT,
            pygame.K_TAB: BUTTON_SELECT,
            pygame.K_RETURN: BUTTON_START,
            pygame.K_KP_ENTER: BUTTON_START,
            pygame.K_SPACE: BUTTON_START,
            pygame.K_UP: BUTTON_UP,
            pygame.K_w: BUTTON_UP,
            pygame.K_DOWN: BUTTON_DOWN,
            pygame.K_s: BUTTON_DOWN,
            pygame.K_LEFT: BUTTON_LEFT,
            pygame.K_a: BUTTON_LEFT,
            pygame.K_RIGHT: BUTTON_RIGHT,
            pygame.K_d: BUTTON_RIGHT,
        }
        button_to_keys = {}
        for key, button in key_to_button.items():
            button_to_keys.setdefault(button, []).append(key)
        manual_key_state: dict[int, bool] = {}
        pulse_frames = {
            BUTTON_A: 0,
            BUTTON_B: 0,
            BUTTON_SELECT: 0,
            BUTTON_START: 0,
            BUTTON_UP: 0,
            BUTTON_DOWN: 0,
            BUTTON_LEFT: 0,
            BUTTON_RIGHT: 0,
        }

        def apply_keyboard_state() -> None:
            keys = pygame.key.get_pressed()
            for button, key_list in button_to_keys.items():
                realtime_pressed = any(keys[k] or manual_key_state.get(k, False) for k in key_list)
                pressed = realtime_pressed or (pulse_frames[button] > 0)
                nes.set_button(button, pressed)
                if pulse_frames[button] > 0:
                    pulse_frames[button] -= 1

        def pump_events() -> None:
            nonlocal running
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    manual_key_state[event.key] = True
                    button = key_to_button.get(event.key)
                    if button is not None:
                        pulse_frames[button] = max(pulse_frames[button], tap_latch_frames)
                elif event.type == pygame.KEYUP:
                    manual_key_state[event.key] = False
                elif event.type == pygame.WINDOWFOCUSLOST:
                    manual_key_state.clear()
                    for button in (
                        BUTTON_A,
                        BUTTON_B,
                        BUTTON_SELECT,
                        BUTTON_START,
                        BUTTON_UP,
                        BUTTON_DOWN,
                        BUTTON_LEFT,
                        BUTTON_RIGHT,
                    ):
                        pulse_frames[button] = 0
                        nes.set_button(button, False)

        step_instruction = nes.bus.step
        ppu = nes.bus.ppu

        while running:
            pump_events()
            apply_keyboard_state()

            ppu.frame_complete = False
            executed = 0
            while running and not ppu.frame_complete:
                step_instruction()
                executed += 1
                # Keep input responsive even when emulation is running < 60 FPS.
                if (executed & 0x1FF) == 0:
                    pump_events()
                    apply_keyboard_state()
                if executed >= 1_000_000:
                    raise RuntimeError("Frame execution exceeded instruction limit")
            ppu.frame_complete = False

            if scale == 1:
                window.blit(frame_surface, (0, 0))
            else:
                pygame.transform.scale(frame_surface, target_size, scaled_surface)
                window.blit(scaled_surface, (0, 0))
            pygame.display.flip()
            clock.tick(60)
    finally:
        pygame.quit()
    return 0


def main() -> int:
    args = _parse_args()
    nes = NES.from_rom(args.rom)
    if args.headless_frames > 0:
        return _headless(nes, args.headless_frames)
    return _interactive(nes, args.scale)


if __name__ == "__main__":
    raise SystemExit(main())
