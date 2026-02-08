import traceback
import sys
sys.stderr = sys.stdout  

try:
    print("Step 1: Starting import...")
    from api.routes import router
    print('Import OK')
except Exception as e:
    print(f"Error: {e}")
    traceback.print_exc()
