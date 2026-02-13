# ASCII 3-Layer Duel Arena

A two-player local keyboard 1v1 ASCII shooter with simulated vertical gameplay layers.

## Run

```bash
python3 game.py
```

## Highlights

- Top-down arena with **3 vertical levels**: crouch, normal, jump.
- Players can move, jump, crouch, dash, and shoot.
- Projectiles only collide with opponents on the **same vertical level**.
- Dash and shooting cooldowns shown in HUD.
- One-hit elimination (with optional shield save).
- Time-based powerups:
  - `S` Shotgun (3-shot spread)
  - `D` Dash Boost (reduced dash cooldown)
  - `H` Shield (absorbs one bullet)
- Main menu with game info and control reference.

## Controls

- **P1**: `W A S D` move, `R` jump, `F` crouch, `V` reset level to normal, `G` dash, `T` shoot
- **P2**: `I J K L` move, `U` jump, `O` crouch, `M` reset level to normal, `P` dash, `Y` shoot
- `ESC` returns to menu during match.
