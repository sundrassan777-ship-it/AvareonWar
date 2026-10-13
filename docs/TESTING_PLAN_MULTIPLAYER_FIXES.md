# Multiplayer - Pre-launch LAN Test Plan

**Updated:** 2026-10-12 (after the multiplayer audit, Phases 1-8 on `fix/multiplayer-sync`)
**Purpose:** check on real PCs what the automated tests cannot: real networks, real timing,
real players. The automated suite (`tests/test_mp_*.py`, see CODE_GUIDE "Testing Network
Changes") already runs 2-4 real games in one process for every audit finding.

This replaces the February 2026 plan; several things it checked work differently now
(state snapshots instead of per-field gold syncs, seeded battle replays, host-run AI).

---

## Before you start

- **PCs:** 2 for the first pass, then 3-4. All on the same build (the version check refuses
  a mismatch with a message).
- **Hosting:** Main Menu -> Multiplayer -> Host Game. **Joining:** Multiplayer -> Join Game,
  enter the host's IP (shown on the host's lobby screen). Steam: the host's **Invite Friend**
  button in the lobby.
- **After every session, collect from each PC** (zip and name by player):
  - `logs/avareonwar.log` (+ `.1`-`.3` if it rotated) - everything, incl. network warnings
  - `Logs/sync/*.json` - per-game sync log (actions, turn checksums, any desync diff)
  - `Logs/*.json` - per-game log
- Note the time and turn/round when anything looks wrong - it makes the logs easy to find.

### Log lines that mean "look here"

| Line | Meaning |
|------|---------|
| `[SYNC] This PC's state differed from the turn owner's ...` | Sequential: this PC had drifted; the owner's state was applied (healed). Worth a report. |
| `[NETWORK] Replayed battle at X differs from the resolver's ...` | A battle replay came out differently; the resolver's result was applied. Worth a report. |
| `[NETWORK] Failed to apply <TYPE> - message skipped` (+ traceback) | A bug in a message handler. **Always report.** |
| `[NETWORK] REJECTED ...` | A message refused by the rules (who may send what). Should never appear with honest players - report. |
| `[NETWORK] Held messages waited Ns - applying them anyway` | A result arrived long before this PC finished its animation (15 s limit). Report with the turn. |
| `Traceback (most recent call last)` anywhere | Report. |

---

## A. Connecting and the lobby

| # | Steps | Expected |
|---|-------|----------|
| A1 | Host a game; 1-3 players join. | Every PC lists every player in the right slot. Two players with the same name stay in their own slots. |
| A2 | Each player picks a territory, colour and team. | Every PC shows the same picks. A client can only change its own colour/team/territory. |
| A3 | Two players click the same territory at nearly the same time. | Exactly one gets it - the one whose click reached the host first. Nobody loses a territory they already held. |
| A4 | A client leaves the lobby (Leave or closes the game). | Their slot empties on every PC, incl. the host. Their territory is free again. Someone else can join into that slot. |
| A5 | Make slots 1 and 3 occupied with 2 empty, or put everyone on one team. | Launch is greyed out; hovering it says why. |
| A6 | Host on a map other than Avareon (e.g. Azincournean Highlands); a friend joins **through a Steam invite**. | The client loads the same map as the host. |
| A7 | Launch. While loading, a client presses Escape (or closes the game). | That client returns to the menu; the host and the others still start the game (the host does not wait forever). |
| A8 | Launch normally. | Everyone gets to "click to start" and sees the same map, the same starting armies, and **the colours and flags chosen in the lobby**. With Neutral Armies on, the same neutral armies everywhere. With Randomize Bonuses on, the same bonuses everywhere. |
| A9 | Try to join a game that has started. | Refused with a clear message ("The game has already started"). |

## B. Sequential turns

Play 3-5 full turns per configuration: 2 humans; 2 humans + 1 AI; 4 players incl. allies.

| # | Steps | Expected |
|---|-------|----------|
| B1 | On your turn: build, train, research, hero training, castle upgrade, cancel one of each, demolish, move without fighting. | Every other PC shows the same result by the end of your turn (builds/trains may show at End Turn). |
| B2 | Attack: win one battle, lose one, tie one (dice). | Every PC shows the same battle, the same survivors (types and levels), the same captured buildings destroyed, the same hero deaths, and the defender gets their Battle Report. |
| B3 | Let the planning timer run out with moves queued. | The moves still happen on every PC, then the next player's turn starts once on every PC (nobody skips a turn). |
| B4 | AI turn (game with an AI slot). | Every PC sees the same AI moves and battles; afterwards every PC shows the same map. |
| B5 | Leave a battle untouched for 90 s on your turn. | It resolves itself on your PC; after 180 s everything left is settled. Nobody is stuck. |
| B6 | Gold transfer to an ally (if enabled), once per turn. | Arrives once; the sender cannot send more than they have; enemies cannot receive. |
| B7 | Team chat and all chat. | Team chat only reaches allies. |

## C. Simultaneous rounds (primary mode - spend the most time here)

Same configurations as B, plus one 4-player game with 2 v 2 teams.

| # | Steps | Expected |
|---|-------|----------|
| C1 | Everyone plans orders (moves, builds, trains, hero abilities), clicks End Turn at different times. | The "Waiting for: ..." list is right on every PC at every moment. Execution starts on every PC together. |
| C2 | Two armies cross each other on the same border; one is larger. | The same forced-defence outcome on every PC. |
| C3 | Several battles in one round, with different resolvers. | Each resolver fights their own; every PC ends the round with the same map. |
| C4 | Allies capture the same territory together. | The alliance choice goes to the same player on every PC; the result is the same everywhere. |
| C5 | A resolver walks away during battles for 90 s, then 180 s. | At 90 s their own PC resolves their battles; at 180 s the host settles everything left. The round ends on every PC. |
| C6 | Split one army into two orders along the same route. | Both halves move. |
| C7 | A Capital Assault victory, or an elimination mid-round. | The same result and the same end screen on every PC. |

## D. Leaving mid-game

| # | Steps | Expected |
|---|-------|----------|
| D1 | A client closes the game while planning (both modes). | Chat on every PC shows **System:** "<name> has disconnected. AI taking over." The AI (Medium) plays their empire from then on; the game continues. |
| D2 | A client closes the game while their battle window is open / during their sequential turn. | Their battles are fought for them; the turn/round ends normally. |
| D3 | The host closes the game. | Every client sees "Connection lost" and returns to the menu. |
| D4 | Rejoining a running game. | Not possible for launch (reconnect is off by design). |

## E. Progress and end of game

| # | Steps | Expected |
|---|-------|----------|
| E1 | Finish a game a **client** wins. | That client gets the win in the recap, achievements and XP - not the host. |
| E2 | Finish a team game the team wins. | **Every** player on the winning team is credited with the win (recap, achievements, XP). |
| E3 | Win against a player who left on turn 1. | Little/no win XP (anti win-farming). |
| E4 | Recap screen on each PC. | Opens on every PC with the same statistics. |

## F. Quick smoke test (10 minutes, 2 PCs)

1. Host + 1 client, Simultaneous, Avareon, one AI slot.
2. Round 1: each player moves, builds a Farm, trains a unit; End Turn.
3. Round 2: attack the AI; fight the battle; check both PCs show the same result.
4. Round 3: the client attacks the host; the host fights; check survivors on both PCs.
5. The client closes the game; the host sees the System chat line and plays on vs. the AI.
6. Collect both PCs' logs and check them for the lines in the table above.

## G. Joining through Steam (2 PCs, a playtest build on both)

Added 2026-10-13 with Steam joining (CODE_GUIDE "Steam joining (SDR bridge)"). A = host,
B = a Steam friend. Steam must be running and online on both. Copy both logs afterwards -
they grow across sessions, so say when the test started.

| # | Steps | Expected |
|---|-------|----------|
| G1 | A hosts. B opens Join Game. | B's **Steam Friends** tab lists A within ~2 s; **Join** gets B into the lobby in 1-2 s. A's lobby line ends with "or via Steam". |
| G2 | B's game closed: B uses **Join Game** on A in Steam's friends list (or accepts A's invite). | The game starts and joins A - no "launched with arguments" warning from Steam. |
| G3 | B's game open on the main menu, the multiplayer menu or Join Game: Join Game on A in Steam (also press it twice). | B joins at once from any of those screens, once. |
| G4 | B in a game (single player): A invites B. | A gold message in B's game; B joins after returning to the main menu. |
| G5 | Play a few rounds over Steam, incl. a battle; then A quits mid-game. | The game plays normally; B sees "Connection lost". |
| G6 | A fills the free slots with AI; B tries to join. | Refused with the reason ("No slots available"), at once. |
| G7 | A goes back to the main menu; B uses an old invite. | A leaves B's list within ~2 s; B is told "A is not hosting a game right now" at once (no address attempts). |
| G8 | A starts the game with the launch option `--no-steam-relay`. | A's lobby says "Steam off"; B still sees A in the list and joins by address. |
| G9 | B on another network (e.g. a phone hotspot); B joins from the list. | Joins; B's log says "connected (relayed)". |
| G10 | B presses Cancel while "Connecting to A through Steam". | Back at once. |

**If something fails, `--sdr-test`** (launch option) opens a diagnostics window instead of the
game and writes `logs/sdr_test.log`: relay state, a single-PC self-test (S), host (H) / join
(J) between the two PCs.

---

**Report format:** what you did, what you expected, what you saw, the turn/round, which PC,
plus the logs from every PC.
