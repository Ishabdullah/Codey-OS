exec(open(__import__("os").path.join(__import__("os").path.dirname(__import__("os").path.realpath(__file__)),"h.py")).read())
install_fakes()
os.chdir(B+"/work")
import types
try:
    import main as M
    print("main imported", M.__file__)
except Exception as e:
    print("main import failed", repr(e))
