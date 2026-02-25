import os
os.chdir(r'c:\Users\jstol\eclipse-workspace\AvareonWar')

def fix(path, pairs):
    with open(path, 'r', encoding='utf-8') as f:
        c = f.read()
    for old, new in pairs:
        if old in c:
            c = c.replace(old, new, 1)
            print(f'  OK: {old[:50]}')
        else:
            print(f'  MISS: {old[:50]}')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(c)

print('=== ai_player.py ===')
fix('ai_player.py', [
    ('print(f"[AI] Resolving battle in {territory_name} (Players: {[p+1 for p in players_involved]})")', 'logger.info(f"Resolving battle in {territory_name} (Players: {[p+1 for p in players_involved]})")'),
    ('print(f"[AI] Resolved battle in {territory_name}")', 'logger.info(f"Resolved battle in {territory_name}")'),
    ('print(f"[AI ERROR] Failed to resolve battle in {territory_name}")', 'logger.error(f"Failed to resolve battle in {territory_name}")'),
    ('print(f"[AI] All battles resolved, advancing to next player")', 'logger.info("All battles resolved, advancing to next player")'),
    ('print(f"[AI ERROR] Failed to auto-resolve battles: {e}")\n            import traceback\n            traceback.print_exc()', 'logger.error(f"Failed to auto-resolve battles: {e}", exc_info=True)'),
])
print('Done')
