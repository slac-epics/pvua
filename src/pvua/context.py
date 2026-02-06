from enum import Enum

import epics
from p4p.client.thread import Context as PVAContext


class Preference(Enum):
    UNKNOWN = 0  # Will use both PVA and CA until one works
    CA = 1
    PVA = 2


# todo: monitor wrapper
class Monitor:
    pass


class Context:
    def __init__(self, pva_ctxt=None):
        if pva_ctxt is None:
            self.pva_ctxt = PVAContext('pva')
        else:
            self.pva_ctxt = pva_ctxt

        self.pv_preference_cache: dict[str, Preference] = {}

    def get(self, pv_name: str, as_string: bool = False, preference: Preference = Preference.UNKNOWN):
        match preference:
            case Preference.PVA:
                self.pv_preference_cache[pv_name] = preference
                return self.pva_ctxt.get(pv_name)
            case Preference.CA:
                self.pv_preference_cache[pv_name] = preference
                return epics.caget(pv_name, as_string=as_string)
            case _:
                if pv_name not in self.pv_preference_cache:
                    # todo: improve selection logic, multithread
                    if (value := self.get(pv_name, as_string, Preference.PVA)) is not None and not isinstance(value, TimeoutError):
                        return str(value) if as_string else value
                    elif (value := self.get(pv_name, as_string, Preference.CA)) is not None:
                        return value
                    else:
                        del self.pv_preference_cache[pv_name]
                        return None
                elif self.pv_preference_cache[pv_name] == Preference.UNKNOWN:
                    del self.pv_preference_cache[pv_name]
                    return self.get(pv_name, as_string, Preference.UNKNOWN)
                else:
                    return self.get(pv_name, as_string, self.pv_preference_cache[pv_name])

    def __getitem__(self, pv_name: str):
        return self.get(pv_name)

    def put(self, pv_name: str, value, preference: Preference = Preference.UNKNOWN):
        match preference:
            case Preference.PVA:
                self.pv_preference_cache[pv_name] = preference
                return self.pva_ctxt.put(pv_name, value)
            case Preference.CA:
                self.pv_preference_cache[pv_name] = preference
                return epics.caput(pv_name, value)
            case Preference.UNKNOWN:
                if pv_name not in self.pv_preference_cache:
                    # todo: determine correct preference based on timeouts
                    self.put(pv_name, value, Preference.PVA)
                    self.put(pv_name, value, Preference.CA)
                    del self.pv_preference_cache[pv_name]
                elif self.pv_preference_cache[pv_name] == Preference.UNKNOWN:
                    del self.pv_preference_cache[pv_name]
                    self.put(pv_name, value, Preference.UNKNOWN)
                else:
                    self.put(pv_name, value, self.pv_preference_cache[pv_name])

    def __setitem__(self, pv_name: str, value):
        return self.put(pv_name, value)

    def info_ca(self, pv_name: str):
        # Only supported by PyEPICS
        return epics.cainfo(pv_name)

    def monitor(self, pv_name: str, callback, preference: Preference = Preference.UNKNOWN):
        return Monitor()  # todo: monitor wrapper
        #ca.camonitor(pv_name, callback) # pv_name, writer, callback, timeout, monitor_delta
        #self.pva_ctxt.monitor(pv_name, callback) # pv_name, callback, request, notify_disconnect

    def rpc_pva(self, pv_name: str, value, **kwargs):
        # Only supported by PVA
        return self.pva_ctxt.rpc(pv_name, value, **kwargs)

    def reset_preferences(self):
        self.pv_preference_cache.clear()
