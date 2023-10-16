# script.py
try:
    import mpi4py
except ImportError:
    raise ImportError(
        "Missing dependency 'mpi4py'. Use pip or conda to install it."
    ) from None 
# TODO: Find a way to move this after all imports
mpi4py.rc(recv_mprobe=False, initialize=False)
from mpi4py import MPI  # noqa: E402
import sys
thread_level = MPI.Init_thread()
args =['-R', '-c', "import unidist; import unidist.config as cfg; cfg.Backend.put('mpi'); cfg.MpiSharedObjectStore.put(False); unidist.init()"]
intercomm = MPI.COMM_SELF.Spawn(
            sys.executable,
            args,
            maxprocs=4,
            root=0,
        )
comm = intercomm.Merge(high=False)
MPI.Finalize()
    # # Apply decorator to make `square` a remote function.
    # @unidist.remote
    # def square(x):
    #     return x * x

    # # Asynchronously execute remote function.
    # square_refs = [square.remote(i) for i in range(4)]
