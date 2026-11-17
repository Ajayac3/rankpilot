"""
RankPilot — Central logging setup.
All modules import get_logger(__name__) instead of using print().
Logs go to: console (INFO+) and rankpilot/data/logs/rankpilot.log (DEBUG+).
"""
import logging, os
from logging.handlers import RotatingFileHandler

_LOG_DIR  = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         'data', 'logs')
_LOG_FILE = os.path.join(_LOG_DIR, 'rankpilot.log')

_configured = False

def _setup():
    global _configured
    if _configured:
        return
    os.makedirs(_LOG_DIR, exist_ok=True)

    root = logging.getLogger('rankpilot')
    root.setLevel(logging.DEBUG)

    fmt = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s',
                            datefmt='%Y-%m-%d %H:%M:%S')

    # Console — INFO and above
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)

    # File — DEBUG and above, 5MB × 3 rotations
    fh = RotatingFileHandler(_LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3,
                             encoding='utf-8')
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)

    root.addHandler(ch)
    root.addHandler(fh)
    root.propagate = False
    _configured = True


def get_logger(name: str) -> logging.Logger:
    _setup()
    # Strip leading package paths so names stay short
    short = name.replace('rankpilot.', '').replace('collectors.', '').replace('analysis.', '')
    return logging.getLogger(f'rankpilot.{short}')
