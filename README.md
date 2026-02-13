# ASCII 3-Layer Duel Arena

A two-player local keyboard 1v1 ASCII shooter with simulated vertical gameplay layers.

## Run

```bash
python3 game.py
```

No external dependencies are required.

## Highlights

- Top-down arena with **3 vertical levels**: crouch, normal, jump.
- Main menu modes:
  - **1v1 Local**
  - **Versus Bot** (simple random-move AI)
- After selecting a mode, pick one arena size:
  - **Small** (`30x10`)
  - **Medium** (`44x14`)
  - **Large** (`70x24`)
- Jump auto-returns to normal level after a short pause.
- Crouch returns to normal when crouch input is released/not repeated.
- Projectiles are level-specific and only hit targets on the same vertical level.
- Shooting cooldown reduced to **0.1s**.
- Hold shoot to charge; release fires larger projectiles.
- Movement is disabled while charging.
- Dash travels farther and leaves a short-lived trail indicator.
- Timed powerups:
  - `S` Shotgun (temporary 3-shot spread)
  - `D` Dash Boost (temporary low dash cooldown)
  - `H` Shield (absorbs one bullet)
- Scoring system: on a valid hit, scorer gains a point, popup appears, and pressing any key starts the next round while keeping score.

## Controls

- **P1**: `W A S D` move, `E` jump, `Left Shift` crouch, `R` dash, `Q` shoot/charge
- **P2**: `I J K L` move, `O` jump, `H` crouch, `P` dash, `U` shoot/charge
- During match: `ESC` returns to menu.

> Note: standalone `Left Shift` key reporting can vary across terminals/OSes, but dedicated Shift scan-code handling was added for Windows consoles.
