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

FRAME_TIME = 0.05
MOVE_HOLD_TIMEOUT = 0.35
SHOT_COOLDOWN = 0.1
CHARGE_RELEASE_WINDOW = 0.08
MAX_CHARGE_TIME = 0.75
DASH_COOLDOWN = 2.2
DASH_DISTANCE = 7
DASH_TRAIL_TTL = 0.18
PROJECTILE_SPEED = 2
POWERUP_SPAWN_INTERVAL = 8.0
POWERUP_LIFETIME = 14.0
SHOTGUN_DURATION = 10.0
DASH_BOOST_DURATION = 10.0
DASH_BOOST_COOLDOWN = 0.6
JUMP_DURATION = 0.45

LEVEL_NORMAL = 0
LEVEL_JUMP = 1
LEVEL_NAMES = {LEVEL_NORMAL: "NORMAL", LEVEL_JUMP: "JUMP"}
LEVEL_PLAYER_GLYPHS = {LEVEL_NORMAL: "A", LEVEL_JUMP: "^"}
LEVEL_PLAYER2_GLYPHS = {LEVEL_NORMAL: "B", LEVEL_JUMP: "M"}
PROJECTILE_GLYPHS = {
    LEVEL_NORMAL: {1: "*", 2: "#", 3: "@"},
    LEVEL_JUMP: {1: "O", 2: "Q", 3: "0"},
}

ARENA_PRESETS = {
    "small": (30, 10),
    "medium": (44, 14),
    "large": (70, 24),
}

KEYMAP = {
    "p1": {"up": "w", "down": "s", "left": "a", "right": "d", "jump": "e", "dash": "r", "shoot": "q"},
    "p2": {"up": "i", "down": "k", "left": "j", "right": "l", "jump": "o", "dash": "p", "shoot": "u"},
}


@dataclass
class Projectile:
    x: int
    y: int
    dx: int
    dy: int
    level: int
    owner: str
    size: int = 1


@dataclass
class PowerUp:
    x: int
    y: int
    kind: str
    spawned_at: float


@dataclass
class DashTrail:
    x: int
    y: int
    glyph: str
    expires_at: float


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
    jump_until: float = 0.0
    move_dx: int = 0
    move_dy: int = 0
    move_until: float = 0.0
    charging: bool = False
    charge_started_at: float = 0.0
    last_charge_input_at: float = 0.0

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
                keys.append("\n" if c == "\r" else c)
        else:
            while True:
                readable, _, _ = select.select([sys.stdin], [], [], 0)
                if not readable:
                    break
                c = sys.stdin.read(1)
                if not c:
                    break
                keys.append(c)
        return keys

    def wait_for_any_key(self):
        while True:
            if self.get_keys():
                return
            time.sleep(0.03)


def clear_screen():
    print("\033[2J\033[H", end="")


class AsciiArenaGame:
    def __init__(self):
        self.players: Dict[str, Player] = {}
        self.projectiles: List[Projectile] = []
        self.powerups: List[PowerUp] = []
        self.dash_trails: List[DashTrail] = []
        self.last_spawn_at = time.time()
        self.scores = {"p1": 0, "p2": 0}
        self.bot_mode = False
        self.last_bot_action = 0.0
        self.arena_size_name = "large"
        self.arena_width, self.arena_height = ARENA_PRESETS[self.arena_size_name]

    def select_arena_size(self) -> bool:
        clear_screen()
        print("Choose arena size:\n\n1) Small\n2) Medium\n3) Large\n(Enter/Esc to cancel)")
        choice = input("\nSelect option: ").strip()
        if choice == "1":
            self.arena_size_name = "small"
        elif choice == "2":
            self.arena_size_name = "medium"
        elif choice == "3":
            self.arena_size_name = "large"
        else:
            return False
        self.arena_width, self.arena_height = ARENA_PRESETS[self.arena_size_name]
        return True

    def reset_round(self):
        self.players = {
            "p1": Player("p1", "P1", 4, self.arena_height // 2, facing=(1, 0)),
            "p2": Player("p2", "BOT" if self.bot_mode else "P2", self.arena_width - 5, self.arena_height // 2, facing=(-1, 0)),
        }
        self.projectiles = []
        self.powerups = []
        self.dash_trails = []
        self.last_spawn_at = time.time()

    def clamp_in_arena(self, x: int, y: int) -> Tuple[int, int]:
        return max(0, min(self.arena_width - 1, x)), max(0, min(self.arena_height - 1, y))

    def spawn_powerup_if_needed(self, now: float):
        if now - self.last_spawn_at < POWERUP_SPAWN_INTERVAL:
            return
        self.last_spawn_at = now
        occupied = {(p.x, p.y) for p in self.players.values()}
        for _ in range(30):
            x = random.randint(1, self.arena_width - 2)
            y = random.randint(1, self.arena_height - 2)
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

    def normalize_key(self, key: str) -> str:
        if key == "\x1b":
            return key
        return key.lower() if key.isalpha() else key

    def update_level_state(self, player: Player, now: float):
        if player.level == LEVEL_JUMP and now >= player.jump_until:
            player.level = LEVEL_NORMAL

    def fire_projectiles(self, player: Player, now: float, size: int):
        player.last_shot_at = now
        base_dx, base_dy = player.facing if player.facing != (0, 0) else (1, 0)
        shots = [(base_dx, base_dy, 0, 0)]
        if now < player.shotgun_until:
            px, py = -base_dy, base_dx
            shots = [
                (base_dx, base_dy, 0, 0),
                (base_dx, base_dy, px, py),
                (base_dx, base_dy, -px, -py),
            ]
        for dx, dy, ox, oy in shots:
            sx, sy = self.clamp_in_arena(player.x + ox, player.y + oy)
            self.projectiles.append(Projectile(sx, sy, dx, dy, player.level, player.pid, size=size))

    def start_or_update_charge(self, player: Player, now: float):
        if not player.charging:
            if not player.can_shoot(now):
                return
            player.charging = True
            player.charge_started_at = now
            player.last_charge_input_at = now
        else:
            player.last_charge_input_at = now

    def maybe_release_charge(self, player: Player, now: float):
        if not player.charging:
            return
        if now - player.last_charge_input_at < CHARGE_RELEASE_WINDOW and now - player.charge_started_at < MAX_CHARGE_TIME:
            return
        charge_time = max(0.0, min(MAX_CHARGE_TIME, now - player.charge_started_at))
        size = 1 if charge_time < 0.15 else (2 if charge_time < 0.4 else 3)
        self.fire_projectiles(player, now, size)
        player.charging = False

    def handle_key_for_player(self, player: Player, key: str, now: float):
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
            if not player.charging:
                player.move_dx, player.move_dy = dx, dy
                player.move_until = now + MOVE_HOLD_TIMEOUT

        if key == m["jump"]:
            player.level = LEVEL_JUMP
            player.jump_until = now + JUMP_DURATION
        elif key == m["dash"]:
            self.dash(player, now)
        elif key == m["shoot"]:
            self.start_or_update_charge(player, now)

    def apply_continuous_movement(self, player: Player, now: float):
        if player.charging:
            return
        if now <= player.move_until and (player.move_dx or player.move_dy):
            player.x, player.y = self.clamp_in_arena(player.x + player.move_dx, player.y + player.move_dy)

    def handle_inputs(self, keys: List[str], now: float):
        normalized = [self.normalize_key(k) for k in keys]
        if "\x1b" in normalized:
            raise KeyboardInterrupt

        for key in normalized:
            for player in self.players.values():
                if not player.alive or (self.bot_mode and player.pid == "p2"):
                    continue
                self.handle_key_for_player(player, key, now)

        for player in self.players.values():
            self.apply_continuous_movement(player, now)
            self.update_level_state(player, now)
            self.maybe_release_charge(player, now)

    def run_bot(self, now: float):
        if not self.bot_mode:
            return
        bot = self.players["p2"]
        if not bot.alive or now - self.last_bot_action < 0.16:
            return
        self.last_bot_action = now
        action = random.choice(["move", "move", "move", "jump", "dash", "shoot"])
        if action == "move":
            self.handle_key_for_player(bot, random.choice(["i", "j", "k", "l"]), now)
        elif action == "jump":
            self.handle_key_for_player(bot, "o", now)
        elif action == "dash":
            self.handle_key_for_player(bot, "p", now)
        elif action == "shoot" and bot.can_shoot(now):
            self.fire_projectiles(bot, now, 1)
        self.apply_continuous_movement(bot, now)
        self.update_level_state(bot, now)

    def dash(self, player: Player, now: float):
        if player.charging or not player.can_dash(now):
            return
        player.last_dash_at = now
        dx, dy = player.facing
        if dx == 0 and dy == 0:
            dx = 1 if player.pid == "p1" else -1

        trail_glyph = "-" if dx != 0 else "|"
        start_x, start_y = player.x, player.y
        for i in range(1, DASH_DISTANCE):
            tx, ty = start_x - dx * i, start_y - dy * i
            if 0 <= tx < self.arena_width and 0 <= ty < self.arena_height:
                self.dash_trails.append(DashTrail(tx, ty, trail_glyph, now + DASH_TRAIL_TTL))

        player.x, player.y = self.clamp_in_arena(player.x + dx * DASH_DISTANCE, player.y + dy * DASH_DISTANCE)

    def projectile_hits_player(self, proj: Projectile, player: Player) -> bool:
        if player.level != proj.level:
            return False
        return abs(player.x - proj.x) + abs(player.y - proj.y) <= max(0, proj.size - 1)

    def step_projectiles(self) -> Optional[str]:
        scorer = None
        for _ in range(PROJECTILE_SPEED):
            survivors = []
            for proj in self.projectiles:
                proj.x += proj.dx
                proj.y += proj.dy
                if not (0 <= proj.x < self.arena_width and 0 <= proj.y < self.arena_height):
                    continue
                hit = False
                for pid, player in self.players.items():
                    if pid == proj.owner or not player.alive:
                        continue
                    if self.projectile_hits_player(proj, player):
                        if player.shield:
                            player.shield = False
                        else:
                            player.alive = False
                            scorer = proj.owner
                        hit = True
                        break
                if not hit:
                    survivors.append(proj)
            self.projectiles = survivors
            if scorer:
                return scorer
        return None

    def step_dash_trails(self, now: float):
        self.dash_trails = [t for t in self.dash_trails if now < t.expires_at]

    def draw_projectile(self, grid: List[List[str]], proj: Projectile):
        radius = max(0, proj.size - 1)
        glyph = PROJECTILE_GLYPHS[proj.level][proj.size]
        for ox in range(-radius, radius + 1):
            for oy in range(-radius, radius + 1):
                if abs(ox) + abs(oy) > radius:
                    continue
                px, py = proj.x + ox, proj.y + oy
                if 0 <= px < self.arena_width and 0 <= py < self.arena_height:
                    grid[py][px] = glyph

    def charge_tier(self, player: Player, now: float) -> int:
        charge_time = max(0.0, min(MAX_CHARGE_TIME, now - player.charge_started_at))
        return 1 if charge_time < 0.15 else (2 if charge_time < 0.4 else 3)

    def facing_indicator(self, player: Player, now: float) -> str:
        if player.charging:
            return PROJECTILE_GLYPHS[player.level][self.charge_tier(player, now)]
        fx, fy = player.facing
        if abs(fx) >= abs(fy):
            return ">" if fx >= 0 else "<"
        return "v" if fy > 0 else "^"

    def render(self, now: float):
        grid = [[" " for _ in range(self.arena_width)] for _ in range(self.arena_height)]
        for t in self.dash_trails:
            if 0 <= t.x < self.arena_width and 0 <= t.y < self.arena_height:
                grid[t.y][t.x] = t.glyph
        for pu in self.powerups:
            grid[pu.y][pu.x] = {"shotgun": "S", "dash_boost": "D", "shield": "H"}[pu.kind]
        for proj in self.projectiles:
            self.draw_projectile(grid, proj)
        for p in self.players.values():
            if p.alive:
                grid[p.y][p.x] = p.glyph()
        for p in self.players.values():
            if not p.alive:
                continue
            ax, ay = p.x + p.facing[0], p.y + p.facing[1]
            if 0 <= ax < self.arena_width and 0 <= ay < self.arena_height:
                grid[ay][ax] = self.facing_indicator(p, now)

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
            charge = " CHARGING" if player.charging else ""
            return f"{player.name} LVL:{LEVEL_NAMES[player.level]:6} DASH:{dash_left:>4.1f}s SHOT:{shot_left:>4.2f}s BUFFS:{','.join(buffs) if buffs else '-'}{charge}"

        score_line = f"ARENA:{self.arena_size_name.upper():6}  SCORE  P1:{self.scores['p1']}  {self.players['p2'].name}:{self.scores['p2']}"
        lines = [score_line, status(self.players["p1"]), "#" * (self.arena_width + 2)]
        for row in grid:
            lines.append("#" + "".join(row) + "#")
        lines.append("#" * (self.arena_width + 2))
        lines.append(status(self.players["p2"]))
        lines.append("ESC: menu | hold shoot to charge | can re-aim while charging")
        clear_screen()
        print("\n".join(lines), flush=True)

    def show_point_popup(self, scorer_pid: str, kb: Keyboard):
        self.scores[scorer_pid] += 1
        winner_name = self.players[scorer_pid].name
        clear_screen()
        print(f"{winner_name} scored a point!\n")
        print(f"Current score: P1 {self.scores['p1']} - {self.players['p2'].name} {self.scores['p2']}")
        print("\nPress any key to continue...")
        kb.wait_for_any_key()

    def run_match(self, versus_bot: bool = False):
        self.bot_mode = versus_bot
        self.last_bot_action = 0.0
        self.reset_round()
        with Keyboard() as kb:
            try:
                while True:
                    now = time.time()
                    keys = kb.get_keys()
                    self.handle_inputs(keys, now)
                    self.run_bot(now)
                    self.spawn_powerup_if_needed(now)
                    self.handle_pickups(now)
                    scorer = self.step_projectiles()
                    self.step_dash_trails(now)
                    self.render(now)
                    if scorer:
                        self.show_point_popup(scorer, kb)
                        self.reset_round()
                    time.sleep(FRAME_TIME)
            except KeyboardInterrupt:
                return

    def show_controls(self):
        clear_screen()
        print("=== CONTROLS ===\n")
        print("P1: W/A/S/D move | E jump | R dash | Q shoot (hold to charge)")
        print("P2: I/J/K/L move | O jump | P dash | U shoot (hold to charge)")
        print("Jump auto-returns to normal level after a short time.")
        print("Movement continues while holding direction and stops during shot charge.")
        print("You can re-aim while charging without firing/canceling.")
        print("Facing indicator arrows (< > ^ v) show current aim direction.")
        print("Projectiles only hit opponents on the same vertical level.")
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
            print("1) 1v1 Local")
            print("2) Versus Bot")
            print("3) Controls")
            print("4) Powerups")
            print("5) Quit")
            choice = input("\nSelect option: ").strip()
            if choice in ("1", "2"):
                if self.select_arena_size():
                    self.run_match(versus_bot=choice == "2")
            elif choice == "3":
                self.show_controls()
            elif choice == "4":
                self.show_powerups()
            elif choice == "5":
                clear_screen()
                return


if __name__ == "__main__":
    AsciiArenaGame().menu()
