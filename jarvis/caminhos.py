import os
import sys

FROZEN = getattr(sys, "frozen", False)

PASTA_RECURSOS = getattr(
    sys, "_MEIPASS",
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)


PASTA_APP = os.path.dirname(sys.executable) if FROZEN else PASTA_RECURSOS
