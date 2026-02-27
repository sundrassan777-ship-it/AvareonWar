# -*- coding: utf-8 -*-
# data_definitions.py
# Pure data definitions extracted from game_state/__init__.py
#
# Contains: BUILDING_TYPES, HERO_TYPES, BONUS_TYPES, build_technologies()
# These are static data constants and a factory function used by GameState.__init__.

"""
War of Avareon - Game Data Definitions

This module contains pure data definitions (constants and a builder function)
that were extracted from game_state/__init__.py to reduce its size and improve
maintainability.

Contents:
    BUILDING_TYPES: Building costs, effects, and construction times
    HERO_TYPES: Hero definitions with abilities, costs, and training times
    BONUS_TYPES: Territory bonus types and their values
    build_technologies(): Factory function that returns the 21-technology tree
"""

# ============================================================================
# BUILDING_TYPES - Building costs and definitions
# ============================================================================

BUILDING_TYPES = {
    'Farm': {'cost': 30, 'letter': 'F', 'effect': 'income', 'value': 10, 'time': 1},
    'Mine': {'cost': 40, 'letter': 'M', 'effect': 'income', 'value': 15, 'time': 1},
    'Barracks': {'cost': 50, 'letter': 'B', 'effect': 'recruitment', 'value': True, 'time': 1},
    'Keep': {'cost': 100, 'letter': 'K', 'effect': 'defense', 'value': 2, 'time': 2},
    'Square': {'cost': 60, 'letter': 'S', 'effect': 'multiplier', 'value': 1.5, 'time': 1},
    'Training Grounds': {'cost': 50, 'letter': 'T', 'effect': 'training', 'value': 15, 'time': 1},
}

# ============================================================================
# HERO_TYPES - Hero type definitions with abilities
# ============================================================================

HERO_TYPES = {
    'Halon Nextroy': {
        'cost': 400,
        'letter': 'H',
        'name': 'Halon Nextroy',
        'training_time': 4,  # Player turns
        'abilities': [
            {
                'name': 'Aggressive Diplomacy',
                'type': 'active',
                'cooldown': 5,
                'description': 'Target a neutral or enemy territory with 1 or fewer armies and no Keep. Destroy all armies and buildings, claiming the territory. Seledra\'s Champion of the People can save Farms and Mines.',
                'icon': 'assets/heroes/abilities/AggressiveDiplomacyIcon.png'
            },
            {
                'name': 'Levy',
                'type': 'active',
                'cooldown': 3,
                'description': 'Target one of your territories to immediately collect its full income (base income + buildings + multipliers).',
                'icon': 'assets/heroes/abilities/LevyIcon.png'
            },
            {
                'name': 'Extensive Connections',
                'type': 'passive',
                'description': 'Gain 4 Gold per territory owned at the end of your turn.',
                'icon': 'assets/heroes/abilities/ExtensiveConnectionsIcon.png'
            }
        ],
        'description': ['Lord of Rossenburg'],
        'icon': 'assets/heroes/nextroy.png'
    },
    'Aidam Narn': {
        'cost': 600,
        'letter': 'A',
        'name': 'Aidam Narn',
        'training_time': 5,
        'abilities': [
            {
                'name': 'Royal Charisma',
                'type': 'active',
                'cooldown': 7,
                'description': 'Steal up to 5 units from target enemy territory and move them to Narn\'s Keep (respects 15 unit limit). Cannot be used if Narn\'s Keep has 15 units.',
                'icon': 'assets/heroes/abilities/RoyalCharismaIcon.png'
            },
            {
                'name': 'Regicide',
                'type': 'active',
                'cooldown': 6,
                'description': 'Target an enemy Keep. If a hero resides there, instantly kill that hero. If no hero is present, the ability is wasted.',
                'icon': 'assets/heroes/abilities/RegicideIcon.png'
            },
            {
                'name': 'Legacy of the Empire',
                'type': 'passive',
                'description': 'All your territories generate 50% more base income (does not affect Farms, Mines, or Squares).',
                'icon': 'assets/heroes/abilities/LegacyOfTheEmpireIcon.png'
            }
        ],
        'description': ['King of Azincourne'],
        'icon': 'assets/heroes/narn.png'
    },
    'Erec Silvyr': {
        'cost': 250,
        'letter': 'E',
        'name': 'Erec Silvyr',
        'training_time': 2,
        'abilities': [
            {
                'name': 'Extort Populace',
                'type': 'active',
                'cooldown': 3,
                'description': 'Gain 50 Gold for each of your Keeps or Castles.',
                'icon': 'assets/heroes/abilities/ExtortPopulaceIcon.png'
            },
            {
                'name': 'Confiscate',
                'type': 'passive',
                'description': 'When you demolish a Farm or Mine, gain 175% of the cost back instead of 50%.',
                'icon': 'assets/heroes/abilities/Confiscate.png'
            },
            {
                'name': 'Ruthless Ingenuity',
                'type': 'passive',
                'description': 'Technology research takes 1 less turn but costs 33% more Gold.',
                'icon': 'assets/heroes/abilities/RuthlessIngenuity.png'
            }
        ],
        'description': ['Lord of Generax'],
        'icon': 'assets/heroes/silvyr.png'
    },
    'Darius Brennhen': {
        'cost': 150,
        'letter': 'D',
        'name': 'Darius Brennhen',
        'training_time': 2,
        'abilities': [
            {
                'name': 'Reinforce',
                'type': 'active',
                'cooldown': 4,
                'description': 'Summon 2 Swordsmen battalions in the territory of Brennhen\'s Keep (must have 13 or fewer units).',
                'icon': 'assets/heroes/abilities/ReinforcementIcon.png'
            },
            {
                'name': 'Safe Haven',
                'type': 'passive',
                'description': 'When losing a battle in a territory adjacent to Brennhen\'s Keep, one random unit retreats to the Keep\'s territory instead of being destroyed.',
                'icon': 'assets/heroes/abilities/SafeHavenIcon.png'
            },
            {
                'name': 'Scavenge the Fallen',
                'type': 'passive',
                'description': 'Gain 30 Gold whenever you lose a battle (does not trigger when an empty territory is captured).',
                'icon': 'assets/heroes/abilities/ScavengeTheFallenIcon.png'
            }
        ],
        'description': ['Lord of Noxefort'],
        'icon': 'assets/heroes/brennhen.png'
    },
    'Neil Hévilneu': {
        'cost': 500,
        'letter': 'N',
        'name': 'Neil Hévilneu',
        'training_time': 5,
        'abilities': [
            {
                'name': 'Decisive Strike',
                'type': 'active',
                'cooldown': 6,
                'description': 'Target an enemy territory with at least 2 units. Half of the armies (rounded down) are randomly removed.',
                'icon': 'assets/heroes/abilities/DecisiveStrikeIcon.png'
            },
            {
                'name': 'Valorous Charge',
                'type': 'active',
                'cooldown': 4,
                'description': 'Move up to 15 units from Hévilneu\'s Keep territory to target allied territory (respects 15 unit limit). Units are marked as Moved on arrival.',
                'icon': 'assets/heroes/abilities/ValorousChargeIcon.png'
            },
            {
                'name': 'Vanquish the Enemy',
                'type': 'passive',
                'description': 'All your Swordsmen, Pikemen, Archers, and Cavalry gain +20% strength.',
                'icon': 'assets/heroes/abilities/VanquishTheEnemyIcon.png'
            }
        ],
        'description': ['Supreme Commander of', 'Northern Powers'],
        'icon': 'assets/heroes/hevilneu.png'
    },
    # Serthus Diarcess - Campaign-only hero (not trainable in standard games)
    # Copy of Neil Hévilneu with different icon/name for Campaign Mission 3
    'Serthus Diarcess': {
        'cost': 500,
        'letter': 'Z',  # Z for Zjoals
        'name': 'Serthus Diarcess',
        'training_time': 5,
        'trainable': False,  # Campaign-only hero, not available in training menu
        'abilities': [
            {
                'name': 'Decisive Strike',
                'type': 'active',
                'cooldown': 6,
                'description': 'Target an enemy territory with at least 2 units. Half of the armies (rounded down) are randomly removed.',
                'icon': 'assets/heroes/abilities/DecisiveStrikeIcon.png'
            },
            {
                'name': 'Valorous Charge',
                'type': 'active',
                'cooldown': 4,
                'description': 'Move up to 15 units from Diarcess\'s Keep territory to target allied territory (respects 15 unit limit). Units are marked as Moved on arrival.',
                'icon': 'assets/heroes/abilities/ValorousChargeIcon.png'
            },
            {
                'name': 'Vanquish the Enemy',
                'type': 'passive',
                'description': 'All your Swordsmen, Pikemen, Archers, and Cavalry gain +20% strength.',
                'icon': 'assets/heroes/abilities/VanquishTheEnemyIcon.png'
            }
        ],
        'description': ['The Emperor of Zjoals'],
        'icon': 'assets/heroes/serthus.png'
    },
    'Seledra Rennervail': {
        'cost': 350,
        'letter': 'S',
        'name': 'Seledra Rennervail',
        'training_time': 4,
        'abilities': [
            {
                'name': 'Vow of Silence',
                'type': 'active',
                'cooldown': 5,  # Turns
                'description': 'Prevents all enemy heroes from using active abilities until the end of your next turn.',
                'icon': 'assets/heroes/abilities/VowOfSilenceIcon.png'
            },
            {
                'name': 'Defiance',
                'type': 'passive',
                'description': 'Protects the Keep\'s territory and adjacent friendly territories from enemy hero abilities.',
                'icon': 'assets/heroes/abilities/DefianceIcon.png'
            },
            {
                'name': 'Champion of the People',
                'type': 'passive',
                'description': 'When conquering territories, Farms and Mines are preserved and change ownership instead of being destroyed.',
                'icon': 'assets/heroes/abilities/ChampionOfThePeople.png'
            }
        ],
        'description': ['Princess of Arcburg'],
        'icon': 'assets/heroes/rennervail.png'
    },
    'Evain Nithieln': {
        'cost': 550,
        'letter': 'V',
        'name': 'Evain Nithieln',
        'training_time': 6,
        'abilities': [
            {
                'name': 'Embargo',
                'type': 'active',
                'cooldown': 6,
                'description': 'At the start of your enemies\' next turn, they receive no income from territories, Farms, Mines, or Squares.',
                'icon': 'assets/heroes/abilities/EmbargoIcon.png'
            },
            {
                'name': 'Master Negotiator',
                'type': 'active',
                'cooldown': 5,
                'description': 'For this turn, all Farms, Mines, and Squares cost 75% less gold.',
                'icon': 'assets/heroes/abilities/MasterNegotiatorIcon.png'
            },
            {
                'name': 'Farmer Subsidies',
                'type': 'passive',
                'description': 'All your Farms generate 50% more income.',
                'icon': 'assets/heroes/abilities/FarmerSubsidiesIcon.png'
            }
        ],
        'description': ['High Commander of', 'Affrancian Union'],
        'icon': 'assets/heroes/asten.png'
    },
    'Vearen Asford': {
        'cost': 300,
        'letter': 'F',
        'name': 'Vearen Asford',
        'training_time': 2,
        'abilities': [
            {
                'name': 'Relentless Charge',
                'type': 'active',
                'cooldown': 6,
                'description': 'Summon 4 Cavalry battalions in target friendly territory (must have 11 or fewer units).',
                'icon': 'assets/heroes/abilities/RelentlessChargeIcon.png'
            },
            {
                'name': 'Haste',
                'type': 'passive',
                'description': 'Units trained in territories adjacent to Asford\'s Keep or in the Keep\'s territory are immediately ready to move.',
                'icon': 'assets/heroes/abilities/HasteIcon.png'
            },
            {
                'name': 'Pillage',
                'type': 'passive',
                'description': 'Gain 200 Gold whenever you destroy an enemy Keep.',
                'icon': 'assets/heroes/abilities/PillageIcon.png'
            }
        ],
        'description': ['Grand General of', 'Naragonthid'],
        'icon': 'assets/heroes/asford.png'
    },
    # Regnus Aevencourne - Campaign-only hero (not trainable in standard games)
    # Clone of Darius Brennhen with different icon/name for Campaign Mission 4
    'Regnus Aevencourne': {
        'cost': 150,
        'letter': 'R',
        'name': 'Regnus Aevencourne',
        'training_time': 2,
        'trainable': False,  # Campaign-only hero, not available in training menu
        'abilities': [
            {
                'name': 'Reinforce',
                'type': 'active',
                'cooldown': 4,
                'description': 'Summon 2 Swordsmen battalions in the territory of Aevencourne\'s Keep (must have 13 or fewer units).',
                'icon': 'assets/heroes/abilities/ReinforcementIcon.png'
            },
            {
                'name': 'Safe Haven',
                'type': 'passive',
                'description': 'When losing a battle in a territory adjacent to Aevencourne\'s Keep, one random unit retreats to the Keep\'s territory instead of being destroyed.',
                'icon': 'assets/heroes/abilities/SafeHavenIcon.png'
            },
            {
                'name': 'Scavenge the Fallen',
                'type': 'passive',
                'description': 'Gain 30 Gold whenever you lose a battle (does not trigger when an empty territory is captured).',
                'icon': 'assets/heroes/abilities/ScavengeTheFallenIcon.png'
            }
        ],
        'description': ['The Emperor of Azincourne'],
        'icon': 'assets/heroes/regnus.png'
    }
}

# ============================================================================
# BONUS_TYPES - Territory bonus types and their values
# ============================================================================

# Territory Bonus System - each territory provides global bonuses to its owner
BONUS_TYPES = {
    'income_bonus': {'display': 'Income', 'value': 3, 'format': '+{}%'},
    'tech_cost': {'display': 'Technology Research Cost', 'value': -5, 'format': '{}%'},
    'unit_cost': {'display': 'Unit Training Cost', 'value': -5, 'format': '{}%'},
    'hero_cost': {'display': 'Hero Training Cost', 'value': -3, 'format': '{}%'},
    'pikeman_str': {'display': 'Pikeman Strength', 'value': 10, 'format': '+{}%'},
    'archer_str': {'display': 'Archer Strength', 'value': 10, 'format': '+{}%'},
    'swordsman_str': {'display': 'Swordsman Strength', 'value': 10, 'format': '+{}%'},
    'cavalry_str': {'display': 'Cavalry Strength', 'value': 10, 'format': '+{}%'},
    'building_cost': {'display': 'Building Cost', 'value': -15, 'format': '{}%'}
}


# ============================================================================
# build_technologies() - Technology tree factory function
# ============================================================================

def build_technologies():
    """
    Build and return the technology tree list.

    Creates 21 technologies arranged in a 3-column x 7-row grid.
    Each technology is a dict with id, name, column, row, description,
    cost, turns, icon, effect_type, effect_value, and optionally requires_castle.

    Returns:
        list: List of 21 technology data dicts
    """
    technologies = []
    for col in range(3):
        for row in range(7):
            tech_id = f"tech_{col}_{row}"

            # Define specific technologies
            if col == 0 and row == 0:  # Column 1, Row 1 - Efficient Farming I
                tech_data = {
                    'id': tech_id,
                    'name': 'Efficient Farming I',
                    'column': col,
                    'row': row,
                    'description': 'All your Farms generate 20% more income.',
                    'cost': 100,
                    'turns': 2,
                    'icon': 'assets/upgrades/EfficientFarming1Icon.png',
                    'effect_type': 'farm_income_bonus',
                    'effect_value': 20
                }
            elif col == 0 and row == 1:  # Column 1, Row 2 - Efficient Mining I
                tech_data = {
                    'id': tech_id,
                    'name': 'Efficient Mining I',
                    'column': col,
                    'row': row,
                    'description': 'All your Mines generate 20% more income.',
                    'cost': 150,
                    'turns': 2,
                    'icon': 'assets/upgrades/EfficientMining1Icon.png',
                    'effect_type': 'mine_income_bonus',
                    'effect_value': 20
                }
            elif col == 0 and row == 2:  # Column 1, Row 3 - Leave Nothing Behind
                tech_data = {
                    'id': tech_id,
                    'name': 'Leave Nothing Behind',
                    'column': col,
                    'row': row,
                    'description': 'Recover 50% of the cost when your Farms and Mines are destroyed.',
                    'cost': 150,
                    'turns': 3,
                    'icon': 'assets/upgrades/LeaveNothingBehindIcon.png',
                    'effect_type': 'building_destruction_recovery',
                    'effect_value': 50
                }
            elif col == 0 and row == 3:  # Column 1, Row 4 - Supply and Demand
                tech_data = {
                    'id': tech_id,
                    'name': 'Supply and Demand',
                    'column': col,
                    'row': row,
                    'description': 'Squares multiply territory income by 2.5\u00d7 instead of 1.5\u00d7.',
                    'cost': 250,
                    'turns': 3,
                    'icon': 'assets/upgrades/SupplyAndDemandIcon.png',
                    'effect_type': 'square_multiplier_bonus',
                    'effect_value': 2.5,
                    'requires_castle': True
                }
            elif col == 0 and row == 4:  # Column 1, Row 5 - Efficient Farming II
                tech_data = {
                    'id': tech_id,
                    'name': 'Efficient Farming II',
                    'column': col,
                    'row': row,
                    'description': 'All your Farms generate an additional 20% more income.',
                    'cost': 300,
                    'turns': 2,
                    'icon': 'assets/upgrades/EfficientFarming2Icon.png',
                    'effect_type': 'farm_income_bonus_2',
                    'effect_value': 20,
                    'requires_castle': True
                }
            elif col == 0 and row == 5:  # Column 1, Row 6 - Efficient Mining II
                tech_data = {
                    'id': tech_id,
                    'name': 'Efficient Mining II',
                    'column': col,
                    'row': row,
                    'description': 'All your Mines generate an additional 20% more income.',
                    'cost': 350,
                    'turns': 3,
                    'icon': 'assets/upgrades/EfficientMining2Icon.png',
                    'effect_type': 'mine_income_bonus_2',
                    'effect_value': 20,
                    'requires_castle': True
                }
            elif col == 0 and row == 6:  # Column 1, Row 7 - Laws of Trade
                tech_data = {
                    'id': tech_id,
                    'name': 'Laws of Trade',
                    'column': col,
                    'row': row,
                    'description': 'Farms and Mines generate +15% income if in or adjacent to a territory with a Keep.',
                    'cost': 400,
                    'turns': 3,
                    'icon': 'assets/upgrades/LawsOfTradeIcon.png',
                    'effect_type': 'keep_proximity_bonus',
                    'effect_value': 15,
                    'requires_castle': True
                }
            elif col == 1 and row == 0:  # Column 2, Row 1 - Improved Training
                tech_data = {
                    'id': tech_id,
                    'name': 'Improved Training',
                    'column': col,
                    'row': row,
                    'description': 'Reduces cost of Swordsmen and Pikemen by 20%.',
                    'cost': 100,
                    'turns': 2,
                    'icon': 'assets/upgrades/ImprovedTrainingIcon.png',
                    'effect_type': 'unit_cost_reduction',
                    'effect_value': 20
                }
            elif col == 1 and row == 1:  # Column 2, Row 2 - Makeshift Barracks
                tech_data = {
                    'id': tech_id,
                    'name': 'Makeshift Barracks',
                    'column': col,
                    'row': row,
                    'description': 'Reduces Barracks cost by 25%. \nDemolishing a Barracks now returns 100% of gold spent.',
                    'cost': 200,
                    'turns': 2,
                    'icon': 'assets/upgrades/MakeshiftBarracks.png',
                    'effect_type': 'barracks_upgrade',
                    'effect_value': 25
                }
            elif col == 1 and row == 2:  # Column 2, Row 3 - Animal Handling
                tech_data = {
                    'id': tech_id,
                    'name': 'Animal Handling',
                    'column': col,
                    'row': row,
                    'description': 'Reduces cost of Cavalry by 25%.',
                    'cost': 200,
                    'turns': 3,
                    'icon': 'assets/upgrades/AnimalHandlingIcon.png',
                    'effect_type': 'cavalry_cost_reduction',
                    'effect_value': 25
                }
            elif col == 1 and row == 3:  # Column 2, Row 4 - Battlement Archery
                tech_data = {
                    'id': tech_id,
                    'name': 'Battlement Archery',
                    'column': col,
                    'row': row,
                    'description': 'Archers gain +50% strength in territories \nwith friendly Keep or Castle.',
                    'cost': 250,
                    'turns': 2,
                    'icon': 'assets/upgrades/BattlementArcheryIcon.png',
                    'effect_type': 'archer_keep_strength',
                    'effect_value': 50,
                    'requires_castle': True
                }
            elif col == 1 and row == 4:  # Column 2, Row 5 - Raze the Countryside
                tech_data = {
                    'id': tech_id,
                    'name': 'Raze the Countryside',
                    'column': col,
                    'row': row,
                    'description': 'Gain 30 Gold whenever you destroy an enemy Farm.',
                    'cost': 200,
                    'turns': 3,
                    'icon': 'assets/upgrades/RazeTheCountrysideIcon.png',
                    'effect_type': 'farm_destruction_bonus',
                    'effect_value': 30,
                    'requires_castle': True
                }
            elif col == 1 and row == 5:  # Column 2, Row 6 - Cavalry Tactics
                tech_data = {
                    'id': tech_id,
                    'name': 'Cavalry Tactics',
                    'column': col,
                    'row': row,
                    'description': 'Cavalry units gain +33% strength in battles.',
                    'cost': 250,
                    'turns': 2,
                    'icon': 'assets/upgrades/CavalryTacticsIcon.png',
                    'effect_type': 'cavalry_strength_bonus',
                    'effect_value': 33,
                    'requires_castle': True
                }
            elif col == 1 and row == 6:  # Column 2, Row 7 - Divide and Conquer
                tech_data = {
                    'id': tech_id,
                    'name': 'Divide and Conquer',
                    'column': col,
                    'row': row,
                    'description': 'Pikemen and Swordsmen gain +20% strength in battles. \nArchers gain +50% strength when sieging Keeps.',
                    'cost': 400,
                    'turns': 3,
                    'icon': 'assets/upgrades/DivideAndConquerIcon.png',
                    'effect_type': 'keep_siege_bonus',
                    'effect_value': 1,  # Flag: 1 = enabled
                    'requires_castle': True
                }
            elif col == 2 and row == 0:  # Column 3, Row 1 - Master Planner I
                tech_data = {
                    'id': tech_id,
                    'name': 'Master Planner I',
                    'column': col,
                    'row': row,
                    'description': 'Increases planning time limit by 30 seconds.',
                    'cost': 100,
                    'turns': 2,
                    'icon': 'assets/upgrades/MasterPlanner1Icon.png',
                    'effect_type': 'time_limit',
                    'effect_value': 30
                }
            elif col == 2 and row == 1:  # Column 3, Row 2 - Improved Command I
                tech_data = {
                    'id': tech_id,
                    'name': 'Improved Command I',
                    'column': col,
                    'row': row,
                    'description': 'Increases command limit by 35.',
                    'cost': 150,
                    'turns': 2,
                    'icon': 'assets/upgrades/ImprovedCommand1Icon.png',
                    'effect_type': 'command_limit',
                    'effect_value': 35
                }
            elif col == 2 and row == 2:  # Column 3, Row 3 - Royal Decree
                tech_data = {
                    'id': tech_id,
                    'name': 'Royal Decree',
                    'column': col,
                    'row': row,
                    'description': 'Reduces cost of Heroes and Keeps by 15%.',
                    'cost': 175,
                    'turns': 3,
                    'icon': 'assets/upgrades/RoyalDecreeIcon.png',
                    'effect_type': 'cost_reduction',
                    'effect_value': 15
                }
            elif col == 2 and row == 3:  # Column 3, Row 4 - Master Planner II
                tech_data = {
                    'id': tech_id,
                    'name': 'Master Planner II',
                    'column': col,
                    'row': row,
                    'description': 'Increases planning time limit by 30 seconds.',
                    'cost': 200,
                    'turns': 2,
                    'icon': 'assets/upgrades/MasterPlanner2Icon.png',
                    'effect_type': 'time_limit',
                    'effect_value': 30,
                    'requires_castle': True  # Special requirement
                }
            elif col == 2 and row == 4:  # Column 3, Row 5 - Heroic Fortitude
                tech_data = {
                    'id': tech_id,
                    'name': 'Heroic Fortitude',
                    'column': col,
                    'row': row,
                    'description': 'Increases hero limit to 4.',
                    'cost': 250,
                    'turns': 3,
                    'icon': 'assets/upgrades/HeroicFortitudeIcon.png',
                    'effect_type': 'hero_limit',
                    'effect_value': 4,
                    'requires_castle': True  # Special requirement
                }
            elif col == 2 and row == 5:  # Column 3, Row 6 - Improved Command II
                tech_data = {
                    'id': tech_id,
                    'name': 'Improved Command II',
                    'column': col,
                    'row': row,
                    'description': 'Increases command limit by 35.',
                    'cost': 300,
                    'turns': 2,
                    'icon': 'assets/upgrades/ImprovedCommand2Icon.png',
                    'effect_type': 'command_limit',
                    'effect_value': 35,
                    'requires_castle': True  # Special requirement
                }
            elif col == 2 and row == 6:  # Column 3, Row 7 - Last Resort
                tech_data = {
                    'id': tech_id,
                    'name': 'Last Resort',
                    'column': col,
                    'row': row,
                    'description': 'Keeps and Castles with Heroes gain +100% defense bonus.',
                    'cost': 350,
                    'turns': 3,
                    'icon': 'assets/upgrades/LastResortIcon.png',
                    'effect_type': 'hero_keep_defense',
                    'effect_value': 2,
                    'requires_castle': True  # Special requirement
                }
            else:
                # Placeholder for other technologies
                tech_data = {
                    'id': tech_id,
                    'name': f"Tech {col+1}-{row+1}",
                    'column': col,
                    'row': row,
                    'description': f"Placeholder technology in column {col+1}, row {row+1}",
                    'cost': 0,
                    'turns': 0,
                    'icon': None,
                    'effect_type': None,
                    'effect_value': None
                }

            technologies.append(tech_data)

    return technologies
