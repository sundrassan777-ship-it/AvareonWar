# Multiplayer Simultaneous Mode - Testing Plan

**Created:** 2026-02-01
**Purpose:** Verify all sync fixes work correctly without breaking existing functionality

---

## Test Configuration Options

| Config | Players | Mode | Network |
|--------|---------|------|---------|
| **A** | 1 Human vs 1-3 AI | Simultaneous | Local (single-player) |
| **B** | 2 Human | Simultaneous | Multiplayer (host + 1 client) |
| **C** | 1 Human vs 1-3 AI | Sequential | Local (single-player) |

---

## PART 1: Regression Tests (Must Pass Before New Features)

### Test 1.1: Sequential Mode Still Works
**Config:** C (1 Human vs 1 AI, Sequential)

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Start new game: Sequential mode, 1 human vs 1 AI | Game starts, human is Player 1 |
| 2 | End turn without actions | AI takes its turn, timer shows AI thinking |
| 3 | Build a Farm | Farm construction starts, gold deducted |
| 4 | End turn | Farm progress advances |
| 5 | Train a unit at Barracks | Training starts |
| 6 | Attack AI territory with 2+ armies | Battle popup appears |
| 7 | Resolve battle | Winner determined, territory changes hands |
| 8 | End turn | Income collected, construction/training progress |

**Pass Criteria:** All steps complete without errors, AI takes turns normally

---

### Test 1.2: Simultaneous Single-Player Still Works
**Config:** A (1 Human vs 1 AI, Simultaneous)

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Start new game: Simultaneous mode, 1 human vs 1 AI | Game starts with timer countdown |
| 2 | Queue movement order | Arrow appears on map |
| 3 | Queue building order | Build icon appears on plot |
| 4 | Click "Ready" button | Player marked ready |
| 5 | Wait for AI to ready (or timer expires) | AI marks ready, execution starts |
| 6 | Watch movement animations | Armies move simultaneously |
| 7 | Observe battle markers (if conflict) | Battle markers appear |
| 8 | Resolve any battles | Battles resolve, round completes |
| 9 | New planning phase starts | Timer resets, can queue new orders |

**Pass Criteria:** AI marks ready, execution works, round completes correctly

---

### Test 1.3: Basic Multiplayer Connection
**Config:** B (2 Human, Simultaneous)

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Host starts multiplayer game | Lobby appears |
| 2 | Client joins lobby | Both players see each other |
| 3 | Host selects territory | Territory claimed for host |
| 4 | Client selects territory | Territory claimed for client |
| 5 | Host launches game | Both enter game |
| 6 | Both players see same map state | Territory ownership matches |

**Pass Criteria:** Both players connected and see same initial state

---

## PART 2: Sync Fix Tests

### Test 2.1: Unit Composition Preserved After Battle (Issue #6)
**Config:** A or B (any Simultaneous mode)

**Setup:**
- Player has territory with mixed units (Swordsman + Archer + Pikeman)
- Train different unit types at Barracks before this test

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Note unit composition in territory | e.g., "2 Swordsman, 1 Archer, 1 Pikeman" |
| 2 | Attack enemy/neutral territory | Movement order created |
| 3 | Execute phase completes | Battle occurs |
| 4 | Win the battle | Territory captured |
| 5 | Check surviving unit composition | **Should NOT be all Swordsmen** |
| 6 | Hover over new territory | Unit types preserved (Archer, Pikeman visible) |

**Pass Criteria:** After battle, surviving units keep their original types (not all Swordsmen)

**For Multiplayer (Config B):** Both host AND client should see same unit composition

---

### Test 2.2: Alliance Chooser Deterministic (Issue #2)
**Config:** B (2 Human, Simultaneous, Allied/Same Team)

**Setup:**
- Both players on same team (alliance)
- Both players have armies adjacent to same neutral territory

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Player 1 queues attack on neutral Territory X | Arrow shows |
| 2 | Player 2 queues attack on same Territory X | Arrow shows |
| 3 | Make sure both have EQUAL army counts | e.g., both send 3 armies |
| 4 | Both mark ready | Execution starts |
| 5 | Armies arrive simultaneously | Alliance marker appears (blue) |
| 6 | Check who is the "chooser" | **Lower player index should be chooser** |
| 7 | Host sees Player 1 (index 0) as chooser | Correct |
| 8 | Client sees Player 1 (index 0) as chooser | **Same as host** |

**Pass Criteria:** With equal armies, lowest player index is always chooser (deterministic, not random)

---

### Test 2.3: Hero Ability Execution (Issue #3)
**Config:** A (1 Human vs AI, Simultaneous)

**Setup:**
- Player has a Hero trained (e.g., Brennhen with "Reinforce" ability)
- Hero ability is off cooldown

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Open Hero panel | Hero abilities visible |
| 2 | Click hero ability (e.g., Reinforce) | Ability executes **immediately** (real-time) |
| 3 | Verify effect appears instantly | Reinforce: 4 Swordsmen spawn in Keep territory |
| 4 | Verify ability on cooldown | Cooldown indicator shows immediately |
| 5 | (Optional) If silenced, ability button disabled | Vow of Silence blocks ability use |

**Note:** Hero abilities execute in real-time during planning phase, NOT queued for execution.
This allows for tactical counterplay (e.g., Vow of Silence must be used before enemy abilities).

**Pass Criteria:** Hero ability executes immediately on click, effect visible, cooldown applied

---

### Test 2.4: Hero Training Execution (Issue #4)
**Config:** A (1 Human vs AI, Simultaneous)

**Setup:**
- Player has a Keep (not Castle)
- Enough gold for hero training

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Click on Keep | Keep panel opens |
| 2 | Click hero to train | Training starts **immediately** (real-time) |
| 3 | Verify gold deducted | Gold reduced by hero cost |
| 4 | Verify training indicator | Keep shows training in progress |
| 5 | Complete required rounds | Training timer counts down each round |
| 6 | Hero completes | Hero appears in Heroes panel |

**Note:** Hero training starts immediately on click (gold deducted, training begins).
The training process takes multiple rounds to complete.

**Pass Criteria:** Hero training starts immediately on click, completes after required rounds

---

### Test 2.5: Authoritative Gold Sync (Issue #10)
**Config:** B (2 Human, Simultaneous)

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Note both players' starting gold | e.g., Host: 50, Client: 50 |
| 2 | Host builds Farm (costs gold) | Gold deducted locally |
| 3 | Client builds Farm | Gold deducted locally |
| 4 | Both mark ready | Execution phase |
| 5 | Round completes | Income collected |
| 6 | Host checks client's gold (if visible) | Should match client's view |
| 7 | Client checks their gold | Should match host's authoritative value |

**Pass Criteria:** After SIM_ROUND_COMPLETE, gold values are synchronized

**Verification (console logs):**
Look for: `[NETWORK] Sync: Player X gold Y -> Z` (indicates correction applied)

---

### Test 2.6: Forced Defend Notification (Issue #7)
**Config:** B (2 Human, Simultaneous)

**Setup:**
- Player 1 has territory A adjacent to territory B
- Player 2 owns territory B, has territory B adjacent to territory A
- Crossing attack scenario

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Player 1 attacks from A to B | Arrow A→B |
| 2 | Player 2 attacks from B to A | Arrow B→A |
| 3 | Make Player 2's army larger | e.g., 5 vs 3 |
| 4 | Both mark ready | Execution starts |
| 5 | Crossing conflict detected | Larger army forces smaller to defend |
| 6 | Player 1 (smaller) forced to defend | Message appears for Player 1 |
| 7 | Player 1's attack is cancelled | Army stays in territory A |

**Pass Criteria:** Forced defend notification sent to affected player

**Console verification:**
Look for: `[HOST] Broadcasting SIM_FORCED_DEFEND`

---

### Test 2.7: Eliminated Players Sync (Issue #16)
**Config:** A (1 Human vs 2 AI, Simultaneous)

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Capture all of AI Player 2's territories | AI eliminated |
| 2 | Check eliminated status | AI should be eliminated |
| 3 | Continue playing | Eliminated AI should not take turns |
| 4 | Income phase | Eliminated player gets no income |
| 5 | Round complete | Eliminated player skipped correctly |

**Pass Criteria:** Eliminated players properly tracked and skipped

---

### Test 2.8: Mark Ready Duplicate Prevention (Issue #22)
**Config:** A or B (any Simultaneous)

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Enter planning phase | Timer counting |
| 2 | Click Ready button | Marked as ready |
| 3 | Rapidly click Ready button multiple times | No additional effect |
| 4 | Check console logs | Only ONE "mark_ready" processed |

**Pass Criteria:** Multiple Ready clicks don't cause multiple callbacks

**Console verification:**
Look for: `[SIM_STATE] Ignoring mark_ready - player X already ready`

---

## PART 3: Multi-Client Validation Tests

### Test 3.1: Player Index Validation
**Config:** B (2 Human, Simultaneous)

This is difficult to test without malformed messages, but verify:

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Client sends movement order | Order accepted by host |
| 2 | Check console for validation | No rejection messages |
| 3 | Order executes correctly | Armies move |

**Console verification:**
Should NOT see: `[NETWORK] REJECTED: Invalid player_index`

---

## PART 4: Stress Tests

### Test 4.1: Rapid Order Queueing
**Config:** B (2 Human, Simultaneous)

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Both players rapidly queue multiple orders | Orders queue without errors |
| 2 | Queue: 3 movements, 2 buildings, 1 training each | All orders visible |
| 3 | Both mark ready quickly | Execution starts |
| 4 | All orders execute | No missing orders |
| 5 | Round completes | State consistent on both sides |

**Pass Criteria:** No lost orders, no crashes, consistent state

---

### Test 4.2: Client Disconnect and AI Takeover
**Config:** B (2 Human, Simultaneous)

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Start multiplayer game | Both connected |
| 2 | Play 1-2 rounds normally | Game working |
| 3 | Client closes game (force quit) | Client disconnects |
| 4 | Host sees disconnect message | AI takes over client's slot |
| 5 | Host continues playing | AI controls disconnected player |
| 6 | Game still playable | No crash |

**Pass Criteria:** Game continues with AI takeover

---

## Test Execution Checklist

### Before Testing
- [ ] Clean build (no cached Python files)
- [ ] Console visible for log monitoring
- [ ] Note starting conditions

### Regression Tests (MUST PASS FIRST)
- [ ] Test 1.1: Sequential Mode Still Works
- [ ] Test 1.2: Simultaneous Single-Player Still Works
- [ ] Test 1.3: Basic Multiplayer Connection

### Sync Fix Tests
- [ ] Test 2.1: Unit Composition Preserved After Battle
- [ ] Test 2.2: Alliance Chooser Deterministic
- [ ] Test 2.3: Hero Ability Execution
- [ ] Test 2.4: Hero Training Execution
- [ ] Test 2.5: Authoritative Gold Sync
- [ ] Test 2.6: Forced Defend Notification
- [ ] Test 2.7: Eliminated Players Sync
- [ ] Test 2.8: Mark Ready Duplicate Prevention

### Multi-Client Tests
- [ ] Test 3.1: Player Index Validation

### Stress Tests
- [ ] Test 4.1: Rapid Order Queueing
- [ ] Test 4.2: Client Disconnect and AI Takeover

---

## Console Log Indicators

**Good Signs (expected):**
```
[SIM_STATE] Player X marked ready
[SIM_PHASE] Executing X orders
[HOST] Broadcasting SIM_ROUND_COMPLETE
[NETWORK] Sync: Player X gold Y -> Z (if correction needed)
```

**Warning Signs (investigate):**
```
[NETWORK] WARNING: ... missing player_index
[SIM_STATE] Ignoring mark_ready - not in planning phase
```

**Error Signs (bugs):**
```
[NETWORK] REJECTED: ...
Traceback (most recent call last):
AttributeError: ...
KeyError: ...
```

---

## Quick Smoke Test (5 minutes)

If short on time, run this minimal test:

1. **Start:** 1 Human vs 1 AI, Simultaneous mode
2. **Round 1:** Queue 1 movement order, click Ready
3. **Verify:** AI marks ready, armies move
4. **Round 2:** Build Farm, train unit, click Ready
5. **Verify:** Construction started, training started
6. **Round 3:** Attack AI territory, click Ready
7. **Verify:** Battle occurs, resolve it
8. **Round 4:** Check unit composition after battle
9. **Verify:** Units not all Swordsmen

**Pass:** Game played 4 rounds without crashes, units preserved types

---

**Last Updated:** 2026-02-01
