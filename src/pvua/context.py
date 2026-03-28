from enum import IntEnum
import epics
import math
from p4p.client.thread import Context as PVAContext
# noinspection PyProtectedMember
from p4p.client.thread import Subscription
from p4p import Value
from typing import Any, Callable


class Provider(IntEnum):
    INHERIT = 0  # Inherit provider from context default
    UNKNOWN = 1  # Will use PVA then CA until one works
    CA = 2
    PVA = 3


class Context:
    class Monitor:
        """
        Wrapper around PV monitors. Do not instantiate directly, use the monitor method on a Context instance instead.
        """

        def __init__(self, pvname: str, callback: Callable, context: "Context", pva_subscription: Subscription | None):
            self.pvname = pvname
            self.callback = callback
            self.context = context
            self.pva_subscription = pva_subscription

        def close(self) -> None:
            """
            Closes the monitor.
            """
            if self.pva_subscription is not None:
                self.pva_subscription.close()

            if self.pvname in self.context.pv_monitors:
                self.context.pv_monitors[self.pvname].remove(self)

        @property
        def provider(self) -> Provider:
            """
            :return: The protocol used for the monitored PV
            """
            return Provider.PVA if self.pva_subscription is not None else Provider.CA

    @staticmethod
    def _posix_timestamp_to_epics(posix_seconds_past_epoch: int) -> int:
        """
        Convert a POSIX timestamp to an EPICS timestamp.
        :param int posix_seconds_past_epoch: The POSIX timestamp to convert
        :return: The EPICS timestamp
        """
        return posix_seconds_past_epoch - 631152000  # See POSIX_TIME_AT_EPICS_EPOCH in epicsTime.h

    @staticmethod
    def _unpack_float(f: float) -> float | None:
        """
        Replace NaN with None, which signifies "not provided" in PyEPICS.
        :param float f: Float to unpack
        :return: The float value, or None if given NaN value
        """
        return None if math.isnan(f) else f

    @staticmethod
    def _unpack_pva_value(value: Value, init_all_keys=False) -> dict[str, Any]:
        if not isinstance(value, Value):
            return {}

        out: dict[str, Any] = {}
        if init_all_keys:
            # Init all fields to None
            out = {field: None for field in [
                "read_access",
                "write_access",
                "value",
                "char_value",
                "count",
                "ftype",
                "type",
                "status",
                "precision",
                "units",
                "severity",
                "timestamp",
                "access",
                "host",
                "enum_strs",
                "upper_disp_limit",
                "lower_disp_limit",
                "upper_alarm_limit",
                "lower_alarm_limit",
                "upper_warning_limit",
                "lower_warning_limit",
                "upper_ctrl_limit",
                "lower_ctrl_limit",
                "chid",
                "cb_info",
            ]}

        out["read_access"] = True
        out["write_access"] = True # Probably not possible to determine with p4p

        out["pva_value"] = value

        # TODO: enum_strs with NTEnum: "enum_strs: the list of enumeration strings"

        # TODO: Still need support for NTEnum. The rest of the NT types in the spec are seldom used.
        pva_id = value.getID()
        if pva_id.startswith("epics:nt/NTScalar:"):
            out["value"] = value["value"]
            out["type"] = type(value["value"])
            out["char_value"] = str(value["value"])
        elif pva_id.startswith("epics:nt/NTNDArray:"):
            out["value"] = value["value"]
            out["type"] = type(value["value"][0])
            out["count"] = 0
            for dim in value["dimension"]:
                out["count"] += dim["size"]
            out["char_value"] = repr(value["value"])  # seems good enough here
        elif pva_id.startswith("epics:nt/NTScalarArray:"):
            # Untested -- Yell at Jeremy L. if this throws an error
            out["value"] = value["value"]
            out["type"] = type(value["value"][0])
            out["char_value"] = str(" ".join(value["value"]))
            out["count"] = len(value["value"])
        elif pva_id.startswith("epics:nt/NTTable:"):
            # Untested -- Yell at Jeremy L. if this throws an error
            tab = {}
            n = 0
            for l in value["labels"]:
                tab[l] = value["value"][n]
                n += 1
            out["type"] = dict
            out["value"] = tab
            out["char_value"] = str(tab)
            out["count"] = len(tab.keys())
        else:
            raise TypeError(f"Unsupported NT type {pva_id}")

        out = {}
        if "alarm" in value.keys():
            out.update({
                "status": value["alarm"]["status"],
                "severity": value["alarm"]["severity"],
            })
        if "display" in value.keys():
            out.update({
                "precision": value["display"]["precision"],
                "units": value["display"]["units"],
                "upper_disp_limit": Context._unpack_float(value["display"]["limitHigh"]),
                "lower_disp_limit": Context._unpack_float(value["display"]["limitLow"]),
            })
        if "valueAlarm" in value.keys():
            out.update({
                "upper_alarm_limit": Context._unpack_float(value["valueAlarm"]["highAlarmLimit"]),
                "lower_alarm_limit": Context._unpack_float(value["valueAlarm"]["lowAlarm"]),
                "upper_warning_limit": Context._unpack_float(value["valueAlarm"]["highWarningLimit"]),
                "lower_warning_limit": Context._unpack_float(value["valueAlarm"]["lowWarningLimit"]),
            })
        if "control" in value.keys():
            out.update({
                "upper_ctrl_limit": Context._unpack_float(value["control"]["highLimit"]),
                "lower_ctrl_limit": Context._unpack_float(value["control"]["lowLimit"]),
            })
        if "timeStamp" in value.keys():
            # TODO: check if posix or EPICS time
            out["timestamp"] = float(value["timeStamp"]["secondsPastEpoch"]) + (value["timeStamp"]["nanoseconds"] / 1e9)
            out["posixseconds"] = value["timeStamp"]["secondsPastEpoch"],
            out["nanoseconds"] = value["timeStamp"]["nanoseconds"]

        return out

    def __init__(self, pva_ctxt=None, provider_get=Provider.UNKNOWN, provider_put=Provider.UNKNOWN, provider_monitor=Provider.UNKNOWN):
        """
        :param pva_ctxt: p4p context to use, or None to create a new one. NOTE: In order for this to work correctly, the PVA context must be created with nt=False.
        :param Provider provider_get: Provider override for gets
        :param Provider provider_put: Provider override for puts
        :param Provider provider_monitor: Provider override for monitors
        """
        if pva_ctxt is None:
            # noinspection PyTypeChecker
            self.pva_ctxt = PVAContext("pva", nt=False)
        else:
            self.pva_ctxt = pva_ctxt

        self.provider_get = provider_get     if provider_get     != Provider.INHERIT else Provider.UNKNOWN
        self.provider_put = provider_put     if provider_put     != Provider.INHERIT else Provider.UNKNOWN
        self.provider_mon = provider_monitor if provider_monitor != Provider.INHERIT else Provider.UNKNOWN

        self.pv_provider_cache: dict[str, Provider] = {}
        self.pv_monitors: dict[str, list[Context.Monitor]] = {}

    def determine_providers(self, pvnames: list[str]) -> None:
        """
        Given a list of PVs, issue a GET per PV to cache the available provider.
        :param list[str] pvnames: List of PVs to cache. If they're already cached, they will be skipped.
        """
        for pvname in pvnames:
            if pvname not in self.pv_provider_cache:
                # Issue a GET and discard the result
                self.get(pvname=pvname, provider_override=Provider.UNKNOWN)

    def get_provider(self, pvname: str) -> Provider:
        """
        :param str pvname: PV to get provider of
        :return: The provider for the given PV, or Provider.UNKNOWN if no known provider
        """
        if pvname in self.pv_provider_cache:
            return self.pv_provider_cache[pvname]
        return Provider.UNKNOWN

    def get(self, pvname: str, count: int | None = None, as_string: bool = False, as_numpy: bool = False, timeout: float | None = None, provider_override: Provider = Provider.INHERIT):
        """
        Issue a GET request to a PV.
        :param int/None count: Explicit limit of the size of array values
        :param str pvname: Name of the PV to GET
        :param bool as_string: If true, convert the value to string before returning
        :param bool as_numpy: If true, convert array to a NumPy array before returning
        :param float/None timeout: Timeout in seconds to wait for a response
        :param Provider provider_override: Provider to use. Default of INHERIT will use the setting on the Context
        """
        provider = self.provider_get if provider_override == Provider.INHERIT else provider_override
        match provider:
            case Provider.PVA:
                value = self.pva_ctxt.get(pvname, timeout=timeout)["value"]
                if as_string:
                    value = str(value)
                if as_numpy and epics.ca.HAS_NUMPY and not isinstance(value, epics.ca.numpy.ndarray):
                    if count is not None and count < len(value):
                        value = value[:count]
                    value = epics.ca.numpy.asarray(value)
                elif not as_numpy and epics.ca.HAS_NUMPY and isinstance(value, epics.ca.numpy.ndarray):
                    value = value.tolist()
                    if count is not None and count < len(value):
                        value = value[:count]
                return value
            case Provider.CA:
                return epics.caget(pvname, count=count, as_string=as_string, as_numpy=as_numpy, timeout=timeout)
            case _:
                if pvname not in self.pv_provider_cache:
                    try:
                        if (value := self.get(pvname, count=count, as_string=as_string, as_numpy=as_numpy, timeout=timeout, provider_override=Provider.PVA)) is not None:
                            self.pv_provider_cache[pvname] = Provider.PVA
                            return str(value) if as_string else value
                    except TimeoutError:
                        pass
                    if (value := self.get(pvname, count=count, as_string=as_string, as_numpy=as_numpy, timeout=timeout, provider_override=Provider.CA)) is not None:
                        self.pv_provider_cache[pvname] = Provider.CA
                        return value
                    else:
                        return None
                else:
                    return self.get(pvname, count=count, as_string=as_string, as_numpy=as_numpy, timeout=timeout, provider_override=self.pv_provider_cache[pvname])

    def __getitem__(self, pvname: str):
        return self.get(pvname)

    def get_ctrlvars(self, pvname: str, provider_override: Provider = Provider.INHERIT):
        """
        Issue a GET request to a PV, returning control variables.
        :param str pvname: Name of the PV
        :param Provider provider_override: Provider to use. Default of INHERIT will use the setting on the Context
        :return: Dictionary containing control variables
        """
        provider = self.provider_get if provider_override == Provider.INHERIT else provider_override
        match provider:
            case Provider.PVA:
                value = self.pva_ctxt.get(pvname)
                if value is not None:
                    ctrl_data = Context._unpack_pva_value(value)
                    return {key: ctrl_data[key] for key in (
                        "status", "severity", "precision", "units", "enum_strs",
                        "upper_disp_limit", "lower_disp_limit", "upper_alarm_limit",
                        "lower_alarm_limit", "upper_warning_limit", "lower_warning_limit",
                        "upper_ctrl_limit", "lower_ctrl_limit"
                    ) if key in ctrl_data}
                return None
            case Provider.CA:
                ctrl_data = epics.PV(pvname).get_ctrlvars()
                if ctrl_data is not None:
                    return {key: ctrl_data[key] for key in (
                        "status", "severity", "precision", "units", "enum_strs",
                        "upper_disp_limit", "lower_disp_limit", "upper_alarm_limit",
                        "lower_alarm_limit", "upper_warning_limit", "lower_warning_limit",
                        "upper_ctrl_limit", "lower_ctrl_limit"
                    ) if key in ctrl_data}
                return None
            case _:
                if pvname not in self.pv_provider_cache:
                    try:
                        if (value := self.get_ctrlvars(pvname, Provider.PVA)) is not None:
                            self.pv_provider_cache[pvname] = Provider.PVA
                            return value
                    except TimeoutError:
                        pass
                    if (value := self.get_ctrlvars(pvname, Provider.CA)) is not None:
                        self.pv_provider_cache[pvname] = Provider.CA
                        return value
                    else:
                        return None
                else:
                    return self.get_ctrlvars(pvname, self.pv_provider_cache[pvname])

    def get_timevars(self, pvname: str, provider_override: Provider = Provider.INHERIT):
        """
        Issue a GET request to a PV, returning timestamp.
        :param str pvname: Name of the PV
        :param Provider provider_override: Provider to use. Default of INHERIT will use the setting on the Context
        :return: Dictionary containing timestamp
        """
        provider = self.provider_get if provider_override == Provider.INHERIT else provider_override
        match provider:
            case Provider.PVA:
                value = self.pva_ctxt.get(pvname)
                if value is not None:
                    time_data = Context._unpack_pva_value(value)
                    return {key: time_data[key] for key in (
                        "timestamp", "posixseconds", "nanoseconds",
                    ) if key in time_data}
                return None
            case Provider.CA:
                time_data = epics.PV(pvname).get_timevars()
                if time_data is not None:
                    return {key: time_data[key] for key in (
                        "timestamp", "posixseconds", "nanoseconds",
                    ) if key in time_data}
                return None
            case _:
                if pvname not in self.pv_provider_cache:
                    try:
                        if (value := self.get_timevars(pvname, Provider.PVA)) is not None:
                            self.pv_provider_cache[pvname] = Provider.PVA
                            return value
                    except TimeoutError:
                        pass
                    if (value := self.get_timevars(pvname, Provider.CA)) is not None:
                        self.pv_provider_cache[pvname] = Provider.CA
                        return value
                    else:
                        return None
                else:
                    return self.get_timevars(pvname, self.pv_provider_cache[pvname])

    def put(self, pvname: str, value, provider_override: Provider = Provider.INHERIT):
        """
        Issue a PUT request to a PV.
        :param str pvname: Name of the PV to PUT
        :param value: Value to put. Must be an unwrapped value of some kind
        :param Provider provider_override: Provider to use. Default of INHERIT will use the setting on the Context
        """
        provider = self.provider_put if provider_override == Provider.INHERIT else provider_override
        match provider:
            case Provider.PVA:
                return self.pva_ctxt.put(pvname, value)
            case Provider.CA:
                return epics.caput(pvname, value)
            case _:
                if pvname not in self.pv_provider_cache:
                    try:
                        value = self.put(pvname, value, Provider.PVA)
                        self.pv_provider_cache[pvname] = Provider.PVA
                        return value
                    except TimeoutError:
                        pass
                    if (value := self.put(pvname, value, Provider.CA)) is None or value < 0:
                        return None
                    self.pv_provider_cache[pvname] = Provider.CA
                    return value
                else:
                    return self.put(pvname, value, self.pv_provider_cache[pvname])

    def __setitem__(self, pvname: str, value):
        return self.put(pvname, value)

    def info_ca(self, pvname: str) -> str:
        """
        Only supported by PyEPICS.
        :param str pvname: Name of the PV
        :return: A human-readable string with PV metadata
        """
        return epics.cainfo(pvname, print_out=False)

    def monitor(self, pvname: str, callback, provider_override: Provider = Provider.UNKNOWN) -> Monitor | None:
        """
        Monitor a specific PV.

        The callback's **kwargs matches what PyEPICS supplies to monitor callbacks, with the following exceptions:
        - "cb_info", "host", and "access" are unsupported and always set to None
        - "write_access" is unsupported and always set to True
        - "ftype" and "chid" are *only* set for CA callbacks for informational purposes
        - "pva_value" is set for PVA callbacks and provides the full p4p.Value structure

        :param str pvname: Name of the PV
        :param callback: Callback for when the PV value changes
        :param Provider provider_override: Provider to use. Default of INHERIT will use the setting on the Context
        :return: An instance of the Monitor class, which can be used to close the monitor
        """
        provider = self.provider_mon if provider_override == Provider.INHERIT else provider_override
        mon = None
        match provider:
            case Provider.PVA:
                sub = self.pva_ctxt.monitor(pvname, lambda val, pv=pvname: self._pv_monitor_callback(pv, val))
                if sub is None:
                    return None
                mon = Context.Monitor(pvname, callback, self, sub)
            case Provider.CA:
                epics.camonitor(pvname, writer=None, callback=self._ca_monitor_callback)
                mon = Context.Monitor(pvname, callback, self, None)
            case _:
                if pvname not in self.pv_provider_cache:
                    try:
                        if (monitor := self.monitor(pvname, callback, Provider.PVA)) is not None:
                            self.pv_provider_cache[pvname] = Provider.PVA
                            return monitor
                    except TimeoutError:
                        pass
                    if (monitor := self.monitor(pvname, callback, Provider.CA)) is not None:
                        self.pv_provider_cache[pvname] = Provider.CA
                        return monitor
                    else:
                        return None
                else:
                    return self.monitor(pvname, callback, self.pv_provider_cache[pvname])

        # Add monitors to the list of registered monitors
        if pvname not in self.pv_monitors:
            self.pv_monitors[pvname] = []
        self.pv_monitors[pvname].append(mon)
        return mon

    def _ca_monitor_callback(self, **kwargs):
        """
        Proxies CA callbacks into the registered callbacks.
        :param kwargs: Callback information provided by PyEPICS
        """
        if kwargs["pvname"] not in self.pv_monitors:
            return

        # Modify kwargs to closely match what we get from a PVA callback.
        # This is just to avoid cases where CA monitors work with your code, and PVA monitors don't
        for field in ["cb_info", "host", "access", "pva_value"]:
            kwargs[field] = None
        kwargs["write_access"] = True

        # Invoke all monitors for this PV
        for monitor in self.pv_monitors[kwargs["pvname"]]:
            if monitor.provider != Provider.CA:
                continue
            monitor.callback(**kwargs)

    def _pv_monitor_callback(self, pv: str, value: Value | Exception):
        """
        Handles unpacking of NT structures into kwargs for registered callbacks.
        :param str pv: Name of the PV
        :param Value/Exception value: Callback information provided by p4p
        """
        if pv not in self.pv_monitors or not isinstance(value, Value):
            return

        r = Context._unpack_pva_value(value, init_all_keys=True)
        r["pvname"] = pv

        # Invoke all monitors for this PV
        for monitor in self.pv_monitors[pv]:
            if monitor.provider != Provider.PVA:
                continue
            monitor.callback(**r.copy())

    def rpc_pva(self, pvname: str, value: Value, **kwargs):
        """
        Only supported by p4p.
        :param str pvname: Name of the PV
        :param Value value: Value to put
        :param kwargs: Extra arguments for p4p
        :return: A p4p Value, or an exception
        """
        return self.pva_ctxt.rpc(pvname, value, **kwargs)

    def reset_provider_cache(self) -> None:
        """
        Resets the provider cache.
        """
        self.pv_provider_cache = {}
