import os
import random
import sys
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

if os.name == "nt":
    import msvcrt
else:
    import select
    import termios
    import tty

ARENA_WIDTH = 70
ARENA_HEIGHT = 24
FRAME_TIME = 0.05
SHOT_COOLDOWN = 0.22
DASH_COOLDOWN = 2.2
DASH_DISTANCE = 4
PROJECTILE_SPEED = 2
POWERUP_SPAWN_INTERVAL = 8.0
POWERUP_LIFETIME = 14.0
SHOTGUN_DURATION = 10.0
DASH_BOOST_DURATION = 10.0
DASH_BOOST_COOLDOWN = 0.6

LEVEL_CROUCH = 0
LEVEL_NORMAL = 1
LEVEL_JUMP = 2
LEVEL_NAMES = {LEVEL_CROUCH: "CROUCH", LEVEL_NORMAL: "NORMAL", LEVEL_JUMP: "JUMP"}
LEVEL_PLAYER_GLYPHS = {LEVEL_CROUCH: ".", LEVEL_NORMAL: "A", LEVEL_JUMP: "^"}
LEVEL_PLAYER2_GLYPHS = {LEVEL_CROUCH: ",", LEVEL_NORMAL: "B", LEVEL_JUMP: "M"}
LEVEL_PROJECTILE_GLYPHS = {LEVEL_CROUCH: ".", LEVEL_NORMAL: "*", LEVEL_JUMP: "O"}

KEYMAP = {
    "p1": {
        "up": "w",
        "down": "s",
        "left": "a",
        "right": "d",
        "jump": "r",
        "crouch": "f",
        "dash": "g",
        "shoot": "t",
        "normal": "v",
    },
    "p2": {
        "up": "i",
        "down": "k",
        "left": "j",
        "right": "l",
        "jump": "u",
        "crouch": "o",
        "dash": "p",
        "shoot": "y",
        "normal": "m",
    },
}


@dataclass
class Projectile:
    x: int
    y: int
    dx: int
    dy: int
    level: int
    owner: str


@dataclass
class PowerUp:
    x: int
    y: int
    kind: str
    spawned_at: float


@dataclass
class Player:
    pid: str
    name: str
    x: int
    y: int
    level: int = LEVEL_NORMAL
    facing: Tuple[int, int] = (1, 0)
    alive: bool = True
    shield: bool = False
    shotgun_until: float = 0.0
    dash_boost_until: float = 0.0
    last_shot_at: float = -999.0
    last_dash_at: float = -999.0

    def glyph(self) -> str:
        return LEVEL_PLAYER_GLYPHS[self.level] if self.pid == "p1" else LEVEL_PLAYER2_GLYPHS[self.level]

    def dash_cooldown(self, now: float) -> float:
        return DASH_BOOST_COOLDOWN if now < self.dash_boost_until else DASH_COOLDOWN

    def can_shoot(self, now: float) -> bool:
        return now - self.last_shot_at >= SHOT_COOLDOWN

    def can_dash(self, now: float) -> bool:
        return now - self.last_dash_at >= self.dash_cooldown(now)


class Keyboard:
    def __init__(self):
        self._fd = None
        self._old_settings = None

    def __enter__(self):
        if os.name != "nt":
            self._fd = sys.stdin.fileno()
            self._old_settings = termios.tcgetattr(self._fd)
            tty.setcbreak(self._fd)
        return self

    def __exit__(self, exc_type, exc, tb):
        if os.name != "nt" and self._fd is not None and self._old_settings is not None:
            termios.tcsetattr(self._fd, termios.TCSADRAIN, self._old_settings)

    def get_keys(self) -> List[str]:
        keys: List[str] = []
        if os.name == "nt":
            while msvcrt.kbhit():
                c = msvcrt.getwch()
                if c in ("\x00", "\xe0"):
                    if msvcrt.kbhit():
                        msvcrt.getwch()
                    continue
                keys.append(c.lower())
        else:
            while True:
                readable, _, _ = select.select([sys.stdin], [], [], 0)
                if not readable:
                    break
                c = sys.stdin.read(1)
                if c:
                    keys.append(c.lower())
                else:
                    break
        return keys


def clear_screen():
    print("\033[2J\033[H", end="")


class AsciiArenaGame:
    def __init__(self):
        self.players: Dict[str, Player] = {}
        self.projectiles: List[Projectile] = []
        self.powerups: List[PowerUp] = []
        self.last_spawn_at = time.time()
        self.winner: Optional[Player] = None

    def reset_round(self):
        self.players = {
            "p1": Player("p1", "P1", 8, ARENA_HEIGHT // 2, facing=(1, 0)),
            "p2": Player("p2", "P2", ARENA_WIDTH - 9, ARENA_HEIGHT // 2, facing=(-1, 0)),
        }
        self.projectiles = []
        self.powerups = []
        self.last_spawn_at = time.time()
        self.winner = None

    def clamp_in_arena(self, x: int, y: int) -> Tuple[int, int]:
        return max(0, min(ARENA_WIDTH - 1, x)), max(0, min(ARENA_HEIGHT - 1, y))

    def spawn_powerup_if_needed(self, now: float):
        if now - self.last_spawn_at < POWERUP_SPAWN_INTERVAL:
            return
        self.last_spawn_at = now
        occupied = {(p.x, p.y) for p in self.players.values()}
        for _ in range(30):
            x = random.randint(2, ARENA_WIDTH - 3)
            y = random.randint(2, ARENA_HEIGHT - 3)
            if (x, y) not in occupied:
                self.powerups.append(PowerUp(x, y, random.choice(["shotgun", "dash_boost", "shield"]), now))
                return

    def apply_powerup(self, player: Player, kind: str, now: float):
        if kind == "shotgun":
            player.shotgun_until = max(player.shotgun_until, now + SHOTGUN_DURATION)
        elif kind == "dash_boost":
            player.dash_boost_until = max(player.dash_boost_until, now + DASH_BOOST_DURATION)
        elif kind == "shield":
            player.shield = True

    def handle_pickups(self, now: float):
        self.powerups = [p for p in self.powerups if now - p.spawned_at <= POWERUP_LIFETIME]
        for player in self.players.values():
            for pu in list(self.powerups):
                if (player.x, player.y) == (pu.x, pu.y):
                    self.apply_powerup(player, pu.kind, now)
                    self.powerups.remove(pu)

    def handle_key(self, key: str, now: float):
        if key == "q":
            raise KeyboardInterrupt
        for player in self.players.values():
            if not player.alive:
                continue
            m = KEYMAP[player.pid]
            dx, dy = 0, 0
            if key == m["up"]:
                dy = -1
            elif key == m["down"]:
                dy = 1
            elif key == m["left"]:
                dx = -1
            elif key == m["right"]:
                dx = 1
            if dx or dy:
                player.facing = (dx, dy)
                player.x, player.y = self.clamp_in_arena(player.x + dx, player.y + dy)

            if key == m["jump"]:
                player.level = LEVEL_JUMP
            elif key == m["crouch"]:
                player.level = LEVEL_CROUCH
            elif key == m["normal"]:
                player.level = LEVEL_NORMAL
            elif key == m["dash"]:
                self.dash(player, now)
            elif key == m["shoot"]:
                self.shoot(player, now)

    def shoot(self, player: Player, now: float):
        if not player.can_shoot(now):
            return
        player.last_shot_at = now
        dirs = [player.facing if player.facing != (0, 0) else (1, 0)]
        if now < player.shotgun_until:
            fx, fy = dirs[0]
            spread = [(fx, fy), (fx + fy, fy + fx), (fx - fy, fy - fx)]
            dirs = []
            for dx, dy in spread:
                ndx = 0 if dx == 0 else (1 if dx > 0 else -1)
                ndy = 0 if dy == 0 else (1 if dy > 0 else -1)
                if ndx == 0 and ndy == 0:
                    ndx = 1
                dirs.append((ndx, ndy))
        for dx, dy in dirs:
            self.projectiles.append(Projectile(player.x, player.y, dx, dy, player.level, player.pid))

    def dash(self, player: Player, now: float):
        if not player.can_dash(now):
            return
        player.last_dash_at = now
        dx, dy = player.facing
        if dx == 0 and dy == 0:
            dx = 1 if player.pid == "p1" else -1
        player.x, player.y = self.clamp_in_arena(player.x + dx * DASH_DISTANCE, player.y + dy * DASH_DISTANCE)

    def step_projectiles(self):
        for _ in range(PROJECTILE_SPEED):
            survivors = []
            for proj in self.projectiles:
                proj.x += proj.dx
                proj.y += proj.dy
                if not (0 <= proj.x < ARENA_WIDTH and 0 <= proj.y < ARENA_HEIGHT):
                    continue
                hit = False
                for pid, player in self.players.items():
                    if pid == proj.owner or not player.alive:
                        continue
                    if (player.x, player.y, player.level) == (proj.x, proj.y, proj.level):
                        if player.shield:
                            player.shield = False
                        else:
                            player.alive = False
                            self.winner = self.players[proj.owner]
                        hit = True
                        break
                if not hit:
                    survivors.append(proj)
            self.projectiles = survivors

    def render(self, now: float):
        grid = [[" " for _ in range(ARENA_WIDTH)] for _ in range(ARENA_HEIGHT)]

        for pu in self.powerups:
            grid[pu.y][pu.x] = {"shotgun": "S", "dash_boost": "D", "shield": "H"}[pu.kind]

        for proj in self.projectiles:
            if 0 <= proj.x < ARENA_WIDTH and 0 <= proj.y < ARENA_HEIGHT:
                grid[proj.y][proj.x] = LEVEL_PROJECTILE_GLYPHS[proj.level]

        for p in self.players.values():
            if p.alive:
                grid[p.y][p.x] = p.glyph()

        def status(player: Player) -> str:
            dash_left = max(0.0, player.dash_cooldown(now) - (now - player.last_dash_at))
            shot_left = max(0.0, SHOT_COOLDOWN - (now - player.last_shot_at))
            buffs = []
            if now < player.shotgun_until:
                buffs.append("SHOTGUN")
            if now < player.dash_boost_until:
                buffs.append("DASH+")
            if player.shield:
                buffs.append("SHIELD")
            buff_text = ",".join(buffs) if buffs else "-"
            return f"{player.name} LVL:{LEVEL_NAMES[player.level]:6} DASH:{dash_left:>4.1f}s SHOT:{shot_left:>4.2f}s BUFFS:{buff_text}"

        lines = [status(self.players["p1"]), "#" * (ARENA_WIDTH + 2)]
        for row in grid:
            lines.append("#" + "".join(row) + "#")
        lines.append("#" * (ARENA_WIDTH + 2))
        lines.append(status(self.players["p2"]))
        lines.append("ESC/Q: menu | P1 normal level: V | P2 normal level: M")

        clear_screen()
        print("\n".join(lines), flush=True)

    def round_over(self):
        clear_screen()
        print(f"{self.winner.name} WINS! ONE SHOT, ONE LIFE.\n")
        print("Press [R] for rematch, or [Enter] for main menu.")
        while True:
            choice = input("> ").strip().lower()
            if choice == "r":
                self.run_match()
                return
            if choice == "":
                return

    def run_match(self):
        self.reset_round()
        with Keyboard() as kb:
            try:
                while True:
                    now = time.time()
                    for key in kb.get_keys():
                        if key in ("\x1b", "q"):
                            return
                        self.handle_key(key, now)

                    self.spawn_powerup_if_needed(now)
                    self.handle_pickups(now)
                    self.step_projectiles()

                    if not self.players["p1"].alive:
                        self.winner = self.players["p2"]
                    elif not self.players["p2"].alive:
                        self.winner = self.players["p1"]

                    self.render(now)

                    if self.winner:
                        self.round_over()
                        return
                    time.sleep(FRAME_TIME)
            except KeyboardInterrupt:
                return

    def show_controls(self):
        clear_screen()
        print("=== CONTROLS ===\n")
        print("P1: W/A/S/D move | R jump | F crouch | V normal level | G dash | T shoot")
        print("P2: I/J/K/L move | U jump | O crouch | M normal level | P dash | Y shoot")
        print("Projectiles only hit opponents on the same vertical level.")
        print("Jump and crouch change ASCII size to simulate Z-level.")
        print("\nPress Enter to return.")
        input()

    def show_powerups(self):
        clear_screen()
        print("=== POWERUPS ===\n")
        print("S = Shotgun (temporary): fires 3 projectiles in spread")
        print("D = Dash Boost (temporary): significantly lowers dash cooldown")
        print("H = Shield: blocks the next incoming bullet")
        print("\nPowerups spawn over time and expire if not picked up.")
        print("\nPress Enter to return.")
        input()

    def menu(self):
        while True:
            clear_screen()
            print(r"""
   ___   _____  _____ ___ ___   ___  _   _   _   _  ___
  / _ \ / ____|/ ____|_ _|_ _| / _ \| \ | | | \ | |/ _ \
 | | | | (___ | |     | | | | | | | |  \| | |  \| | | | |
 | | | |\___ \| |     | | | | | | | | . ` | | . ` | | | |
 | |_| |____) | |____ | | | | | |_| | |\  | | |\  | |_| |
  \___/|_____/ \_____|___|___| \___/|_| \_| |_| \_|\___/
""")
            print("ASCII 3-LAYER DUEL ARENA\n")
            print("1) Start Match")
            print("2) Controls")
            print("3) Powerups")
            print("4) Quit")
            choice = input("\nSelect option: ").strip()

            if choice == "1":
                self.run_match()
            elif choice == "2":
                self.show_controls()
            elif choice == "3":
                self.show_powerups()
            elif choice == "4":
                clear_screen()
                return


if __name__ == "__main__":
    AsciiArenaGame().menu()
