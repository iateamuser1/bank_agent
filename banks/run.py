"""Launch all 20 mock bank portals (one server, all banks under /bank/<id>/).

    python -m bank_agent.banks.run
"""

import uvicorn
import yaml
from pathlib import Path

if __name__ == "__main__":
    cfg = yaml.safe_load((Path(__file__).resolve().parents[1] / "config.yaml").read_text())
    uvicorn.run("bank_agent.banks.app:app", host=cfg["banks"]["host"], port=cfg["banks"]["port"], reload=False)
