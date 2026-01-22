from fastapi import FastAPI
import uvicorn
import os

try:
    from zoi_complete_system import app
except ImportError:
  
    from zoi_complete_system import app

if __name__ == "__main__":
   
    port = int(os.environ.get("PORT", 8000))
    
    uvicorn.run(app, host="0.0.0.0", port=port)
