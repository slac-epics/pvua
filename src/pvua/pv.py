from .context import Provider, Context


class PV:
    """
    Intended to be a (mostly) drop-in replacement for PV objects from PyEPICS.
    """

    def __init__(self, context: Context, pv_name: str, provider_get_override: Provider = Provider.INHERIT, provider_put_override: Provider = Provider.INHERIT, provider_monitor_override: Provider = Provider.INHERIT):
        self.context = context
        self.pv_name = pv_name
        self.provider_get_override = provider_get_override
        self.provider_put_override = provider_put_override
        self.provider_monitor_override = provider_monitor_override

    def get(self, as_string: bool = False):
        return self.context.get(self.pv_name, as_string, self.provider_get_override)

    def put(self, value):
        return self.context.put(self.pv_name, value, self.provider_put_override)

    def info(self):
        # Only supported for CA
        return self.context.info_ca(self.pv_name)

    def __str__(self):
        return f"{self.pv_name}: {info if (info := self.info()) is not None else "Failed to load information."}"

    def monitor(self, callback):
        return self.context.monitor(self.pv_name, callback, self.provider_monitor_override)
