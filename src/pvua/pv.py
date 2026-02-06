from .context import Preference, Context


class PV:
    """
    Intended to be a (mostly) drop-in replacement for PV objects from PyEPICS.
    """

    def __init__(self, context: Context, pv_name: str, preference: Preference = Preference.UNKNOWN):
        self.context = context
        self.pv_name = pv_name
        self.preference = preference

    def get(self, as_string: bool = False):
        return self.context.get(self.pv_name, as_string, self.preference)

    def put(self, value):
        return self.context.put(self.pv_name, value, self.preference)

    def info(self):
        # Only supported for CA
        match self.preference:
            case Preference.UNKNOWN | Preference.CA:
                return self.context.info_ca(self.pv_name)
            case _:
                return None

    def __str__(self):
        return f"{self.pv_name}: {info if (info := self.info()) is not None else "Failed to load information."}"

    def monitor(self, callback):
        return self.context.monitor(self.pv_name, callback)
