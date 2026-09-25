# -*- coding: utf-8 -*-
# config/action_error_messages.py
# Every player-facing "action refused" message, in one place.

"""
Action Error Messages
=====================

When the game refuses an action the player tried (not enough gold, target out of
reach, ...), it plays the denial sound and shows one of these messages as a red
notification in the top-left corner of the map.

HOW TO EDIT
-----------
- Change only the text between the quotes. The comment above each line says
  exactly when the player sees that message.
- The word before the colon (e.g. 'gold') is an internal code the game looks up.
  Do not change it.
- Words in {curly braces} are filled in by the game (e.g. {territory} becomes
  "Lobardia"). Keep them if you want the value shown, or delete them. Don't add
  new ones: an unknown {name} is shown as-is instead of being filled in.
- \\n starts a new line inside the notification.

Code: add a failure by setting game_state.last_action_error = '<code>' (and
optionally last_action_error_args = {...} for the {placeholders}) before the
method returns False, then call Game._show_action_failure_feedback() at the call
site. Or call Game.show_action_error('<code>', name=value) directly.
"""

import logging

logger = logging.getLogger(__name__)


ACTION_ERROR_MESSAGES = {

    # =====================================================================
    # A. TRAINING, BUILDING, RESEARCH, HEROES
    # =====================================================================

    # Clicking to build, train a unit, research a technology, train a hero or
    # upgrade a Keep to a Castle without enough gold.
    'gold': "Not enough resources!",

    # Training a unit when your total unit count has reached your Command Limit
    # (the cap on all your units across the map).
    'command_limit': "Cannot train more units — Command Limit reached!",

    # Training a unit in a territory that already holds 15 armies
    # (units still in the training queue don't count).
    'army_limit': "Army limit reached in this territory!",

    # Training a unit when that Barracks already has 4 units queued.
    'queue_full': "Training queue is full!",

    # Training a hero when you already have the maximum number of heroes.
    'hero_limit': "Hero limit reached!",

    # Pressing a build shortcut key (F/M/B/K/Q/T) while the selected plot
    # already has a building, or a building under construction.
    'plot_occupied': "This plot is already in use!",

    # =====================================================================
    # B. ARMY ORDERS (right-clicking a territory with units selected)
    # =====================================================================

    # Sending units to your own or an allied territory would push it above
    # the army limit. {territory} = target, {limit} = the limit (15).
    'reinforce_limit': "Cannot reinforce {territory}: would exceed army limit of {limit}!",

    # The target territory doesn't border the units' territory (and there is
    # no valid 2-step route for a Captain).
    'not_adjacent': "Cannot reach target territory!",

    # At least one selected unit has already moved this turn (its icon is
    # greyed out in the army strip).
    'unit_not_ready': "Some selected armies are not ready to move!",

    # Campaign Mission 6: the target territory is locked by the story for now.
    # {territory} = target.
    'target_blocked': "Cannot target {territory} yet!",

    # Simultaneous mode: trying to give an order or start research while
    # battles are being resolved.
    'wrong_phase': "Cannot do that while battles are resolving!",

    # =====================================================================
    # C. HERO ABILITIES - shared messages (shown after clicking an ability and
    #    then a target territory; targeting stays on so you can pick again)
    # =====================================================================

    # Relentless Charge, Levy, Valorous Charge (they only work on your own
    # land): the target is an enemy, allied or neutral territory.
    'ability_not_own_territory': "You can only target your own territories!",

    # Aggressive Diplomacy, Decisive Strike, Royal Charisma, Regicide (they
    # only work on other players' land): the target is your own territory.
    'ability_own_territory': "Cannot target your own territory!",

    # Decisive Strike, Royal Charisma, Regicide: the target has no owner
    # (grey territory).
    'ability_neutral': "Cannot target neutral territory!",

    # Aggressive Diplomacy, Decisive Strike, Royal Charisma, Regicide: the
    # target is shielded by an enemy hero's Defiance ability.
    'ability_defiance': "Territory is protected by Defiance!",

    # =====================================================================
    # D. HERO ABILITIES - one message per ability
    # =====================================================================

    # Relentless Charge (summons 4 Cavalry into your territory): the target
    # already has 12+ units, so 4 more wouldn't fit. {current} = its units.
    'charge_too_many': "Territory has too many units! ({current}/15)\nNeed 11 or fewer to summon 4 Cavalry.",

    # Reinforce (summons 2 Swordsmen at the hero's Keep, no target click): the
    # hero's Keep territory already has 14+ units. {current} = its units.
    'reinforce_too_many': "Territory has too many units! ({current}/15)\nNeed 13 or fewer to summon 2 Swordsmen.",

    # Aggressive Diplomacy (takes over a weakly held territory): the target has
    # 2 or more armies. {current} = its armies.
    'diplomacy_too_many': "Territory has too many armies! ({current})\nNeed 1 or fewer to target.",

    # Aggressive Diplomacy: the target has a Keep or Castle.
    'diplomacy_keep': "Cannot target territories with Keeps!",

    # Aggressive Diplomacy, Campaign Mission 6 only: the target is locked by
    # the story for now.
    'diplomacy_blocked': "Cannot take over that territory yet!",

    # Decisive Strike (kills half the units in an enemy territory): the target
    # has fewer than 2 units. {count} = its units.
    'strike_min_units': "Territory must have at least 2 units! (has {count})",

    # Valorous Charge (moves units from the hero's Keep to another of your
    # territories): you clicked the hero's own Keep territory.
    'valorous_own_keep': "Cannot target hero's own Keep territory!",

    # Valorous Charge: the hero's Keep territory has no units to send.
    # {keep} = the Keep's territory.
    'valorous_no_units': "No units in {keep} to move!",

    # Valorous Charge: the destination already has 15 units.
    # {territory} = destination, {count} = its units.
    'valorous_full': "{territory} is full! ({count}/15)",

    # Royal Charisma (steals up to 5 enemy units into Aidam Narn's Keep): an
    # enemy has captured the territory where Narn's Keep is.
    'charisma_keep_lost': "You no longer own Narn's Keep territory!",

    # Royal Charisma: Narn's Keep territory already has 15 units, so there is
    # no room for stolen units.
    'charisma_keep_full': "Narn's Keep already has 15 units! Cannot use Royal Charisma.",

    # Royal Charisma: the target territory has no units to steal.
    'charisma_no_units': "Target territory has no units!",

    # Regicide (kills the enemy hero in a Keep): the target has no Keep.
    'regicide_no_keep': "Target territory must have a Keep!",

    # Regicide: the target has a Keep but no hero inside. The ability still
    # goes on cooldown (by design: Regicide has to hit a hero).
    'regicide_no_hero': "Regicide failed — no hero present!",

    # =====================================================================
    # E. OTHER
    # =====================================================================

    # Players window: clicking Send (or pressing Enter) with the gold amount
    # empty or 0.
    'transfer_no_amount': "Enter an amount of Gold to send!",

    # =====================================================================
    # F. RARE SAFETY MESSAGES (practically never shown - only if the game's
    #    data is out of sync). You can leave these alone.
    # =====================================================================

    # The ability target isn't a known territory.
    'ability_invalid_territory': "Invalid territory!",

    # The hero using the ability can't be found (e.g. it just died).
    'hero_not_found': "Hero not found!",

    # Decisive Strike: the unit counter says 2+, but no units are found.
    'strike_no_armies': "No armies found in territory!",

    # Decisive Strike: fewer units found than the counter reported.
    'strike_not_enough': "Not enough units in territory!",

    # Valorous Charge: 0 units can move after the limits are applied.
    'valorous_none_movable': "No units can be moved!",
}

# Shown for a code that is missing from the table above (a programming slip).
DEFAULT_ACTION_ERROR = "Action failed!"


def format_action_error(code, **fmt):
    """
    Look up the message for `code` and fill in its {placeholders}.

    Never raises: an unknown code falls back to DEFAULT_ACTION_ERROR, and a text
    whose placeholders don't match (e.g. edited to use a new {name}) is shown
    unformatted, with a warning in the log, rather than crashing the game.
    """
    text = ACTION_ERROR_MESSAGES.get(code)
    if text is None:
        logger.warning(f"Unknown action error code {code!r}")
        return DEFAULT_ACTION_ERROR
    try:
        return text.format(**fmt)
    except (KeyError, IndexError, ValueError) as e:
        logger.warning(f"Action error {code!r}: could not fill placeholders ({e}); showing raw text")
        return text
