# ASCII 3-Layer Duel Arena

A two-player local keyboard 1v1 ASCII shooter with simulated vertical gameplay layers.

## Run

```bash
python3 game.py
```

No external dependencies are required.

## Highlights

- Top-down arena with **2 vertical levels** now: normal and jump.
- Main menu modes:
  - **1v1 Local**
  - **Versus Bot** (simple random-move AI)
- After selecting a mode, pick one arena size:
  - **Small** (`30x10`)
  - **Medium** (`44x14`)
  - **Large** (`70x24`)
- Shooting cooldown is **0.1s**.
- Hold shoot to charge; release fires larger projectiles.
- Movement is disabled while charging, but you can still re-aim while charging.
- Facing indicator arrows (`<`, `>`, `^`, `v`) show player aim direction.
- Dash travels farther and leaves a short-lived trail indicator.
- Timed powerups:
  - `S` Shotgun (temporary 3-shot spread)
  - `D` Dash Boost (temporary low dash cooldown)
  - `H` Shield (absorbs one bullet)
- Scoring system: on a valid hit, scorer gains a point, popup appears, and pressing any key starts the next round while keeping score.

## Controls

- **P1**: `W A S D` move, `E` jump, `R` dash, `Q` shoot/charge
- **P2**: `I J K L` move, `O` jump, `P` dash, `U` shoot/charge
- During match: `ESC` returns to menu.
