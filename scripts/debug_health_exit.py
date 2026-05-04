from tasks.health import run_all_checks, CRITICAL, FAIL, WARN, PASS

results = run_all_checks()
for r in results:
    print(f"{r.name}: level={r.level}, status={r.status}")

has_critical_fail = any(
    r.level == CRITICAL and r.status == FAIL for r in results
)
print(f"has_critical_fail: {has_critical_fail}")
