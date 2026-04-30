import epics

from .context import Provider, Context


class PV:
    """
    Intended to be a (mostly) drop-in replacement for PV objects from PyEPICS.
    """

    def __init__(self, context: Context, pvname: str, provider_get_override: Provider = Provider.INHERIT, provider_put_override: Provider = Provider.INHERIT, provider_mon_override: Provider = Provider.INHERIT):
        self.context = context
        self.pvname = pvname
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

    def force_connect(self, pvname=None, **kwargs) -> None:
        if self.ca_obj is not None:
            self.ca_obj.force_connect(pvname, **kwargs)
            if pvname is not None:
                self.pvname = pvname

    def force_read_access_rights(self) -> None:
        if self.ca_obj is not None:
            self.ca_obj.force_read_access_rights()

    # auto_monitor

    # auto_monitor_mask

    def wait_for_connection(self, timeout: int | float | None = None) -> bool:
        if self.ca_obj is not None:
            self.ca_obj.wait_for_connection(timeout=timeout)
        return True

    def connect(self, timeout: int | float | None = None) -> bool:
        if self.ca_obj is not None:
            return self.ca_obj.connect(timeout=timeout)
        return True

    @property
    def connected(self) -> bool:
        if self.ca_obj is not None:
            return self.ca_obj.connected
        return True

    # clear_auto_monitor

    def reconnect(self) -> bool:
        if self.ca_obj is not None:
            return self.ca_obj.reconnect()
        return True

    # poll

    # noinspection PyUnusedLocal
    def get(self, count: int | None = None, as_string: bool = False, as_numpy: bool = True, timeout: float | None = None, with_ctrlvars: bool = False, **kwargs):
        if with_ctrlvars:
            return {
                "value": self.context.get(self.pvname, count=count, as_string=as_string, as_numpy=as_numpy, timeout=timeout, provider_override=self.provider_get_override),
                **self.context.get_ctrlvars(self.pvname, provider_override=self.provider_get_override)
            }
        else:
            return self.context.get(self.pvname, count=count, as_string=as_string, as_numpy=as_numpy, timeout=timeout, provider_override=self.provider_get_override)

    def get_with_metadata(self, count: int | None = None, as_string: bool = False, as_numpy: bool = True, timeout : float | None = None, with_ctrlvars: bool = False, as_namespace: bool = False):
        if self.ca_obj is not None:
            return self.ca_obj.get_with_metadata(count=count, as_string=as_string, as_numpy=as_numpy, timeout=timeout, with_ctrlvars=with_ctrlvars, as_namespace=as_namespace)
        return self.context.get_with_metadata(self.pvname, count=count, as_string=as_string, as_numpy=as_numpy, timeout=timeout, with_ctrlvars=with_ctrlvars, as_namespace=as_namespace, provider_override=self.provider_get_override)

    def put(self, value, timeout: float = 30.0):
        if self.ca_obj is not None:
            return self.ca_obj.put(value, timeout=timeout)
        return self.context.put(self.pvname, value=value, timeout=timeout, provider_override=self.provider_put_override)

    def monitor(self, callback):
        return self.context.monitor(self.pvname, callback=callback, provider_override=self.provider_mon_override)

    def get_ctrlvars(self, as_namespace: bool = False):
        if self.ca_obj is not None:
            # Match Context::get_ctrlvars
            ctrl_data = self.ca_obj.get_ctrlvars()
            return {key: ctrl_data[key] for key in (
                "status", "severity", "precision", "units", "enum_strs",
                "upper_disp_limit", "lower_disp_limit", "upper_alarm_limit",
                "lower_alarm_limit", "upper_warning_limit", "lower_warning_limit",
                "upper_ctrl_limit", "lower_ctrl_limit"
            ) if key in ctrl_data}
        return self.context.get_ctrlvars(self.pvname, as_namespace=as_namespace, provider_override=self.provider_get_override)

    def get_timevars(self, as_namespace: bool = False):
        if self.ca_obj is not None:
            # Match Context::get_timevars
            time_data = self.ca_obj.get_timevars()
            return {key: time_data[key] for key in (
                "timestamp", "posixseconds", "nanoseconds",
            ) if key in time_data}
        return self.context.get_timevars(self.pvname, as_namespace=as_namespace, provider_override=self.provider_get_override)

    def run_callbacks(self) -> None:
        if self.ca_obj is not None:
            self.ca_obj.run_callbacks()

    def run_callback(self, index: int | None = None) -> None:
        if self.ca_obj is not None:
            self.ca_obj.run_callback(index)

    def add_callback(self, callback=None, index: int | None = None, run_now: bool = False, with_ctrlvars: bool = True, **kwargs):
        if self.ca_obj is not None:
            return self.ca_obj.add_callback(
                callback=callback, index=index, run_now=run_now,
                with_ctrlvars=with_ctrlvars, **kwargs,
            )
        # Fallback: delegate to context monitor
        self.context.monitor(self.pvname, callback, self.provider_mon_override)
        return 0

    def remove_callback(self, index: int | None = None) -> None:
        if self.ca_obj is not None:
            self.ca_obj.remove_callback(index=index)

    def clear_callbacks(self) -> None:
        if self.ca_obj is not None:
            self.ca_obj.clear_callbacks()

    def __getval__(self):
        return self.get()

    @property
    def value(self):
        return self.__getval__()

    def __setval__(self, val) -> None:
        self.put(val)

    @value.setter
    def value(self, value):
        self.__setval__(value)

    @property
    def char_value(self) -> str | None:
        if self.ca_obj is not None:
            return self.ca_obj.char_value
        # TODO
        return None

    @property
    def status(self) -> int | None:
        if self.ca_obj is not None:
            return self.ca_obj.status
        return self.context.get_ctrlvars(self.pvname, provider_override=self.provider_get_override).get("status")

    @property
    def char_status(self) -> str | None:
        if self.ca_obj is not None:
            return self.ca_obj.char_status
        # TODO
        return None

    @property
    def type(self) -> str | None:
        if self.ca_obj is not None:
            return self.ca_obj.type
        # TODO
        return None

    @property
    def typefull(self) -> str | None:
        if self.ca_obj is not None:
            return self.ca_obj.typefull
        # TODO
        return None

    @property
    def host(self) -> str | None:
        if self.ca_obj is not None:
            return self.ca_obj.host
        # TODO
        return None
        #return self.context.get_ctrlvars(self.pvname, provider_override=self.provider_get_override).get("host")

    @property
    def count(self) -> int | None:
        if self.ca_obj is not None:
            return self.ca_obj.count
        # TODO
        return None

    @property
    def nelm(self) -> int | None:
        if self.ca_obj is not None:
            return self.ca_obj.nelm
        # TODO
        return None

    @property
    def read_access(self) -> bool:
        if self.ca_obj is not None:
            return bool(self.ca_obj.read_access)
        return True

    @property
    def write_access(self) -> bool:
        if self.ca_obj is not None:
            return bool(self.ca_obj.write_access)
        return True

    @property
    def access(self) -> str:
        if self.ca_obj is not None:
            return self.ca_obj.access
        return "read/write"

    # monitor delta

    @property
    def severity(self) -> int | None:
        if self.ca_obj is not None:
            return self.ca_obj.severity
        return self.context.get_ctrlvars(self.pvname, provider_override=self.provider_get_override).get("severity")

    @property
    def char_severity(self) -> str | None:
        if self.ca_obj is not None:
            return self.ca_obj.char_severity
        # TODO
        return None

    @property
    def timestamp(self) -> float | None:
        if self.ca_obj is not None:
            return self.ca_obj.timestamp
        return self.context.get_timevars(self.pvname, provider_override=self.provider_get_override).get("timestamp")

    @property
    def posixseconds(self) -> int | None:
        if self.ca_obj is not None:
            return self.ca_obj.posixseconds
        return self.context.get_timevars(self.pvname, provider_override=self.provider_get_override).get("posixseconds")

    @property
    def nanoseconds(self) -> int | None:
        if self.ca_obj is not None:
            return self.ca_obj.nanoseconds
        return self.context.get_timevars(self.pvname, provider_override=self.provider_get_override).get("nanoseconds")

    @property
    def precision(self) -> int | None:
        if self.ca_obj is not None:
            return self.ca_obj.precision
        return self.context.get_ctrlvars(self.pvname, provider_override=self.provider_get_override).get("precision")

    @property
    def units(self) -> str | None:
        if self.ca_obj is not None:
            return self.ca_obj.units
        return self.context.get_ctrlvars(self.pvname, provider_override=self.provider_get_override).get("units")

    @property
    def enum_strs(self) -> list[str] | None:
        if self.ca_obj is not None:
            return self.ca_obj.enum_strs
        return self.context.get_ctrlvars(self.pvname, provider_override=self.provider_get_override).get("enum_strs")

    @property
    def upper_disp_limit(self) -> float | None:
        if self.ca_obj is not None:
            return self.ca_obj.upper_disp_limit
        return self.context.get_ctrlvars(self.pvname, provider_override=self.provider_get_override).get("upper_disp_limit")

    @property
    def lower_disp_limit(self) -> float | None:
        if self.ca_obj is not None:
            return self.ca_obj.lower_disp_limit
        return self.context.get_ctrlvars(self.pvname, provider_override=self.provider_get_override).get("lower_disp_limit")

    @property
    def upper_alarm_limit(self) -> float | None:
        if self.ca_obj is not None:
            return self.ca_obj.upper_alarm_limit
        return self.context.get_ctrlvars(self.pvname, provider_override=self.provider_get_override).get("upper_alarm_limit")

    @property
    def lower_alarm_limit(self) -> float | None:
        if self.ca_obj is not None:
            return self.ca_obj.lower_alarm_limit
        return self.context.get_ctrlvars(self.pvname, provider_override=self.provider_get_override).get("lower_alarm_limit")

    @property
    def lower_warning_limit(self) -> float | None:
        if self.ca_obj is not None:
            return self.ca_obj.lower_warning_limit
        return self.context.get_ctrlvars(self.pvname, provider_override=self.provider_get_override).get("lower_warning_limit")

    @property
    def upper_warning_limit(self) -> float | None:
        if self.ca_obj is not None:
            return self.ca_obj.upper_warning_limit
        return self.context.get_ctrlvars(self.pvname, provider_override=self.provider_get_override).get("upper_warning_limit")

    @property
    def upper_ctrl_limit(self) -> float | None:
        if self.ca_obj is not None:
            return self.ca_obj.upper_ctrl_limit
        return self.context.get_ctrlvars(self.pvname, provider_override=self.provider_get_override).get("upper_ctrl_limit")

    @property
    def lower_ctrl_limit(self) -> float | None:
        if self.ca_obj is not None:
            return self.ca_obj.lower_ctrl_limit
        return self.context.get_ctrlvars(self.pvname, provider_override=self.provider_get_override).get("lower_ctrl_limit")

    @property
    def info(self) -> str | None:
        if self.ca_obj is not None:
            return self.ca_obj.info
        return self.context.info_ca(self.pvname)

    # put_complete

    def __str__(self) -> str:
        return self.info() or ''

    def __repr__(self) -> str:
        if self.ca_obj is not None:
            return repr(self.ca_obj)
        return f"<PV '{self.pvname}' {'connected' if self.connected else 'disconnected'}>"

    def __eq__(self, other) -> bool:
        if self.ca_obj is not None and other.ca_obj is not None:
            return self.ca_obj == other.ca_obj
        if isinstance(other, PV):
            return self.pvname == other.pvname
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.pvname)

    def disconnect(self) -> None:
        if self.ca_obj is not None:
            self.ca_obj.disconnect()
