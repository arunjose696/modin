# script.py
import os 
  
  
# Get the number of CPUs 
# in the system using 
# os.cpu_count() method 
cpuCount = os.cpu_count() 
print(cpuCount)
if True:
    import unidist

    # Initialize unidist's backend. The MPI backend is used by default.
    unidist.init()

    # # Apply decorator to make `square` a remote function.
    # @unidist.remote
    # def square(x):
    #     return x * x

    # # Asynchronously execute remote function.
    # square_refs = [square.remote(i) for i in range(4)]
