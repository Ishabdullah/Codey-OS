def get_system_info():
    """Get system info."""
    import platform
    return {"os": platform.system(), "arch": platform.machine()}
