import traceback
try:
    import sys
    import os
    sys.path.append(os.path.abspath(
        os.path.join(os.path.dirname(__file__), '..')))
    import rpa_playwright
    print('import ok')
except Exception as e:
    traceback.print_exc()
