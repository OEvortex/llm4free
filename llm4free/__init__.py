from llm4free.litagent import LitAgent

from .AISEARCH import *
from .AIutel import *  # noqa: F403
from .client import Client
from .Extra import *  # noqa: F403
from .llm import *
from .models import model
from .scout import *
from .search import *
from .STT import *  # noqa: F403
from .TTI import *
from .TTS import *
from .update_checker import check_for_updates
from .version import __version__
useragent = LitAgent()


# Check for updates on import to notify users of new versions
try:
    update_message = check_for_updates(force=True)
    if update_message:
        print(update_message)
except Exception:
    pass
