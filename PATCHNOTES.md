# AvareonWar — Patch Notes

Player-facing release notes. For the full technical history, see [CHANGELOG.md](CHANGELOG.md).

---

## The Book of Tales Opens: Lack of Funds

*25 September 2026*

### A new tale to play

The Book of Tales - the button in the bottom-right corner of the Campaign screen - now holds
its first playable story. **Lack of Funds** takes you to the **Azincournean Highlands** at the
dawn of the Age of Empires, as the guiding hand behind Emperor Kondaron of the young Londic
Empire. The primitive Aelatanaic Tribes are gathering on your borders, and the Emperor wants
their lands. His people, however, are running out of patience.

- **Conquer the Aelatanaic Tribes** and **hold the city of Generax** - lose it and the tale is
  over.
- **The Heilonic Kingdoms and the Kingdom of Daurels** watch from the sidelines. They leave
  you alone... until you attack them. Strike one, and that kingdom will strike back.
- **The Tribes** start slowly, but once they get moving they will march on your lands, and
  on the unclaimed territories between you.
- You cannot train Heroes in this tale.
- The story is fully voiced, with an opening scene, a warning whenever your land rises up,
  and its own victory and defeat lines.

Winning earns the new **Lack of Funds** achievement. Tales can be saved and loaded from
Saved Games like any campaign chapter, and when a tale ends you return to the Book of Tales.

### Popularity

This tale introduces **Popularity**, shown as a blue bar in the bottom-left corner of the map.

- Your people's patience drains a little faster every turn you ignore them.
- Press **Invest** beneath the bar to spend gold on your own people: popularity rises, the
  drain slows back down, and the next investment costs a little more.
- At the start of each turn, the lower your popularity, the more likely one of your
  territories **revolts and joins the Tribes** - armies, buildings and all. Your poorest lands
  turn first; your richest only when things get truly bad. Generax will never betray you.
- End a turn at full popularity and your people stay loyal.

### Clearer borders on the Azincournean Highlands

Every territory on the Azincournean Highlands now has a thin outline, so you can see where
one ends and the next begins without hovering over it. This applies wherever you play the
map, including custom and multiplayer games.

### Fixes

- **Attacking an empty territory defended only by a Keep** no longer shows two phantom
  Swordsmen on the battle screen. The screen now shows "No units" with the Keep's defence and
  the correct strengths. Who wins was never affected - only what the screen showed.
- **Demolish Keep can be clicked again.** At some screen sizes the button sat under an area
  that ignored clicks, and during campaign chapters it was shown greyed out even where
  demolishing was allowed.

## Watching a Replay

*22 September 2026*

### The replay player now looks like the game

The Replays list was rebuilt recently, but the screen you actually watch a replay on was
still the old plain one - flat dark panels, grey rounded buttons, and `<<` / `||` / `>` typed
out as text where the playback controls should be.

It now matches the rest of the game. The bar across the top, the strip along the bottom and
the panel down the right side all use the same carved wood you see while playing, with brass
edging and proper golden buttons. The turn number sits in brass at the top right, so you can
see at a glance where you are.

The playback controls are real icons now - a play triangle, a pause, and step arrows -
instead of typed characters. They light up when you point at them and press in when you
click, the same as every other button in the game.

### Easier to read

- **Player names and the action log no longer run off the edge of the panel.** Anything too
  long for the panel is trimmed with an ellipsis instead of spilling past it.
- **Text is larger throughout.** The old sizes were noticeably smaller than every other
  screen.
- **The timeline is easier to grab**, with a larger brass handle and clearer turn marks.

Nothing about how the viewer works has changed. Space still plays and pauses, the arrow keys
still step through, `0`-`4` still switch whose stats you are looking at, and Escape still
takes you back to your replays.

## Saved Games and Replays

*22 September 2026*

### The last two plain screens now match the rest of the game

**Saved Games** and **Replays** were the only screens that still looked like placeholders.
Plain dark boxes, plain grey buttons, and a wash of black over the background - they never
looked like they belonged next to the campaign screens.

Both have been rebuilt. Your saves and replays now sit on the same carved wooden table you
see when you open a campaign chapter, under a brass heading, with the same golden buttons
along the bottom. The delete confirmation got the same treatment, so nothing jumps back to
the old look halfway through.

Nothing about how they work has changed. Click a save to pick it, click it again to load
it, or use the buttons. Everything is exactly where it was.

### Longer save names, and a few rough edges gone

- **Long save names no longer run into the Date column.** Anything too long for its column
  is now trimmed with an ellipsis instead of overlapping what's next to it.
- **A scroll bar shows you where you are** in a long list. Before, the only hint that there
  was more below was the list moving.
- **Scrolling no longer drags rows up over the column headings.**
- **On ultrawide monitors the columns now spread across the full width** instead of
  bunching up on the left-hand side.
- **The mouse wheel works properly on an empty list**, and stops cleanly at the bottom of a
  full one.

### Both screens open faster

Opening Saved Games or Replays used to stall for a moment before drawing. That pause is
gone. It's most noticeable with Replays - every time you finish watching one and come back
to the list, it now appears immediately instead of hitching first.

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
