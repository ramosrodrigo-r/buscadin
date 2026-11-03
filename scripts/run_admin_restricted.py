"""Linux admin launcher: refuse root and prevent privilege gains before exec."""
import ctypes
import os

if os.geteuid() == 0:
    raise SystemExit('Admin must run as a non-root user')
libc = ctypes.CDLL(None, use_errno=True)
libc.prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong]
if libc.prctl(38, 1, 0, 0, 0) != 0:  # PR_SET_NO_NEW_PRIVS
    raise SystemExit('Unable to restrict admin privileges')
os.execvp('buscadin-admin', ['buscadin-admin'])
