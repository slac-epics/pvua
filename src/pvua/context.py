import epics
import math
from p4p.client.thread import Context as PVAContext
from p4p.client.thread import Subscription
from p4p import Value
from enum import IntEnum
from typing import Callable


class Provider(IntEnum):
    INHERIT = 0  # Inherit provider from context default
    UNKNOWN = 1  # Will use PVA then CA until one works
    CA = 2
    PVA = 3


# todo: monitor wrapper
class Monitor:
    def __init__(self, pv: str, cb: Callable, context, pva_sub: Subscription | None):
        self.sub = pva_sub
        self.context = context
        self.pv = pv
        self.cb = cb

    def close(self):
        """Close the subscription"""
        if self.sub is not None:
            self.sub.close()
        self.context.close_monitor(self, self.pv)

    def protocol(self) -> Provider:
        """Returns the protocol used for this PV"""
        return Provider.PVA if self.sub is not None else Provider.CA

class Context:
    def __init__(self, pva_ctxt=None, provider_get=Provider.UNKNOWN, provider_put=Provider.UNKNOWN, provider_monitor=Provider.UNKNOWN):
        """
        Parameters
        ----------
        pva_ctxt : Context | None
            p4p context to use, or None to create a new one.
            NOTE: In order for this to work correctly, the PVA context must be created with nt=False.
        provider_get : Provider
            Provider override for gets
        provider_put : Provider
            Provider override for puts
        provider_monitor : Provider
            Provider override for monitors
        """
        if pva_ctxt is None:
            # noinspection PyTypeChecker
            self.pva_ctxt = PVAContext('pva', nt=False)
        else:
            self.pva_ctxt = pva_ctxt

        self.provider_get = provider_get     if provider_get     != Provider.INHERIT else Provider.UNKNOWN
        self.provider_put = provider_put     if provider_put     != Provider.INHERIT else Provider.UNKNOWN
        self.provider_mon = provider_monitor if provider_monitor != Provider.INHERIT else Provider.UNKNOWN

        self.pv_provider_cache: dict[str, Provider] = {}
        self.monitors: dict[str, list[Monitor]] = {}

    def determine_providers(self, pvs: list[str]):
        """
        Given a list of PVs, issue a GET per PV to cache the available provider.
        
        Parameters
        ----------
        pvs : list[str]
            List of PVs to cache. If they're already cached, they will be skipped.
        """
        for k in pvs:
            if k not in self.pv_provider_cache:
                # Just issue a GET and discard the result
                self.get(pv_name=k, provider_override=Provider.UNKNOWN)

    def get_provider(self, pv_name: str) -> Provider:
        """Returns the provider for a specific PV, or Provider.UNKNOWN if no known provider"""
        if pv_name in self.pv_provider_cache:
            return self.pv_provider_cache[pv_name]
        return Provider.UNKNOWN

    def get(self, pv_name: str, as_string: bool = False, provider_override: Provider = Provider.INHERIT):
        """
        Issue a GET request to a PV
        
        Parameters
        ----------
        pv_name : str
            Name of the PV to GET
        as_string : bool
            If true, convert the value to string before returning
        provider_override : Provider
        """
        provider = self.provider_get if provider_override == Provider.INHERIT else provider_override
        match provider:
            case Provider.PVA:
                return self.pva_ctxt.get(pv_name)["value"]
            case Provider.CA:
                return epics.caget(pv_name, as_string=as_string)
            case _:
                if pv_name not in self.pv_provider_cache:
                    try:
                        if (value := self.get(pv_name, as_string, Provider.PVA)) is not None:
                            self.pv_provider_cache[pv_name] = Provider.PVA
                            return str(value) if as_string else value
                    except TimeoutError:
                        pass
                    if (value := self.get(pv_name, as_string, Provider.CA)) is not None:
                        self.pv_provider_cache[pv_name] = Provider.CA
                        return value
                    else:
                        return None
                else:
                    return self.get(pv_name, as_string, self.pv_provider_cache[pv_name])

    def __getitem__(self, pv_name: str):
        return self.get(pv_name)

    def get_timevars(self, pv_name: str, provider_override: Provider = Provider.INHERIT):
        """
        Issue a GET request, returning timestamp

        Parameters
        ----------
        pv_name : str
            Name of the PV
        provider_override : Provider
        
        Returns
        -------
        dict :
            Dictionary containing timestamp
        """
        provider = self.provider_get if provider_override == Provider.INHERIT else provider_override
        match provider:
            case Provider.PVA:
                time_data = self.pva_ctxt.get(pv_name)
                if time_data is not None and 'timeStamp' in time_data:
                    time_data = time_data['timeStamp']
                    return {
                        'timestamp': self._posix2epics_ts(time_data['secondsPastEpoch']),
                        'posixseconds': time_data['secondsPastEpoch'],
                        'nanoseconds': time_data['nanoseconds']
                    }
                return None
            case Provider.CA:
                time_data = epics.PV(pv_name).get_timevars()
                return {
                    'timestamp': time_data['timestamp'],
                    'posixseconds': time_data['posixseconds'],
                    'nanoseconds': time_data['nanoseconds']
                }
            case _:
                if pv_name not in self.pv_provider_cache:
                    try:
                        if (value := self.get_timevars(pv_name, Provider.PVA)) is not None:
                            self.pv_provider_cache[pv_name] = Provider.PVA
                            return value
                    except TimeoutError:
                        pass
                    if (value := self.get_timevars(pv_name, Provider.CA)) is not None:
                        self.pv_provider_cache[pv_name] = Provider.CA
                        return value
                    else:
                        return None
                else:
                    return self.get_timevars(pv_name, self.pv_provider_cache[pv_name])

    def put(self, pv_name: str, value, provider_override: Provider = Provider.INHERIT):
        """
        Issue a PUT request to a specific PV
        
        Parameters
        ----------
        pv_name : str
            Name of the PV to PUT
        value : Any
            Value to put. Must be an unwrapped value of some kind.
        """
        provider = self.provider_put if provider_override == Provider.INHERIT else provider_override
        match provider:
            case Provider.PVA:
                return self.pva_ctxt.put(pv_name, value)
            case Provider.CA:
                return epics.caput(pv_name, value)
            case _:
                if pv_name not in self.pv_provider_cache:
                    try:
                        value = self.put(pv_name, value, Provider.PVA)
                        self.pv_provider_cache[pv_name] = Provider.PVA
                        return value
                    except TimeoutError:
                        pass
                    if (value := self.put(pv_name, value, Provider.CA)) is None or value < 0:
                        return None
                    self.pv_provider_cache[pv_name] = Provider.CA
                    return value
                else:
                    return self.put(pv_name, value, self.pv_provider_cache[pv_name])

    def __setitem__(self, pv_name: str, value):
        return self.put(pv_name, value)

    def info_ca(self, pv_name: str):
        # Only supported by PyEPICS
        return epics.cainfo(pv_name, print_out=False)

    def _posix2epics_ts(self, posixSecondsPastEpoch: int) -> int:
        """Convert a POSIX timestamp to an EPICS timestamp"""
        return posixSecondsPastEpoch - 631152000 # See POSIX_TIME_AT_EPICS_EPOCH in epicsTime.h

    def monitor(self, pv_name: str, callback, provider_override: Provider = Provider.UNKNOWN) -> Monitor:
        """
        Monitor a specific PV.
        
        The callback's **kwargs matches what pyepics supplies to monitor callbacks, with the following exceptions:
        - 'cb_info', 'host' & 'access' are unsupported and always set to None
        - 'write_access' is unsupported and always set to True
        - 'ftype' and 'chid' are *only* set for CA callbacks for informational purposes
        - 'pva_value' is set for PVA callbacks and provides the full p4p.Value structure

        Parameters
        ----------
        pv_name : str
            Name of the PV
        callback : Callable
        
        Returns
        -------
        Monitor :
            An instance of the Monitor class. This can be used to close out the monitor when it's no longer needed.
        """
        provider = self.provider_mon if provider_override == Provider.INHERIT else provider_override
        mon = None
        match provider:
            case Provider.PVA:
                sub = self.pva_ctxt.monitor(pv_name, lambda val, pv=pv_name: self._pv_monitor_callback(pv, val))
                if sub is None:
                    return False
                mon = Monitor(pv_name, callback, self, sub)
            case Provider.CA:
                epics.camonitor(pv_name, writer=None, callback=self._ca_monitor_callback)
                mon = Monitor(pv_name, callback, self, None)
            case _:
                if pv_name not in self.pv_provider_cache:
                    try:
                        monitor = self.monitor(pv_name, callback, Provider.PVA)
                        self.pv_provider_cache[pv_name] = Provider.PVA
                        return monitor
                    except TimeoutError:
                        pass
                    monitor = self.monitor(pv_name, callback, Provider.CA)
                    self.pv_provider_cache[pv_name] = Provider.CA
                    return monitor
                else:
                    return self.monitor(pv_name, callback, self.pv_provider_cache[pv_name])

        # Add monitors to the list of registered monitors
        if pv_name not in self.monitors:
            self.monitors[pv_name] = []
        self.monitors[pv_name].append(mon)
        return mon

    def close_monitor(self, monitor: Monitor):
        """Close out a monitor"""
        if monitor.pv not in self.monitors:
            return
        self.monitors[monitor.pv].remove(monitor)

    def _ca_monitor_callback(self, **kwargs):
        """Proxies CA callbacks into the registered callbacks"""
        if kwargs['pvname'] not in self.monitors:
            return

        # Modify kwargs to closely match what we get from a PVA callback.
        # This is just to avoid cases where CA monitors work with your code, and PVA monitors don't
        for f in ['cb_info', 'host', 'access', 'pva_value']:
            kwargs[f] = None
        kwargs['write_access'] = True # Match what we do in PVA callbacks

        for k in self.monitors[kwargs['pvname']]:
            if k.protocol() != Provider.CA:
                continue
            k.cb(**kwargs)

    def _pv_monitor_callback(self, pv: str, value: Value | Exception):
        """Handles unpacking of NT structures into kwargs for the callback"""
        if pv not in self.monitors:
            return

        if isinstance(value, Value):
            # Init all fields to None
            r = {}
            fields = [
                'pvname','value','char_value','count','ftype','type','status','precision','units','severity',
                'timestamp','read_access','write_access','access','host','enum_strs','upper_disp_limit',
                'lower_disp_limit','upper_alarm_limit','lower_alarm_limit','upper_warning_limit','lower_warning_limit',
                'upper_ctrl_limit','lower_ctrl_limit','chid','cb_info'
            ]
            for k in fields:
                r[k] = None

            r['pvname'] = pv
            r['write_access'] = True # Probably not possible to determine with p4p
            r['read_access'] = True

            r['pva_value'] = value

            # TODO: enum_strs with NTEnum: "enum_strs: the list of enumeration strings"

            # TODO: Still need support for NTNDArray & NTEnum. The rest of the NT types in the spec are seldom used.
            id = value.getID()
            if id.startswith('epics:nt/NTScalar:'):
                r['value'] = value['value']
                r['type'] = type(value['value'])
                r['char_value'] = str(value['value'])
            elif id.startswith('epics:nt/NTScalarArray:'):
                # Untested -- Yell at Jeremy L. if this throws an error
                r['value'] = value['value']
                r['type'] = type(value['value'][0])
                r['char_value'] = str(' '.join(value['value']))
                r['count'] = len(value['value'])
            elif id.startswith('epics:nt/NTTable:'):
                # Untested -- Yell at Jeremy L. if this throws an error
                tab = {}
                n = 0
                for l in value['labels']:
                    tab[l] = value['value'][n]
                    n += 1
                r['type'] = dict
                r['value'] = tab
                r['char_value'] = str(tab)
                r['count'] = len(tab.keys())
            else:
                raise TypeError(f'Unsupported NT type {id}')

            def unpack_fl(fl) -> float | None:
                """Replace NaN with None, which signifies 'not provided' in pyepics"""
                return None if math.isnan(fl) else fl

            # Unpack display_t
            if 'display' in value:
                v = value['display']
                r['precision'] = v['precision']
                r['units'] = v['units']
                r['upper_disp_limit'] = unpack_fl(v['limitHigh'])
                r['lower_disp_limit'] = unpack_fl(v['limitLow'])
                # TODO: enum_strs

            # Unpack alarm_t
            if 'alarm' in value:
                v = value['alarm']
                r['severity'] = v['severity']
                r['status'] = v['status']

            # Unpack timestamp_t
            if 'timeStamp' in value:
                # TODO: Posix or EPICS time?
                r['timestamp'] = float(value['timeStamp']['secondsPastEpoch']) + value['timeStamp']['nanoseconds'] / 1e9

            # Unpack control_t
            if 'control' in value:
                v = value['control']
                r['lower_ctrl_limit'] = unpack_fl(v['lowLimit'])
                r['upper_ctrl_limit'] = unpack_fl(v['highLimit'])
                # TODO: Min step?

            # Unpack valueAlarm_t
            if 'valueAlarm' in value:
                v = value['valueAlarm']
                r['upper_alarm_limit'] = unpack_fl(v['highAlarmLimit'])
                r['lower_alarm_limit'] = unpack_fl(v['lowAlarm'])
                r['upper_warning_limit'] = unpack_fl(v['highWarningLimit'])
                r['lower_warning_limit'] = unpack_fl(v['lowWarningLimit'])

            # Invoke all monitors for this PV
            for mon in self.monitors[pv]:
                if mon.protocol() != Provider.PVA:
                    continue
                mon.cb(**r.copy())

    def rpc_pva(self, pv_name: str, value, **kwargs):
        # Only supported by PVA
        return self.pva_ctxt.rpc(pv_name, value, **kwargs)

    def reset_provider_cache(self):
        self.pv_provider_cache = {}
