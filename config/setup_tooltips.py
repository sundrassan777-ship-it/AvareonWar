# -*- coding: utf-8 -*-
"""
Hover tooltips on the game setup screens (Custom Game + multiplayer lobby).

Edit the wording here — both screens read this file. Each tooltip is:

    'key': {
        'title': "Shown in gold at the top",
        'entries': [
            ("Term", "Explanation."),      # term in bold, explanation after it
            (None, "A plain paragraph."),  # no term
        ],
    }

Lines wrap automatically to the tooltip width. Where each one shows:
- turn_mode / taxation / victory: hovering the "Turn Mode:", "Taxation Level:" and
  "Victory Condition:" labels (or the small (i) mark next to them) on the left panel
- neutral_armies / randomize_bonuses / gold_transfer / starting_gold: hovering the
  option's name in the Additional Options window
"""

SETUP_TOOLTIPS = {
    # Left panel ------------------------------------------------------------
    'turn_mode': {
        'title': "Turn Mode",
        'entries': [
            ("Sequential", "Players take their turns one after another. You see every "
                           "move the moment it happens."),
            ("Simultaneous", "Everyone plans at the same time against a timer, with orders "
                             "hidden. When all players end their turn, the orders play out "
                             "together and the battles are fought."),
        ],
    },
    'taxation': {
        'title': "Taxation Level",
        'entries': [
            (None, "At the end of every turn, this share of the gold you did not spend is "
                   "lost to taxes, before your income arrives."),
            (None, "Higher taxes reward spending your gold each turn instead of saving it."),
            ("Example (50%)", "Ending the turn with 100 gold leaves 50."),
        ],
    },
    'victory': {
        'title': "Victory Condition",
        'entries': [
            ("Domination", "Control about four fifths of the map's territories "
                           "(45 on Avareon). Allies count together."),
            ("Capital Assault", "A player is eliminated when an enemy captures their "
                                "starting territory. The last side standing wins."),
            ("Total Conquest", "Control every territory on the map. Allies count together."),
        ],
    },

    # Additional Options window ---------------------------------------------
    'neutral_armies': {
        'title': "Neutral Armies",
        'entries': [
            (None, "Unclaimed territories start with small garrisons that defend when "
                   "attacked: 1 unit next to a starting territory, 2 elsewhere."),
            (None, "They never move or grow, and once defeated they are gone for good."),
        ],
    },
    'randomize_bonuses': {
        'title': "Randomize Territory Bonuses",
        'entries': [
            (None, "Shuffles which territory grants which bonus, so the best targets "
                   "change every game. Each bonus type still appears equally often."),
        ],
    },
    'gold_transfer': {
        'title': "Gold Transfer",
        'entries': [
            (None, "Lets players send gold to their allies from the Players window, once "
                   "per ally each turn."),
            (None, "The percentage is the most of your current gold one transfer may send."),
        ],
    },
    'starting_gold': {
        'title': "Starting Gold",
        'entries': [
            (None, "The gold every player begins the game with. The standard game uses 100."),
        ],
    },
}
