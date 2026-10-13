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

    # Multiplayer lobby: hovering the "Join IP:" label (host only). Which one shows
    # depends on whether the router forwarded the game port (UPnP).
    'host_ip_pending': {
        'title': "Join Address",
        'entries': [
            (None, "Setting up internet access with your router. Players on your own "
                   "network can already join with this address."),
        ],
    },
    'host_ip_lan': {
        'title': "Join Address",
        'entries': [
            ("Same network", "Players on your Wi-Fi or home network join with this "
                             "address. If it times out, check that both PCs use the same "
                             "network (not a guest Wi-Fi), that the router does not keep "
                             "Wi-Fi devices apart, and that no VPN is on."),
            ("Over the internet", "Your router did not open the game port automatically "
                                  "(UPnP). Forward TCP port 7777 to this PC in your router "
                                  "settings; players then join with your public IP. Steam "
                                  "invites include both addresses."),
        ],
    },
    'host_ip_internet': {
        'title': "Join Address",
        'entries': [
            (None, "Your router opened the game port, so players anywhere can join with "
                   "this address. Steam invites include it."),
        ],
    },

    # Multiplayer lobby: hovering the Steam note after the join address (host only):
    # host_steam ("or via Steam") while friends can join through Steam, host_steam_off
    # ("Steam off") when they cannot.
    'host_steam': {
        'title': "Joining Through Steam",
        'entries': [
            (None, "Your Steam friends can join this lobby without the IP address and "
                   "without port forwarding: Steam connects you, on any network."),
            ("How", "Invite them with Invite Friend, or they choose you on the Steam Friends "
                    "tab of their Join Game screen, or with Join Game on your name in their "
                    "Steam friends list."),
        ],
    },
    'host_steam_off': {
        'title': "Joining Through Steam",
        'entries': [
            (None, "Friends can only join this lobby with the IP address right now. "
                   "Joining through Steam needs Steam running and online when the game "
                   "starts."),
            (None, "It is also off when the --no-steam-relay launch option is set, or "
                   "\"steam_relay\": false in config.json."),
        ],
    },

    # Multiplayer lobby: hovering the greyed "Launch Game" button (host only).
    # One entry per reason in network/lobby.py LobbyState.launch_blocker().
    'launch_players': {
        'title': "Not Ready to Launch",
        'entries': [
            (None, "A game needs at least two players. Wait for a friend to join, or set "
                   "an empty slot to an AI."),
        ],
    },
    'launch_gap': {
        'title': "Not Ready to Launch",
        'entries': [
            (None, "Players must fill the slots from the top, with no empty slot between "
                   "them. Set the empty slot to an AI, wait for a player to join it, or "
                   "empty the slots below it."),
        ],
    },
    'launch_teams': {
        'title': "Not Ready to Launch",
        'entries': [
            (None, "Everyone is on the same team, so there would be nobody to fight. Put "
                   "at least one player on another team."),
        ],
    },
    'launch_territories': {
        'title': "Not Ready to Launch",
        'entries': [
            (None, "Every player needs a starting territory. For an AI, click its row and "
                   "then a territory on the map."),
        ],
    },
}
