import sys
from pathlib import Path

# корень проекта - чтобы pytest находил пакеты sla, kit и t05_orders_sla
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
