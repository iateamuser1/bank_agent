"""Launch the UI.

    python -m bank_agent.ui.run       # then open http://127.0.0.1:8500/
"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run("bank_agent.ui.app:app", host="127.0.0.1", port=8500, reload=False)
