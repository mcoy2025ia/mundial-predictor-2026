import json, pathlib, sys
sys.stdout.reconfigure(encoding="utf-8")

gm = json.loads(pathlib.Path("frontend/public/data/group_matches.json").read_text(encoding="utf-8"))

# Ver estructura de un partido
first_group = list(gm.keys())[0]
first_match = gm[first_group][0]
print("=== Estructura de un partido ===")
print(json.dumps(first_match, indent=2, ensure_ascii=False))

print("\n=== Campos round/matchday por grupo ===")
for grp, matches in gm.items():
    rounds_in_group = [m.get("round", m.get("matchday", "?")) for m in matches]
    print(grp + ": " + str(rounds_in_group))
