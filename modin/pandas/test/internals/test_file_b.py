import os
import sys

sys.path.append(os.getcwd())  # noqa: E402
from unidist.config import IsMpiSpawnWorkers  # noqa: E402

import modin.pandas as pd  # noqa: E402

IsMpiSpawnWorkers.put(False)  # noqa: E402
os.environ["UNIDIST_CPUS"] = "2"  # noqa: E402
os.environ["MODIN_CPUS"] = "2"  # noqa: E402
df = pd.DataFrame([0])  # noqa: E402
# from modin.config import Engine  # noqa: E402

# engine = Engine.get()  # a


df.dropna()
