import epics

from .context import Provider, Context


class PV:
    """
    Intended to be a (mostly) drop-in replacement for PV objects from PyEPICS.
    """

    def __init__(self, context: Context, pv_name: str, provider_get_override: Provider = Provider.INHERIT, provider_put_override: Provider = Provider.INHERIT, provider_mon_override: Provider = Provider.INHERIT):
        self.context = context
        self.pvname = pv_name
        self.provider_get_override = provider_get_override
        self.provider_put_override = provider_put_override
        self.provider_mon_override = provider_mon_override

        if (
            (context.provider_get != Provider.PVA if provider_get_override == Provider.INHERIT else provider_get_override != Provider.PVA) or
            (context.provider_put != Provider.PVA if provider_put_override == Provider.INHERIT else provider_put_override != Provider.PVA) or
            (context.provider_mon != Provider.PVA if provider_mon_override == Provider.INHERIT else provider_mon_override != Provider.PVA)
        ):
            self.ca_obj = epics.PV(self.pvname)
        else:
            self.ca_obj = None

    def connect(self, timeout: int | float | None = None) -> bool:
        if self.ca_obj is not None:
            return self.ca_obj.connect(timeout=timeout)
        return True

    def wait_for_connection(self, timeout: int | float | None = None) -> bool:
        if self.ca_obj is not None:
            self.ca_obj.wait_for_connection(timeout=timeout)
        return True

    def get(self, as_string: bool = False):
        return self.context.get(self.pvname, as_string, self.provider_get_override)

    def get_timevars(self):
        return self.context.get_timevars(self.pvname, self.provider_get_override)

    def put(self, value):
        return self.context.put(self.pvname, value, self.provider_put_override)

    def info(self):
        # Only supported for CA
        return self.context.info_ca(self.pvname)

    def __str__(self):
        return self.pvname + ': ' + info if (info := self.info()) is not None else "Failed to load information."

    def monitor(self, callback):
        return self.context.monitor(self.pvname, callback, self.provider_mon_override)
