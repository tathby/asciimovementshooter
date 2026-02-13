# ASCII 3-Layer Duel Arena

A two-player local keyboard 1v1 ASCII shooter with simulated vertical gameplay layers.

## Run

```bash
python3 game.py
```

No external dependencies are required.

## Windows compatibility fix

This version does **not** depend on `curses`, so it works on Windows Python installations that do not include `_curses`.

## Highlights

- Top-down arena with **3 vertical levels**: crouch, normal, jump.
- Two players on one keyboard.
- Jump/crouch alter player symbol size to simulate height.
- Projectiles are also level-sized and only hit targets on the same level.
- Dash with cooldown shown in HUD.
- Shooting has a short cooldown to prevent spam.
- One-hit elimination (unless shielded).
- Time-based powerups:
  - `S` Shotgun (temporary 3-shot spread)
  - `D` Dash Boost (temporary low dash cooldown)
  - `H` Shield (absorbs one bullet)
- Main menu with controls and powerup info pages.

## Controls

- **P1**: `W A S D` move, `R` jump, `F` crouch, `V` normal level, `G` dash, `T` shoot
- **P2**: `I J K L` move, `U` jump, `O` crouch, `M` normal level, `P` dash, `Y` shoot
- During match: `Q` or `ESC` returns to menu.
