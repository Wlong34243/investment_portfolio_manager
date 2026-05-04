import os

def run_audit():
    suspect_files = [
        "tasks/build_holdings_current.py",
        "tasks/build_daily_snapshots.py",
        "scripts/live_update.py"
    ]
    
    # We write directly to the file using utf-8 to bypass Windows console errors
    with open("audit_results.txt", "w", encoding="utf-8") as out:
        out.write("==================================================\n")
        out.write("              START OF AUDIT DUMP                 \n")
        out.write("==================================================\n\n")

        for file_path in suspect_files:
            if os.path.exists(file_path):
                out.write(f"\n\n{'='*60}\nFILE: {file_path}\n{'='*60}\n")
                with open(file_path, 'r', encoding='utf-8') as f:
                    out.write(f.read())
            else:
                out.write(f"\n\n[NOT FOUND] {file_path}\n")

        # Dynamically hunt for the Schwab transaction parser
        out.write(f"\n\n{'='*60}\nSEARCHING FOR TRANSACTION PARSER\n{'='*60}\n")
        for root, dirs, files in os.walk("."):
            # Skip hidden folders and virtual environments
            dirs[:] = [d for d in dirs if not d.startswith('.') and 'venv' not in d and '__pycache__' not in d]
            
            for file in files:
                if file.endswith(".py"):
                    path = os.path.join(root, file)
                    # Skip files we already printed
                    if any(path.endswith(s) for s in suspect_files):
                        continue
                    
                    try:
                        with open(path, 'r', encoding='utf-8') as f:
                            content = f.read()
                            # Keywords related to Schwab transaction JSON parsing
                            if "transactionItem" in content or "CURRENCY_USD" in content or "get_transactions" in content:
                                out.write(f"\n\n--- TRANSACTION LOGIC FOUND IN: {path} ---\n")
                                out.write(content)
                    except Exception:
                        pass

        out.write("\n==================================================\n")
        out.write("               END OF AUDIT DUMP                  \n")
        out.write("==================================================\n")
        
    print("Audit complete! Results safely written to audit_results.txt")

if __name__ == "__main__":
    run_audit()