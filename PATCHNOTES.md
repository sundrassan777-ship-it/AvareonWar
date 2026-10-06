# AvareonWar — Patch Notes

Player-facing release notes. For the full technical history, see [CHANGELOG.md](CHANGELOG.md).

---

## A New Tale: Final Breaths

*6 October 2026*

### The last stand of the Zjoal Empire

The Book of Tales has a second story. **Final Breaths** takes you to the final years of the Age
of Kings. A civil war has split the once-mighty Zjoal Empire in two, and the wealthy Kerunian
Empire is marching up from the south while the eastern provinces slip away in rebellion.

- **Hold Lunedale and Free Cities for 15 turns.** Lose either one and the tale is over. A
  counter in the bottom-left corner of the map shows how many turns remain.
- **The Kerunian Empire** starts with a full treasury and attacks every single turn. How many
  troops it can throw at one territory grows as the turns go by.
- **The Nordian Rebels** take one of your territories every other turn - and every turn from
  turn 6 - along with its armies and buildings. They never attack, but they never give land
  back on their own either. Lunedale, Free Cities, Damlére and Oucine stay loyal.
- **Your treasury is taxed at 100%:** any gold you haven't spent when you end your turn is
  lost. Your provinces are full of Barracks - demolishing them refunds their full cost and
  frees the plot for a Mine or a Farm.
- You start with the whole Combat branch and parts of the Economy and Leadership branches
  already researched, and a Castle in Lunedale. Nobody can train Heroes in this tale.
- The tale plays on the lands of Campaign Chapter 3. Tales can be saved and loaded from Saved
  Games.

Winning earns the new **Final Breaths** achievement.

### Fixes

- **Computer opponents no longer waste training orders** when the enemy armies next to them
  are mostly Captains.

---

## The Game Tells You Why

*26 September 2026*

### No more silent clicks

When the game refuses something you try, it now tells you why: you hear the refusal sound
and a red message appears in the top-left corner of the map. Before, many of these clicks
simply did nothing, or left a line in the Action Log that you only saw if that tab was open.

- **Army orders:** "Cannot reach target territory!", "Cannot reinforce X: would exceed army
  limit of 15!", "Some selected armies are not ready to move!", a territory the campaign
  hasn't unlocked yet, or giving orders while battles are being resolved.
- **Hero abilities:** every reason an ability can't hit the territory you picked - your own
  land, neutral land, Defiance, too many units, no Keep, and so on. You stay in targeting
  mode, so you can simply pick another territory.
- **Reinforce** now tells you when its Keep territory is too full, instead of doing nothing.
- **Regicide** on a Keep with no hero inside now tells you it missed. It still goes on
  cooldown - Regicide has to find its mark.
- **Build shortcut keys** on a plot that is already in use, **research** while battles are
  being resolved, and **sending 0 Gold** to an ally in the Players window.
- The message that used to pop up in the middle of the screen for a wrong ability target is
  gone - every message now appears in the same place.
- Clicking the same refused button again refreshes the message instead of piling up copies,
  and longer messages wrap onto a second line instead of being cut off.

### Heroes fall - and you hear about it

When an enemy captures the Keep one of your heroes lives in, or kills it with Regicide, you
now see **"Our Hero, X, has been slain in Y!"** - even when it happens during an opponent's
turn in multiplayer.

### Buttons show what you can really do

- **Red** means a rule prevents it right now; **grey** means the tutorial or the current
  campaign chapter has locked it.
- Map build icons now show a second Square and a Keep in a Fortress territory as
  unavailable; map training icons show a full training queue (4 units).
- While a technology is being researched, the others are greyed out and their tooltip says
  why. The "can't afford" colour now includes your territory research discounts.
- Hero training buttons turn red while their Keep is being upgraded to a Castle.
- End Turn is greyed out while armies are still marching, while battles wait to be resolved,
  and during a campaign intro.
- Battle markers are grey on every turn that isn't yours, including other players' turns in
  multiplayer.
- Locked tabs, order cancel buttons and build buttons during tutorials and campaign intros
  are greyed out instead of looking clickable.
- "Save failed!" is now shown in red.

### Fixes

- **Units were trained twice in single-player Simultaneous games.** Training from the icons
  around a Barracks queued two units and charged you twice.
- **A refused order no longer cancels your armies' previous orders.** Re-ordering units to a
  territory they couldn't reach used to wipe their existing order anyway.
- **Cancelling an order cancels that order.** In games with AI opponents, the X next to an
  order could remove a different one, and Cancel All removed other players' orders too.
- **Demolish Keep works in campaign chapters that forbid hero training.**
- **Hero abilities can no longer target territories hidden by a campaign chapter.**
- **Keyboard build and training shortcuts** now behave exactly like clicking the buttons,
  including in multiplayer.
- Re-ordering some of your units to the territory they were already heading for is no longer
  refused as "over the army limit".

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
