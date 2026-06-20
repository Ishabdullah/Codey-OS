import sys
sys.path.insert(0, "..")
from test_module import get_system_info
result = get_system_info()
assert isinstance(result, dict)
assert "os" in result
print("PASS")
