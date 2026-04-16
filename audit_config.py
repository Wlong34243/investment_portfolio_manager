import os
import re

def find_missing_config_vars(root_dir="."):
    print("🔍 Scanning codebase for 'config.*' usages...")
    
    # Regex to find exactly 'config.UPPERCASE_VAR_NAME'
    pattern = re.compile(r'\bconfig\.([A-Z0-9_]+)\b')
    used_vars = set()
    
    # Walk through all python files
    for dirpath, _, filenames in os.walk(root_dir):
        # Skip hidden directories like .git or virtual environments
        if any(part.startswith('.') or part in ('venv', 'env', '__pycache__') for part in dirpath.split(os.sep)):
            continue
            
        for file in filenames:
            if file.endswith(".py") and file != "config.py" and file != "audit_config.py":
                filepath = os.path.join(dirpath, file)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                        matches = pattern.findall(content)
                        for match in matches:
                            used_vars.add(match)
                except Exception as e:
                    pass

    # Try to load the current config.py to see what is actually defined
    try:
        import config
        defined_vars = set(dir(config))
    except ImportError as e:
        print(f"❌ Error importing config.py: {e}")
        return

    # Find the difference
    missing_vars = used_vars - defined_vars

    if missing_vars:
        print("\n🚨 MISSING CONFIG VARIABLES DETECTED 🚨")
        print("The following variables are used in your code but are completely missing from config.py:\n")
        for var in sorted(missing_vars):
            print(f" - {var}")
        print("\n👉 Action: Add these to config.py with their proper values/lists.")
    else:
        print("\n✅ Audit complete: No missing config variables found!")

if __name__ == "__main__":
    find_missing_config_vars()