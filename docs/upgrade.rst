Updating from PyEPICS
=====================

pvua has been designed to be a (mostly) drop-in replacement for PyEPICS, so the update process should be (mostly) straightforward.

- Equivalents of free-standing functions in the ``epics`` module are now methods of the ``Context`` class, e.g. ``epics.caget`` translates to ``Context.get``.
- Additionally, since pvua is protocol-agnostic, most methods will not have a ca/pva prefix or suffix.
  Methods that do will only work if the PV is using that protocol, e.g. ``Context.rpc_pva`` will only perform a pvAccess RPC call for a PV served through pvAccess.
- Instantiating PV objects now requires passing a ``Context`` object as the first parameter.
- Some parameters of functions in PyEPICS are not currently implemented. See the class documentation for details.
  If your code relies on any of these parameters, please open an issue to request that they be implemented.

The reliance on a ``Context`` object is a necessary change to support pvAccess, however besides managing the context object there should be minimal to no other necessary changes.
