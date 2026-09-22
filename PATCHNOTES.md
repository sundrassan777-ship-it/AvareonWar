# AvareonWar — Patch Notes

Player-facing release notes. For the full technical history, see [CHANGELOG.md](CHANGELOG.md).

---

## Battle Reports

*22 September 2026*

### New: Battle Reports

**You can finally see what happened while you weren't looking.**

Until now, being attacked told you almost nothing. You ended your turn, the enemy moved,
and the only clue was a province quietly changing colour. Did the garrison put up a fight?
Did you lose the Barracks you'd been saving for? With ten or more territories, there was
no way to tell.

Now, at the start of your turn, a report appears over **every territory that was attacked
while you waited**.

Each one tells you at a glance whether you **DEFENDED** or **LOST**, and what it cost:

```
        DEFENDED                          LOST
        ────────                          ────
  - 4 Units Remaining              - 3 Units Lost
  - 2 Structures Remaining         - 2 Structures Destroyed
```

- **Detail** opens the full battle screen — the same one the attacker saw when they beat
  you, but from your side of the field, with your losses broken down by unit type.
- **Close** dismisses a single report.
- **Close All Battle Reports** appears at the top of the screen and clears the lot.

Reports stay pinned to the territory they belong to, so panning the map carries them with
it. They last for your planning phase only: once you end your turn, read or not, they're
gone.

**You'll get a report for:**
- Any battle fought over one of your territories, win or lose
- A territory taken from you **without a fight** — the easiest loss of all to miss
- A **Keep or Fortress that defended alone**, which correctly reports no troop losses

**You won't get one for** territory taken by Halon Nextroy's Aggressive Diplomacy, which
already plays out in front of you, or for an ally taking over a province.

### Losing to Seledra reads differently now

If the player who takes your territory has **Seledra Rennervail**, her Champion of the
People spares your Farms and Mines — but they don't vanish, they *change hands*. Reports
count those separately:

```
  - 4 Units Lost
  - 1 Structure Destroyed
  - 2 Structures Captured
```

So you can tell the difference between a province razed to the ground and one handed over
intact to feed an enemy economy.

### Fixes

- **Fixed a crash** when a territory holding several players' armies lost one of them.
  Most likely after a battle or a withdrawal from a contested province.
- **Fixed a crash** that could occur if a button's artwork failed to load. Buttons now fall
  back to a plain style instead of taking the game down.

### Interface

- The **Cancel** button for construction now just reads "Cancel". The building's name was
  overflowing the button, and the panel above it already tells you what you're cancelling.
- Hero training now reads **"3 turns remaining"** instead of "Training: 3 turns remaining",
  which was running past the edge of the Heroes tab. It also correctly says "1 turn
  remaining" on the final turn.

### Notes

- Battle Reports work in **both turn modes** and in **multiplayer**, including when the
  battle was resolved on someone else's machine.
- In hotseat, each player sees their own reports on their own turn.
- Reports are not saved — they belong to the turn they appear on.
