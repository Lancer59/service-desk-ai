"""Quick smoke test — run with: python _smoke_test.py"""
import sys
sys.path.insert(0, ".")

errors = []

# 1. Registry
print("=== Registry ===")
try:
    from tools.registry import ALL_TOOLS, get_tools
    print(f"OK  tools registered: {len(ALL_TOOLS)}")
    for name in sorted(ALL_TOOLS):
        print(f"    {name}")
except Exception as e:
    errors.append(f"registry: {e}")
    print(f"FAIL  {e}")

# 2. Skill loader
print("\n=== Skills ===")
try:
    from skills.loader import list_all_skills, _load_registry
    _load_registry()
    skills = list_all_skills()
    print(f"OK  skills loaded: {len(skills)}")
    for s in skills:
        tool_count = len(s["tools"])
        print(f"    {s['name']} ({s['domain']}) — {tool_count} tools: {s['tools']}")
except Exception as e:
    errors.append(f"skills: {e}")
    print(f"FAIL  {e}")

# 3. Config
print("\n=== Config ===")
try:
    from config import settings, get_models
    models = get_models()
    print(f"OK  models configured: {len(models)}")
    for m in models:
        print(f"    {m['id']} ({m['deployment']}) temp={m.get('supports_temperature', True)}")
    nx = settings.get("nexthink", {})
    print(f"OK  nexthink scripts: {len(nx.get('script_map', {}))}")
except Exception as e:
    errors.append(f"config: {e}")
    print(f"FAIL  {e}")

# 4. Clients importable (no credentials needed for import)
print("\n=== Clients (import only) ===")
client_modules = [
    "clients.servicenow",
    "clients.graph",
    "clients.nexthink",
    "clients.vm_api",
    "clients.notification",
    "clients.zoom",
    "clients.smtp",
    "clients.mongodb",
    "clients.google_cal",
]
for mod in client_modules:
    try:
        __import__(mod)
        print(f"OK  {mod}")
    except Exception as e:
        errors.append(f"{mod}: {e}")
        print(f"FAIL  {mod}: {e}")

# 5. FastAPI app imports
print("\n=== App ===")
try:
    import main
    print("OK  main.py imports clean")
except Exception as e:
    errors.append(f"main: {e}")
    print(f"FAIL  main: {e}")

# 6. Skill→tool cross-check
print("\n=== Skill↔Tool cross-check ===")
try:
    from skills.loader import list_all_skills
    from tools.registry import ALL_TOOLS
    all_skills = list_all_skills()
    missing = []
    for skill in all_skills:
        for tool_name in skill["tools"]:
            if tool_name not in ALL_TOOLS:
                missing.append(f"{skill['name']} references unknown tool: {tool_name}")
    if missing:
        for m in missing:
            print(f"WARN  {m}")
    else:
        print("OK  all skill tool references resolve in registry")
except Exception as e:
    errors.append(f"cross-check: {e}")
    print(f"FAIL  {e}")

# Summary
print("\n" + "="*40)
if errors:
    print(f"FAILED — {len(errors)} error(s):")
    for e in errors:
        print(f"  {e}")
    sys.exit(1)
else:
    print("ALL CHECKS PASSED")
