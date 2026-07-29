# AUTO-IMPROVED by CCOS Capability Optimizer
# Original issues: Increase timeout or optimize slow code paths
# Improvement timestamp: 2026-07-29 00:29:20

def _with_timeout(func, seconds=30):
    """Run function with timeout in thread."""
    import threading
    result = [None]
    error = [None]
    def target():
        try:
            result[0] = func()
        except Exception as e:
            error[0] = e
    t = threading.Thread(target=target)
    t.daemon = True
    t.start()
    t.join(seconds)
    if t.is_alive():
        return {"success": False, "error": "timeout"}
    if error[0]:
        return {"success": False, "error": str(error[0])}
    return result[0]

def get_system_info():
    """Get system info."""
    import platform
    return {"os": platform.system(), "arch": platform.machine()}
