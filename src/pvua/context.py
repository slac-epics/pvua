from enum import Enum

import epics
from p4p.client.thread import Context as PVAContext


class Provider(Enum):
    INHERIT = 0  # Inherit provider from context default
    UNKNOWN = 1  # Will use PVA then CA until one works
    CA = 2
    PVA = 3


# todo: monitor wrapper
class Monitor:
    pass


class Context:
    def __init__(self, pva_ctxt=None, provider_get=Provider.UNKNOWN, provider_put=Provider.UNKNOWN, provider_monitor=Provider.UNKNOWN):
        if pva_ctxt is None:
            self.pva_ctxt = PVAContext('pva')
        else:
            self.pva_ctxt = pva_ctxt

        self.provider_get     = provider_get     if provider_get     != Provider.INHERIT else Provider.UNKNOWN
        self.provider_put     = provider_put     if provider_put     != Provider.INHERIT else Provider.UNKNOWN
        self.provider_monitor = provider_monitor if provider_monitor != Provider.INHERIT else Provider.UNKNOWN

        self.pv_provider_cache_get:     dict[str, Provider] = {}
        self.pv_provider_cache_put:     dict[str, Provider] = {}
        self.pv_provider_cache_monitor: dict[str, Provider] = {}

    def get(self, pv_name: str, as_string: bool = False, provider_override: Provider = Provider.INHERIT):
        provider = self.provider_get if provider_override == Provider.INHERIT else provider_override
        match provider:
            case Provider.PVA:
                return self.pva_ctxt.get(pv_name)
            case Provider.CA:
                return epics.caget(pv_name, as_string=as_string)
            case _:
                if pv_name not in self.pv_provider_cache_get:
                    try:
                        if (value := self.get(pv_name, as_string, Provider.PVA)) is not None:
                            self.pv_provider_cache_get[pv_name] = Provider.PVA
                            return str(value) if as_string else value
                    except TimeoutError:
                        pass
                    if (value := self.get(pv_name, as_string, Provider.CA)) is not None:
                        self.pv_provider_cache_put[pv_name] = Provider.CA
                        return value
                    else:
                        return None
                else:
                    return self.get(pv_name, as_string, self.pv_provider_cache_get[pv_name])

    def __getitem__(self, pv_name: str):
        return self.get(pv_name)

    def put(self, pv_name: str, value, provider_override: Provider = Provider.INHERIT):
        provider = self.provider_put if provider_override == Provider.INHERIT else provider_override
        match provider:
            case Provider.PVA:
                return self.pva_ctxt.put(pv_name, value)
            case Provider.CA:
                return epics.caput(pv_name, value)
            case _:
                if pv_name not in self.pv_provider_cache_put:
                    try:
                        value = self.put(pv_name, value, Provider.PVA)
                        self.pv_provider_cache_put[pv_name] = Provider.PVA
                        return value
                    except TimeoutError:
                        pass
                    if (value := self.put(pv_name, value, Provider.CA)) is None or value < 0:
                        return None
                    self.pv_provider_cache_put[pv_name] = Provider.CA
                    return value
                else:
                    return self.put(pv_name, value, self.pv_provider_cache_put[pv_name])

    def __setitem__(self, pv_name: str, value):
        return self.put(pv_name, value)

    def info_ca(self, pv_name: str):
        # Only supported by PyEPICS
        return epics.cainfo(pv_name)

    def monitor(self, pv_name: str, callback, provider_override: Provider = Provider.UNKNOWN):
        #provider = self.provider_monitor if provider_override == Provider.INHERIT else provider_override
        return Monitor()  # todo: monitor wrapper
        #ca.camonitor(pv_name, callback) # pv_name, writer, callback, timeout, monitor_delta
        #self.pva_ctxt.monitor(pv_name, callback) # pv_name, callback, request, notify_disconnect

    def rpc_pva(self, pv_name: str, value, **kwargs):
        # Only supported by PVA
        return self.pva_ctxt.rpc(pv_name, value, **kwargs)

    def reset_provider_cache_get(self):
        self.pv_provider_cache_get.clear()

    def reset_provider_cache_put(self):
        self.pv_provider_cache_put.clear()

    def reset_provider_caches(self):
        self.reset_provider_cache_get()
        self.reset_provider_cache_put()
