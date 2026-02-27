# Avareon War - Game Mechanics

**Purpose:** Understand how the game works

---

## 🎮 Core Gameplay Loop

```
Turn Structure:
1. Planning Phase  → Give orders
2. Orders Phase    → Execute orders  
3. Battles Phase   → Resolve conflicts
4. Income Phase    → Collect gold
→ Repeat
```

---

## 🗺️ Territory System

**57 Territories** on the map

**Territory Properties:**
- Owner (player 1-8, or neutral 0)
- Army count (0+)
- Army composition (unit types)
- Buildings (0-5 plots per territory)
- Base income (varies by territory)
- Territorial bonus type (one per territory)

**Adjacency:**
- Territories connect to neighbors
- Can only move to adjacent territories
- Defined in map_data.py ADJACENCY dict

---

## ⚔️ Army System

**4 Unit Types (Counter System):**
- **Swordsman** (25g) — Counters Pikeman, countered by Archer
- **Archer** (20g) — Counters Swordsman, countered by Cavalry
- **Pikeman** (30g) — Counters Cavalry, countered by Swordsman
- **Cavalry** (40g) — Counters Archer, countered by Pikeman

Counter advantage grants 2.0× effective strength in combat (countered units are 0.5×).

**Army Movement:**
1. Select territory with your army
2. Click adjacent territory
3. Order arrow appears
4. Click "End Turn" → armies move

**Army Recruitment:**
1. Select territory with Barracks
2. Click unit type button
3. Pay gold → unit trains for 1 turn
4. Unit spawns next turn (up to 4 in queue per Barracks)

---

## 🏗️ Building System

**5 Building Types:**

1. **Farm** (Cost: 30 gold, Build: 1 turn)
   - +10 income per turn
   - Gains XP passively (+20/turn), each level adds +10% income

2. **Mine** (Cost: 40 gold, Build: 1 turn)
   - +15 income per turn
   - Gains XP passively (+20/turn), each level adds +10% income

3. **Barracks** (Cost: 50 gold, Build: 1 turn)
   - Enables unit recruitment (queue up to 4 units)

4. **Keep/Fortress** (Cost: 100 gold, Build: 2 turns)
   - +2 effective armies for defender in battle
   - One per territory; can upgrade to Castle (150 gold)

5. **Square** (Cost: 60 gold, Build: 1 turn)
   - 1.5× income multiplier for the territory
   - Multiple Squares compound: 1.5 × 1.5 = 2.25×

**Building Process:**
1. Select territory you own
2. Click empty plot (green circle)
3. Choose building type
4. Pay gold → added to queue
5. Each turn: construction_turns -= 1
6. When done → building provides benefits

**Cancellation & Refunds:**
- Cancelling training or research refunds the **exact gold paid** at time of start
- The system stores `cost_paid` so refund is accurate even if bonuses/discounts change
- Construction cancellation also refunds full cost

**Square Multiplier Stacking:**
- If a territory has multiple Squares, their multipliers compound: `1.5 × 1.5 = 2.25×`
- With Supply & Demand tech: `2.5 × 2.5 = 6.25×`

**Building Limits:**
- Max 1 building per turn per territory
- Each plot can have only 1 building
- Must have sufficient gold
- Can queue multiple (built sequentially)

---

## ⚔️ Battle System

**When Battles Occur:**
- Army moves into enemy territory
- Battle scheduled
- Resolved in Battles Phase

**Battle Resolution:**
1. Click battle marker (crossed swords)
2. See participants & armies
3. Click "Resolve"
4. Combat calculated:
   - Base strength from units and counter advantages
   - Keep bonus (+2 effective armies for defender)
   - Unit veterancy bonuses (+15% per level)
   - Composition bonuses (counter matchups)
5. Winner determined
6. Casualties applied
7. Territory ownership updates

**Strength Calculation:**
```
Strength = Sum of (unit_count * unit_strength * counter_bonus)

Defender bonuses:
- Keep: +2 effective armies
- Counter advantage: 2.0× for favorable matchups (countered: 0.5×)

Winner = Higher total strength
```

**Casualties (Strength-Scaled):**
- Winner casualties = `loser_count * (loser_strength / winner_strength)`
- Dominant forces lose far fewer units (counters matter)
- Minimum 1 casualty per battle
- Equal strength → casualties = loser count (1:1 trade)
- 6.5:1 advantage → ~15% of loser count as casualties
- Winner keeps territory

**Casualty Priority (Veterancy-Aware):**
- PRIMARY: Level ASC (lowest-level units die first)
- SECONDARY: Counter tier ASC (countered → neutral → advantaged within same level)
- High-level veterans survive battles over raw recruits, regardless of unit type

---

## 🎖️ Veterancy System

**Unit XP & Leveling:**
- Units start at Level 0 with 0 XP
- Maximum level: 5
- XP thresholds per level: 30, 45, 50, 55, 60 (cumulative: 30, 75, 125, 180, 240)
- Each level grants +15% effective strength (Level 5 = +75%)

**XP Sources (Units):**
- Battle victory: Each surviving unit earns `(10 + enemy_level)` XP per enemy killed
- Hero Keep destruction: +100 XP flat bonus to all survivors when destroying a Keep containing a Hero
- Only winners gain XP; losers and retreaters earn nothing

**Building XP (Farms/Mines):**
- Farms and Mines gain +20 XP per turn passively
- Same level thresholds as units: 30/75/125/180/240 cumulative
- Each level grants +10% income bonus (Level 5 = +50%)
- Income bonus applied to base building value BEFORE tech multipliers
- Newly completed buildings skip XP on their first turn

**XP Preservation:**
- Unit XP carries through army movement via animation pipeline
- Unit XP preserved through reinforcements, ally reinforcements, and conquests
- Building XP cleaned up when buildings are destroyed
- Champion of the People preserves Farm/Mine XP for saved buildings

**UI Display:**
- Army composition grid: brass XP bars below each unit, golden shield icons above per level
- Building info panel: XP bars and shields for selected Farms/Mines
- Tooltips show "Level X | XP: current/next" and bonus percentages

---

## 💰 Economic System

**Income Sources:**

1. **Base Income**
   - Each territory has base income based on economic tier
   - Tier 1: 10g, Tier 2: 15g, Tier 3: 20g per turn
   - 25 tier-1 / 19 tier-2 / 13 tier-3 territories (57 total)
   - Defined in `economic_data.json`, mapped via `TIER_INCOME` in `map_data.py`

2. **Buildings**
   - Farm: +10 gold/turn (base, before veterancy/tech bonuses)
   - Mine: +15 gold/turn (base, before veterancy/tech bonuses)
   - Square: 1.5× multiplier on territory income
   - Total from all owned territories

**Income Collection:**
- Happens in Income Phase
- Automatic
- Added to player_gold

**Taxation:**
- Optional game setting (configured at game setup)
- 5 levels: 0% (No Tax), 25%, 50%, 75%, 100%
- Applied at turn end BEFORE income collection
- Deducts percentage of leftover gold from previous turn
- Encourages spending resources each turn
- Cannot be changed mid-game
- Visible in top panel during gameplay (if > 0%)
- Example (50% tax):
  - End turn with 100 gold → 50 gold lost to tax → 50 remaining
  - Collect 40 income → 90 total gold for next turn

**Spending:**
- Buildings cost gold (immediately)
- Recruitment costs gold (immediately)
- Must have sufficient gold
- Cannot go into debt

**Starting Gold:** 100 gold per player

---

## 🏆 Territorial Bonus System

**Overview:**
Each of the 57 territories on the map grants one permanent bonus to its owner. Bonuses stack globally and apply to all player actions.

**9 Bonus Types:**

1. **Income Bonus** (+3% per territory)
   - Applied to total income after all sources calculated
   - Example: Own 2 income territories → +6% total income
   - Stacks multiplicatively with other income bonuses

2. **Technology Research Cost** (-5% per territory)
   - Reduces cost of all technology research
   - Example: Own 3 tech territories → -15% research costs
   - Displayed in tech tooltip costs

3. **Unit Training Cost** (-5% per territory)
   - Reduces cost of Swordsman, Archer, Pikeman, Cavalry training
   - Does not affect heroes
   - Example: Own 2 unit cost territories → -10% unit costs

4. **Hero Training Cost** (-3% per territory)
   - Reduces cost of hero recruitment
   - Separate from unit costs for balance
   - Example: Own 3 hero territories → -9% hero costs

5. **Pikeman Strength** (+10% per territory)
   - Increases Pikeman effective strength in combat
   - Only applies to Pikeman units
   - Example: Own 2 pikeman territories → +20% Pikeman strength

6. **Archer Strength** (+10% per territory)
   - Increases Archer effective strength in combat
   - Only applies to Archer units
   - Stacks with other combat bonuses

7. **Swordsman Strength** (+10% per territory)
   - Increases Swordsman effective strength in combat
   - Only applies to Swordsman units
   - Applied to base strength before multipliers

8. **Cavalry Strength** (+10% per territory)
   - Increases Cavalry effective strength in combat
   - Only applies to Cavalry units
   - Most powerful due to cavalry base strength

9. **Building Cost** (-15% per territory)
   - Reduces cost of all buildings (Farm, Mine, Barracks, Keep, Square)
   - Highest discount percentage for strategic importance
   - Example: Own 2 building territories → -30% building costs

**How Bonuses Work:**

- **Global Application:** Bonuses apply to all actions across your empire
- **Automatic Updates:** Bonuses recalculate each turn based on current territory ownership
- **Conquest Benefits:** Capturing a bonus territory grants benefits starting next turn
- **Loss Penalties:** Losing a bonus territory removes benefits starting next turn
- **Stacking:** Multiple territories with same bonus stack additively (2× +3% = +6%)
- **Cost Floor:** Costs cannot go below 1 gold (minimum cost enforced)

**Strategic Considerations:**

- **Early Game:** Focus on income and unit cost bonuses for economic advantage
- **Mid Game:** Tech cost bonuses accelerate technology research
- **Late Game:** Strength bonuses can turn battles decisively
- **Multiplayer:** Denying opponent bonuses is as important as gaining your own
- **Balance:** Each bonus type distributed across 3-5 territories for fairness

**UI Display:**

- **Bonus Button:** Located in top panel (right of phase indicator)
  - Hover to see active bonuses
  - Shows summed totals (e.g., "+6% Income" from 2 territories)
  - Always displays YOUR bonuses (not opponent's, even on their turn)
  - Works regardless of which player slot you're in (Player 1-4)
  - In multiplayer: Shows your bonuses only

- **Territory Info:** Bottom panel shows territory's bonus type when selected
  - Example: "Bonus: +3% Income"
  - Helps identify valuable conquest targets

**Assignment:**
- Territory bonuses are pre-configured in `territory_bonuses.json`
- Can be modified using `Bonus_Tool.py` (development tool)
- All 57 territories must have exactly one bonus assigned

---

## 📝 Order System

**Movement Orders:**
- Queue multiple movements
- Execute in Orders Phase
- Can cancel before executing
- Visual arrows show planned moves

**Building Orders:**
- One building per turn max
- Queue system (sequential)
- Automatic execution
- Progress tracked in sidebar

**Recruitment Orders:**
- Immediate effect (added next turn)
- Must have Barracks
- Pay gold upfront
- Units appear in territory

---

## 🎯 Victory Conditions

**Implemented:**
- **Domination (45+):** Control 45 or more territories (default)
  - **Team-based:** Combined team territories count toward threshold
  - Solo players win at 45+ individually
- **Capital Assault:** Capture enemy capital territories to eliminate them
  - Players are eliminated when an **enemy** captures their starting capital
  - Allies cannot eliminate each other (team protection)
  - Territory of eliminated player becomes neutral
- **Total Conquest:** Control all 57 territories
  - **Team-based:** Combined team territories count toward total
  - Solo players must own all territories individually

**Team Victory Logic:**
- Domination/Total Conquest aggregate territory counts per team
- Only enemies can trigger Capital Assault eliminations
- First team member with active territories represents winning team

**Planned:**
- Economic: Reach gold threshold
- Quest: Complete quest chain

---

## 👥 Player System

**Players 1-8:**
- Each has unique color
- Independent economies
- Simultaneous turns (implemented)
- Multiplayer supported (2-4 players)

**Neutral (Player 0):**
- Starting territories
- No actions
- Can be conquered
- No income

---

## 🔄 Phase Details

### **Planning Phase**
- Give all orders
- Build buildings
- Recruit armies
- Review situation
- Click "End Turn" → Orders Phase

### **Orders Phase**
- Automatic execution
- Movement orders execute
- Building construction advances
- Units recruited
- → Battles Phase

### **Battles Phase**
- All conflicts detected
- Battle markers shown
- Player resolves each battle
- Click "Continue" → Income Phase

### **Income Phase**
- Calculate income
- Add gold to players
- Show notifications
- Increment turn
- → Planning Phase

---

## 🎲 Deterministic Combat

**No Random Numbers:**
- Same inputs → same result
- Predictable outcomes
- Strategic planning possible
- Composition matters

**Factors:**
- Unit types, counts, and counter matchups
- Keep defense (+2 effective armies)
- Unit veterancy (up to +75% at level 5)
- Territorial strength bonuses

---

## 📊 UI Elements

**Top Panel:**
- Menu button
- Gold display
- Income display
- FPS counter (optional)

**Bottom Panel:**
- End Turn button
- Build button
- Recruit button
- Phase indicator

**Right Sidebar:**
- Technology tab
- Heroes tab
- Action Queue (orders)
- Action Log (events)
- Chat tab

**Territory Info Panel:**
- Shows selected territory
- Owner, armies, income
- Buildings list
- Quick actions

---

## ⌨️ Controls

**Mouse:**
- Left click: Select/Order
- Right click: Deselect
- Mouse wheel: Zoom
- Middle drag: Pan camera

**Keyboard:**
- Arrow keys: Pan camera
- +/-: Zoom
- Space: End Turn
- Esc: Cancel/Close
- C: Chat
- M: Menu

---

## 🌐 Multiplayer System

Full 2-4 player multiplayer with AI slots, teams, and reconnection support.

### Getting Started

**Hosting a Game:**
1. Main Menu → Multiplayer → Host
2. Wait for players or configure AI slots
3. Set game options (Victory, Taxation, Turn Mode)
4. Click Launch when ready

**Joining a Game:**
1. Main Menu → Multiplayer → Join
2. Enter host's IP address
3. Wait in lobby for host to launch

### Lobby System

**Player Slots (4 total):**
| Slot | Type Options | Notes |
|------|--------------|-------|
| Slot 0 | Human (Host) | Always the host player |
| Slot 1-3 | Human / AI (Easy/Medium/Hard) / Empty | Configurable by host |

**Slot Configuration:**
- **Type**: Human waits for player, AI plays automatically, Empty removes slot
- **Color**: Each player picks unique color (Red/Blue/Green/Yellow)
- **Team**: Alliance grouping (Team 1-4, or FFA)
- **Territory**: Starting capital selection

**Territory Selection:**
- Click map to claim starting territory
- First-come-first-served (timestamp tiebreaker)
- Host can reassign territories
- All players must select before launch

### Teams & Alliances

**Team Benefits:**
- Shared vision of ally movement orders (dashed arrows)
- Cannot attack allied territories
- Allied captures trigger ownership choice popup
- Allied defense combines all armies

**Alliance Mechanics:**
- Same team = allies
- Different team = enemies
- Team can be changed only in lobby

### Host Authority

The host (Player 0) is authoritative:
- Runs all game logic and AI
- Resolves all battles
- Broadcasts state changes to clients
- Controls game flow and timing

**Host-Only Actions:**
- Kick players from lobby
- Configure AI slots
- Change game settings
- Launch game
- End/pause game

### Disconnect Handling

**Client Disconnects:**
1. AI immediately takes over (Medium difficulty)
2. Player can reconnect within 5 minutes
3. Password shown on initial join (save it!)
4. Game continues without interruption

**Host Disconnects:**
- Game ends for all players
- Disconnect dialog shown to clients
- Players return to main menu

**Reconnection:**
1. Join same host IP
2. Enter your name + password
3. Resume control from AI
4. Full state synchronized

### Network Messages

**Lobby Messages:**
- `LOBBY_STATE` - Full lobby sync
- `LOBBY_JOIN/LEAVE` - Player joined/left
- `LOBBY_KICK` - Player kicked by host
- `LOBBY_SLOT_UPDATE` - Slot configuration changed
- `LOBBY_LAUNCH` - Game starting

**Game Messages:**
- `MOVEMENT_ORDER` - Army movement queued
- `BUILDING_ORDER` - Building construction started
- `TRAINING_ORDER` - Unit training queued
- `BATTLE_RESOLVE` - Battle outcome
- `TURN_END` - Turn completed

**Simultaneous Mode Messages:**
- `SIM_PLAYER_READY` - Player finished planning
- `SIM_ALL_READY` - All players ready, execute
- `SIM_ALLIANCE_CHOICE` - Territory owner selection
- `SIM_ROUND_COMPLETE` - Round finished

### UI Indicators

**Lobby:**
- Player names with colors
- Ready status per player
- Host controls highlighted
- Launch button (host only)

**In-Game:**
- Allied movement arrows (dashed)
- Battle markers sync across clients
- Timer synced in simultaneous mode
- "Waiting for: X, Y" shows pending players

### Technical Details

**Connection:**
- TCP sockets with length-prefix framing
- Default port: 7777
- Heartbeat every 5 seconds
- Timeout after 15 seconds no response

**Synchronization:**
- Host-authoritative model
- All game logic runs on host
- Clients receive state updates
- Checksum validation (optional)

---

## 🔄 Simultaneous Turn Mode

An alternative game mode where all players plan at the same time.

### Game Setup

Select "Turn Mode: Simultaneous" in the game setup screen. Available in both single-player and multiplayer.

### Phase Flow

```
┌─────────────────────────────────────────┐
│  PLANNING PHASE                          │
│  - All players queue orders at once      │
│  - Your orders are hidden from others    │
│  - Timer counts down (60s base)          │
│  - Click "End Turn" when ready           │
│  - Wait for other players                │
└─────────────────────────────────────────┘
                  ▼
┌─────────────────────────────────────────┐
│  EXECUTION PHASE                         │
│  - All movements happen simultaneously   │
│  - UI is view-only                       │
│  - Watch flags move across map           │
└─────────────────────────────────────────┘
                  ▼
┌─────────────────────────────────────────┐
│  RESOLUTION PHASE                        │
│  - Crossing army conflicts resolved      │
│  - Battles resolved                      │
│  - Alliance arrivals handled             │
│  - Income collected                      │
└─────────────────────────────────────────┘
                  ▼
            Next Round
```

### Timer System

| Setting | Value |
|---------|-------|
| Base timer | 60 seconds |
| Master Planner I | +30 seconds |
| Master Planner II | +30 seconds (total 120s) |

Timer is always enabled in simultaneous mode. Only your own timer is visible.

### Crossing Armies

When two players order armies to attack each other's territory (A→B while B→A):

- **Stronger army** → Attacks (moves to destination)
- **Weaker army** → Forced to defend (stays in place)
- **Equal strength** → Dice roll determines attacker
- Defender receives popup notification

### Alliance Arrivals

When multiple allied armies capture the same territory:

1. Blue particle marker appears (not red battle marker)
2. Biggest army owner clicks to choose territory recipient
3. Polished UI popup shows "Choose the Territory Owner"
4. Player names displayed in their player color
5. All armies stay in territory with original owners
6. If army limit exceeded → overflow warning (1 turn to move)

### Defensive Battles

When allies defend a territory together against attackers:

- **Original owner retains control** if defenders win
- No alliance choice popup appears (defensive victory)
- Attacker shown on LEFT side of battle interface
- Defenders (owner + allies) shown on RIGHT side

### Newly Trained Units

Units spawning from Barracks in simultaneous mode:

- Start with **"Moved" status** (cannot move on spawn turn)
- Become **"Ready to Move"** at the start of the next round
- Exception: **Haste ability** makes units ready immediately

### Key Differences from Sequential Mode

| Feature | Sequential | Simultaneous |
|---------|-----------|--------------|
| Turn order | One player at a time | All players at once |
| Order visibility | All see all orders | Orders hidden until execution |
| Timer | Optional | Always enabled (per-player) |
| Movement | One army at a time | All armies at once |
| End Turn button | Ends your turn | Marks you as ready |
| Phase ends | After each player | When ALL players ready |

### UI Indicators

- **Waiting...** button: Shows when you've clicked End Turn
- **Waiting for: X, Y** text: Lists players still planning
- **Blue particle marker**: Alliance arrival (click to assign territory)
- **Red glow on flag**: Overflow warning (move armies or they disband)

---

**Last Updated:** February 27, 2026
