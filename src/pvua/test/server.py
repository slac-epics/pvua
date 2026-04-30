import asyncio
import threading
import time
from typing import Any

import numpy as np
import pytest


pv_data: dict = {
    "TEST:FLOAT": {
        "value": -20.0,
        "type": "d",
        "units": "percent",
        "doc": "Temperature delta",
    },
    "TEST:INT": {
        "value": 9,
        "type": "i",
        "units": "",
        "doc": "Stage",
    },
    "TEST:STRING": {
        "value": "MLP",
        "type": "s",
        "units": "",
        "doc": "Acronym",
    },
    "TEST:INTARRAY": {
        "value": [4, 1, 3],
        "type": "aB",
        "units": "",
        "doc": "Integer sequence",
    },
    "TEST:ENUM": {
        "value": 2,
        "type": "enum",
        "enum_strs": ["OFF", "ON", "HALFWAY_ON"],
        "doc": "Enum"
	},
}
pv_lock = threading.Lock()


def start_ca_server() -> threading.Thread:
    from caproto.server import PVGroup, pvproperty, run as caproto_run
    from caproto import ChannelType

    class SIOC(PVGroup):
        float_pv = pvproperty(
            name="FLOAT",
            value=pv_data["TEST:FLOAT"]["value"],
            dtype=ChannelType.DOUBLE,
            units=pv_data["TEST:FLOAT"]["units"],
            doc=pv_data["TEST:FLOAT"]["doc"],
        )

        int_pv = pvproperty(
            name="INT",
            value=pv_data["TEST:INT"]["value"],
            dtype=ChannelType.INT,
            units=pv_data["TEST:INT"]["units"],
            doc=pv_data["TEST:INT"]["doc"],
        )

        string_pv = pvproperty(
            name="STRING",
            value=pv_data["TEST:STRING"]["value"],
            dtype=ChannelType.STRING,
            doc=pv_data["TEST:STRING"]["doc"],
        )

        intarray_pv = pvproperty(
            name="INTARRAY",
            value=pv_data["TEST:INTARRAY"]["value"],
            dtype=ChannelType.INT,
            doc=pv_data["TEST:INTARRAY"]["doc"],
		)
        
        enum_pv = pvproperty(
            name="ENUM",
            value=pv_data["TEST:ENUM"]["value"],
            dtype=ChannelType.ENUM,
            enum_strings=pv_data["TEST:ENUM"]["enum_strs"],
            doc=pv_data["TEST:ENUM"]["doc"],
		)

    def run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        ioc = SIOC(prefix="TEST:")
        caproto_run(ioc.pvdb, startup_hook=None, log_pv_names=False)

    thread = threading.Thread(target=run, daemon=True, name="pvua-test-ca-server")
    thread.start()
    return thread


def start_pva_server() -> threading.Thread:
    from p4p.server import Server as P4PServer
    from p4p.server.thread import SharedPV
    from p4p.nt import NTEnum, NTScalar

    pvs: dict[str, SharedPV] = {}

    class PVHandler:
        def __init__(self, pvname: str):
            self.pvname = pvname

        def put(self, pv: SharedPV, op):
            value = op.value()
            with pv_lock:
                pv_data[self.pvname]["value"] = value["value"]
            new_value = pvs[self.pvname].current()
            new_value["value"] = value["value"]
            pv.post(new_value)
            op.done()

    pvs = {name: SharedPV(handler=PVHandler(name), initial=NTScalar(data["type"]).wrap(data["value"])) for name, data in pv_data.items() if name != "TEST:ENUM"}
    pvs["TEST:ENUM"] = SharedPV(handler=PVHandler("TEST:ENUM"), initial=NTEnum().wrap(pv_data["TEST:ENUM"]["value"], pv_data["TEST:ENUM"]["enum_strs"]))

    def update_pvs():
        while True:
            with pv_lock:
                snapshot = pv_data.copy()
            for name, spec in snapshot.items():
                if name in pvs:
                    try:
                        new_value = pvs[name].current()
                        new_value["value"] = spec["value"]
                        pvs[name].post(new_value)
                    except Exception as e:
                        print(f"[PVA] Error: {e}")
            time.sleep(0.1)

    def run():
        with P4PServer(providers=[pvs]) as server:
            update_thread = threading.Thread(target=update_pvs, daemon=True)
            update_thread.start()
            try:
                while True:
                    time.sleep(0.1)
            finally:
                    server.stop()

    thread = threading.Thread(target=run, daemon=True, name="pvua-test-pva-server")
    thread.start()
    return thread


@pytest.fixture(scope="session", autouse=True)
def ioc_servers():
    ca_thread  = start_ca_server()
    pva_thread = start_pva_server()

    # wait for sIOC startups
    time.sleep(1)
    yield ca_thread, pva_thread


@pytest.fixture(scope="session")
def ctx_ca():
    from pvua import Context, Provider
    return Context(provider_get=Provider.CA, provider_put=Provider.CA, provider_monitor=Provider.CA)


@pytest.fixture(scope="session")
def ctx_pva():
    from pvua import Context, Provider
    return Context(provider_get=Provider.PVA, provider_put=Provider.PVA, provider_monitor=Provider.PVA)


@pytest.fixture(scope="session")
def ctx_unk():
    from pvua import Context, Provider
    return Context(provider_get=Provider.UNKNOWN, provider_put=Provider.UNKNOWN, provider_monitor=Provider.UNKNOWN)


class TestContextCA:
    @pytest.fixture(autouse=True)
    def ready(self, ctx_ca, ioc_servers):
        ctx_ca.determine_providers(pv_data.keys())

    def test_get_float(self, ctx_ca):
        val = ctx_ca.get("TEST:FLOAT")
        assert isinstance(val, float)
        assert val == pytest.approx(pv_data["TEST:FLOAT"]["value"])

    def test_get_int(self, ctx_ca):
        val = ctx_ca.get("TEST:INT")
        assert val == pv_data["TEST:INT"]["value"]

    def test_get_string(self, ctx_ca):
        val = ctx_ca.get("TEST:STRING")
        assert val == pv_data["TEST:STRING"]["value"]

    def test_get_intarray_as_numpy(self, ctx_ca):
        val = ctx_ca.get("TEST:INTARRAY", as_numpy=True)
        assert isinstance(val, np.ndarray)
        for i in range(len(val)):
            assert val[i] == pv_data["TEST:INTARRAY"]["value"][i]

    def test_get_enum(self, ctx_ca):
        val = ctx_ca.get("TEST:ENUM")
        assert val == pv_data["TEST:ENUM"]["value"]

    def test_put_float_roundtrip(self, ctx_ca):
        ctx_ca.put("TEST:FLOAT", 42.5)
        time.sleep(0.2)
        val = ctx_ca.get("TEST:FLOAT")
        assert val == pytest.approx(42.5)
        # restore
        ctx_ca.put("TEST:FLOAT", pv_data["TEST:FLOAT"]["value"])

    def test_put_int_roundtrip(self, ctx_ca):
        ctx_ca.put("TEST:INT", 99)
        time.sleep(0.2)
        val = ctx_ca.get("TEST:INT")
        assert int(val) == 99
        ctx_ca.put("TEST:INT", pv_data["TEST:INT"]["value"])

    def test_put_string_roundtrip(self, ctx_ca):
        ctx_ca.put("TEST:STRING", "HELLO")
        time.sleep(0.2)
        val = ctx_ca.get("TEST:STRING", as_string=True)
        assert val == "HELLO"
        ctx_ca.put("TEST:STRING", pv_data["TEST:STRING"]["value"])

    def test_put_intarray_roundtrip(self, ctx_ca):
        ctx_ca.put("TEST:INTARRAY", [8, 1, 3])
        time.sleep(0.2)
        val = ctx_ca.get("TEST:INTARRAY")
        assert val == [8, 1, 3]
        ctx_ca.put("TEST:INTARRAY", pv_data["TEST:INTARRAY"]["value"])

    def test_put_enum_roundtrip(self, ctx_ca):
        ctx_ca.put("TEST:ENUM", 0)
        time.sleep(0.2)
        val = ctx_ca.get("TEST:ENUM")
        assert val == 0
        ctx_ca.put("TEST:ENUM", pv_data["TEST:ENUM"]["value"])

    def test_get_with_metadata_keys(self, ctx_ca):
        result = ctx_ca.get_with_metadata("TEST:FLOAT")
        assert isinstance(result, dict)
        assert "value" in result

    def test_get_with_metadata_as_namespace(self, ctx_ca):
        result = ctx_ca.get_with_metadata("TEST:FLOAT", as_namespace=True)
        assert hasattr(result, "value")

    def test_get_with_metadata_with_ctrlvars(self, ctx_ca):
        result = ctx_ca.get_with_metadata("TEST:FLOAT", with_ctrlvars=True)
        assert isinstance(result, dict)
        assert "value" in result

    def test_get_ctrlvars_returns_dict(self, ctx_ca):
        result = ctx_ca.get_ctrlvars("TEST:FLOAT")
        assert isinstance(result, dict)

    def test_get_timevars_returns_dict(self, ctx_ca):
        result = ctx_ca.get_timevars("TEST:FLOAT")
        assert isinstance(result, dict)

    def test_info_ca_returns_string(self, ctx_ca):
        result = ctx_ca.info_ca("TEST:FLOAT")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_determine_provider(self, ctx_ca):
        from pvua import Provider
        ctx_ca.determine_providers(["TEST:FLOAT"])
        p = ctx_ca.get_provider("TEST:FLOAT")
        assert isinstance(p, Provider)

    def test_get_provider_unknown_pv(self, ctx_ca):
        from pvua import Provider
        p = ctx_ca.get_provider("DEFINITELY:NOT:REAL")
        assert p == Provider.UNKNOWN

    def test_monitor_receives_callback(self, ctx_ca):
        received: list[Any] = []
        mon = ctx_ca.monitor("TEST:FLOAT", callback=lambda **kw: received.append(kw))
        assert mon is not None
        ctx_ca.put("TEST:FLOAT", 120.0)
        time.sleep(0.5)
        mon.close()
        assert len(received) > 0

    def test_monitor_provider_property(self, ctx_ca):
        from pvua import Provider
        mon = ctx_ca.monitor("TEST:FLOAT", callback=lambda **kw: None)
        assert mon is not None
        assert mon.provider in (Provider.CA, Provider.PVA, Provider.UNKNOWN)
        mon.close()


class TestContextPVA:
    @pytest.fixture(autouse=True)
    def ready(self, ctx_pva, ioc_servers):
        ctx_pva.determine_providers(pv_data.keys())

    def test_get_float(self, ctx_pva):
        val = ctx_pva.get("TEST:FLOAT")
        assert isinstance(val, float)
        assert val == pytest.approx(-20.0)

    def test_get_int(self, ctx_pva):
        val = ctx_pva.get("TEST:INT")
        assert val == pv_data["TEST:INT"]["value"]

    def test_get_string(self, ctx_pva):
        val = ctx_pva.get("TEST:STRING")
        assert val == pv_data["TEST:STRING"]["value"]

    def test_get_intarray_as_numpy(self, ctx_pva):
        val = ctx_pva.get("TEST:INTARRAY", as_numpy=True)
        assert isinstance(val, np.ndarray)
        for i in range(len(val)):
            assert val[i] == pv_data["TEST:INTARRAY"]["value"][i]

    def test_get_enum(self, ctx_pva):
        val = ctx_pva.get("TEST:ENUM")
        assert val == pv_data["TEST:ENUM"]["value"]

    def test_put_float_roundtrip(self, ctx_pva):
        ctx_pva.put("TEST:FLOAT", 42.5)
        time.sleep(0.2)
        val = ctx_pva.get("TEST:FLOAT")
        assert val == pytest.approx(42.5)
        # restore
        ctx_pva.put("TEST:FLOAT", pv_data["TEST:FLOAT"]["value"])

    def test_put_int_roundtrip(self, ctx_pva):
        ctx_pva.put("TEST:INT", 99)
        time.sleep(0.2)
        val = ctx_pva.get("TEST:INT")
        assert int(val) == 99
        ctx_pva.put("TEST:INT", pv_data["TEST:INT"]["value"])

    def test_put_string_roundtrip(self, ctx_pva):
        ctx_pva.put("TEST:STRING", "HELLO")
        time.sleep(0.2)
        val = ctx_pva.get("TEST:STRING", as_string=True)
        assert val == "HELLO"
        ctx_pva.put("TEST:STRING", pv_data["TEST:STRING"]["value"])

    def test_put_intarray_roundtrip(self, ctx_pva):
        ctx_pva.put("TEST:INTARRAY", [8, 1, 3])
        time.sleep(0.2)
        val = ctx_pva.get("TEST:INTARRAY")
        assert val == [8, 1, 3]
        ctx_pva.put("TEST:INTARRAY", pv_data["TEST:INTARRAY"]["value"])

    def test_put_enum_roundtrip(self, ctx_pva):
        ctx_pva.put("TEST:ENUM", 0)
        time.sleep(0.2)
        val = ctx_pva.get("TEST:ENUM")
        assert val == 0
        #ctx_pva.put("TEST:ENUM", pv_data["TEST:ENUM"]["value"])

    def test_get_with_metadata_keys(self, ctx_pva):
        result = ctx_pva.get_with_metadata("TEST:FLOAT")
        assert isinstance(result, dict)
        assert "value" in result

    def test_get_with_metadata_as_namespace(self, ctx_pva):
        result = ctx_pva.get_with_metadata("TEST:FLOAT", as_namespace=True)
        assert hasattr(result, "value")

    def test_get_with_metadata_with_ctrlvars(self, ctx_pva):
        result = ctx_pva.get_with_metadata("TEST:FLOAT", with_ctrlvars=True)
        assert isinstance(result, dict)
        assert "value" in result

    def test_get_ctrlvars_returns_dict(self, ctx_pva):
        result = ctx_pva.get_ctrlvars("TEST:FLOAT")
        assert isinstance(result, dict)

    def test_get_timevars_returns_dict(self, ctx_pva):
        result = ctx_pva.get_timevars("TEST:FLOAT")
        assert isinstance(result, dict)

    def test_info_ca_returns_string(self, ctx_pva):
        result = ctx_pva.info_ca("TEST:FLOAT")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_determine_provider(self, ctx_pva):
        from pvua import Provider
        ctx_pva.determine_providers(["TEST:FLOAT"])
        p = ctx_pva.get_provider("TEST:FLOAT")
        assert isinstance(p, Provider)

    def test_get_provider_unknown_pv(self, ctx_pva):
        from pvua import Provider
        p = ctx_pva.get_provider("DEFINITELY:NOT:REAL")
        assert p == Provider.UNKNOWN

    def test_monitor_receives_callback(self, ctx_pva):
        received: list[Any] = []
        mon = ctx_pva.monitor("TEST:FLOAT", callback=lambda **kw: received.append(kw))
        assert mon is not None
        ctx_pva.put("TEST:FLOAT", 120.0)
        time.sleep(0.5)
        mon.close()
        assert len(received) > 0

    def test_monitor_provider_property(self, ctx_pva):
        from pvua import Provider
        mon = ctx_pva.monitor("TEST:FLOAT", callback=lambda **kw: None)
        assert mon is not None
        assert mon.provider in (Provider.CA, Provider.PVA, Provider.UNKNOWN)
        mon.close()


class TestPVObject:
    @pytest.fixture(scope="class")
    def float_pv(self, ctx_ca, ioc_servers):
        from pvua import PV
        return PV(ctx_ca, "TEST:FLOAT")

    @pytest.fixture(scope="class")
    def int_pv(self, ctx_ca, ioc_servers):
        from pvua import PV
        return PV(ctx_ca, "TEST:INT")

    @pytest.fixture(scope="class")
    def string_pv(self, ctx_ca, ioc_servers):
        from pvua import PV
        return PV(ctx_ca, "TEST:STRING")
    
    @pytest.fixture(scope="class")
    def intarray_pv(self, ctx_ca, ioc_servers):
        from pvua import PV
        return PV(ctx_ca, "TEST:INTARRAY")
    
    @pytest.fixture(scope="class")
    def enum_pv(self, ctx_ca, ioc_servers):
        from pvua import PV
        return PV(ctx_ca, "TEST:ENUM")

    def test_connect_returns_bool(self, float_pv):
        assert isinstance(float_pv.connect(), bool)

    def test_connected_property(self, float_pv):
        float_pv.connect(timeout=5.0)
        assert float_pv.connected is True

    def test_wait_for_connection(self, float_pv):
        result = float_pv.wait_for_connection(timeout=5.0)
        assert result is True

    def test_disconnect_and_reconnect(self, float_pv):
        float_pv.disconnect()
        float_pv.reconnect()
        assert isinstance(float_pv.connected, bool)

    def test_force_connect(self, float_pv):
        float_pv.force_connect()

    def test_force_read_access_rights(self, float_pv):
        float_pv.force_read_access_rights()

    def test_get_float(self, float_pv):
        val = float_pv.get()
        assert val == pytest.approx(120.0)

    def test_pv_get_as_string(self, float_pv):
        val = float_pv.get(as_string=True)
        assert isinstance(val, str)

    def test_pv_get_as_numpy(self, float_pv):
        val = float_pv.get(as_numpy=True)
        assert val is not None

    def test_pv_get_with_ctrlvars(self, float_pv):
        val = float_pv.get(with_ctrlvars=True)
        assert val is not None

    def test_pv_put_roundtrip(self, float_pv):
        float_pv.put(99.9)
        time.sleep(0.2)
        val = float_pv.get()
        assert val == pytest.approx(99.9)
        float_pv.put(pv_data["TEST:FLOAT"]["value"])

    def test_pv_put_with_timeout(self, float_pv):
        float_pv.put(1.0, timeout=5.0)
        float_pv.put(pv_data["TEST:FLOAT"]["value"])

    def test_pv_value_property(self, float_pv):
        assert float_pv.value is not None

    def test_pv_get_ctrlvars(self, float_pv):
        result = float_pv.get_ctrlvars()
        assert result is not None

    def test_pv_get_timevars(self, float_pv):
        result = float_pv.get_timevars()
        assert result is not None

    def test_pv_get_with_metadata(self, float_pv):
        result = float_pv.get_with_metadata()
        assert isinstance(result, dict)
        assert "value" in result

    def test_pv_info(self, float_pv):
        info = float_pv.info
        assert info is None or isinstance(info, str)

    def test_access_property(self, float_pv):
        a = float_pv.access
        assert isinstance(a, str)

    def test_read_access_property(self, float_pv):
        assert isinstance(float_pv.read_access, bool)

    def test_write_access_property(self, float_pv):
        assert isinstance(float_pv.write_access, bool)

    def test_host_property(self, float_pv):
        assert float_pv.host is None or isinstance(float_pv.host, str)

    def test_count_property(self, float_pv):
        assert float_pv.count is None or isinstance(float_pv.count, int)

    def test_nelm_property(self, float_pv):
        assert float_pv.nelm is None or isinstance(float_pv.nelm, int)

    def test_type_property(self, float_pv):
        assert float_pv.type is None or isinstance(float_pv.type, str)

    def test_typefull_property(self, float_pv):
        assert float_pv.typefull is None or isinstance(float_pv.typefull, str)

    def test_units_property(self, float_pv):
        assert float_pv.units is None or isinstance(float_pv.units, str)

    def test_precision_property(self, float_pv):
        assert float_pv.precision is None or isinstance(float_pv.precision, int)

    def test_timestamp_property(self, float_pv):
        assert float_pv.timestamp is None or isinstance(float_pv.timestamp, float)

    def test_posixseconds_property(self, float_pv):
        assert float_pv.posixseconds is None or isinstance(float_pv.posixseconds, (int, float))

    def test_nanoseconds_property(self, float_pv):
        assert float_pv.nanoseconds is None or isinstance(float_pv.nanoseconds, (int, float))

    def test_severity_property(self, float_pv):
        assert float_pv.severity is None or isinstance(float_pv.severity, int)

    def test_status_property(self, float_pv):
        assert float_pv.status is None or isinstance(float_pv.status, int)

    def test_char_severity_property(self, float_pv):
        assert float_pv.char_severity is None or isinstance(float_pv.char_severity, str)

    def test_char_status_property(self, float_pv):
        assert float_pv.char_status is None or isinstance(float_pv.char_status, str)

    def test_char_value_property(self, float_pv):
        assert float_pv.char_value is None or isinstance(float_pv.char_value, str)

    def test_alarm_limits(self, float_pv):
        for attr in (
            "lower_alarm_limit",
            "upper_alarm_limit",
            "lower_warning_limit",
            "upper_warning_limit",
            "lower_ctrl_limit",
            "upper_ctrl_limit",
            "lower_disp_limit",
            "upper_disp_limit",
        ):
            val = getattr(float_pv, attr)
            assert val is None or isinstance(val, (int, float))

    def test_enum_strs_property_none_for_float(self, float_pv):
        assert float_pv.enum_strs is None

    def test_add_and_remove_callback(self, float_pv):
        received: list[Any] = []
        idx = float_pv.add_callback(callback=lambda **kw: received.append(kw))
        float_pv.put(5.5)
        time.sleep(0.4)
        float_pv.remove_callback(index=idx)
        float_pv.put(pv_data["TEST:FLOAT"]["value"])
        assert len(received) > 0

    def test_run_callbacks(self, float_pv):
        received: list[Any] = []
        float_pv.add_callback(callback=lambda **kw: received.append(kw))
        float_pv.run_callbacks()
        float_pv.clear_callbacks()

    def test_run_callback_by_index(self, float_pv):
        received: list[Any] = []
        idx = float_pv.add_callback(callback=lambda **kw: received.append(kw))
        float_pv.run_callback(index=idx)
        assert len(received) >= 1
        float_pv.clear_callbacks()

    def test_clear_callbacks(self, float_pv):
        float_pv.add_callback(callback=lambda **kw: None)
        float_pv.clear_callbacks()

    def test_pv_monitor(self, float_pv):
        received: list[Any] = []
        mon = float_pv.monitor(callback=lambda **kw: received.append(kw))
        float_pv.put(33.3)
        time.sleep(0.4)
        if mon is not None:
            mon.close()
        float_pv.put(pv_data["TEST:FLOAT"]["value"])
        assert len(received) > 0


class TestExtraNTTypes:
    @pytest.fixture(scope="class")
    def ctx_nt(self, ioc_servers):
        from pvua import Context, Provider
        return Context(provider_get=Provider.PVA, provider_put=Provider.PVA, provider_monitor=Provider.PVA)

    @pytest.fixture(scope="class", autouse=True)
    def start_nt_server(self, ioc_servers):
        from p4p.server import Server as P4PServer
        from p4p.server.thread import SharedPV
        from p4p.nt import NTScalar, NTTable, NTEnum, NTNDArray, NTURI

        pvs: dict[str, SharedPV] = {}

        # NTScalar variants
        pvs["NT:SCALAR:F64"]  = SharedPV(initial=NTScalar("d").wrap(1.23))
        pvs["NT:SCALAR:I32"]  = SharedPV(initial=NTScalar("i").wrap(42))
        pvs["NT:SCALAR:STR"]  = SharedPV(initial=NTScalar("s").wrap("hello"))
        pvs["NT:SCALAR:BOOL"] = SharedPV(initial=NTScalar("?").wrap(True))

        # NTScalar arrays
        pvs["NT:ARRAY:F64"] = SharedPV(initial=NTScalar("ad").wrap(np.array([1.0, 2.0, 3.0])))
        pvs["NT:ARRAY:U8"] = SharedPV(initial=NTScalar("aB").wrap(np.array([0, 127, 255], dtype=np.uint8)))

        # NTTable
        table_type = NTTable(columns=[
            NTTable.Value("double", "x"),
            NTTable.Value("double", "y"),
        ])
        pvs["NT:TABLE"] = SharedPV(initial=table_type.wrap({"x": [1.0, 2.0, 3.0], "y": [4.0, 5.0, 6.0]}))

        # NTEnum
        pvs["NT:ENUM"] = SharedPV(initial=NTEnum.wrap({"index": 1, "choices": ["OFF", "ON", "HALFWAY_ON"]}))

        # NTNDArray (2x3)
        image = np.arange(6, dtype=np.uint8).reshape((2, 3))
        pvs["NT:NDARRAY"] = SharedPV(initial=NTNDArray().wrap(image))

        # NTURI
        pvs["NT:URI"] = SharedPV(initial=NTURI.buildType(("x",)).wrap("pva:///some/service", {"x": 1.0}))

        def run():
            with P4PServer(providers=[pvs]) as server:
                while True:
                    time.sleep(0.25)

        thread = threading.Thread(target=run, daemon=True, name="test-nt-server")
        thread.start()
        time.sleep(1)
        yield pvs


    """
    def test_ntscalar_float64(self, ctx_nt):
        val = ctx_nt.get("NT:SCALAR:F64")
        assert val == pytest.approx(1.23)

    def test_ntscalar_int32(self, ctx_nt):
        val = ctx_nt.get("NT:SCALAR:I32")
        assert int(val) == 42

    def test_ntscalar_string(self, ctx_nt):
        val = ctx_nt.get("NT:SCALAR:STR", as_string=True)
        assert val == "hello"

    def test_ntscalar_bool(self, ctx_nt):
        val = ctx_nt.get("NT:SCALAR:BOOL")
        assert bool(val) is True

    def test_ntscalar_put_float64(self, ctx_nt):
        ctx_nt.put("NT:SCALAR:F64", 9.99)
        time.sleep(0.2)
        val = ctx_nt.get("NT:SCALAR:F64")
        assert val == pytest.approx(9.99)

    def test_ntscalar_with_metadata(self, ctx_nt):
        result = ctx_nt.get_with_metadata("NT:SCALAR:F64")
        assert "value" in result

    def test_ntscalar_monitor(self, ctx_nt):
        received: list[Any] = []
        mon = ctx_nt.monitor("NT:SCALAR:F64", callback=lambda **kw: received.append(kw))
        ctx_nt.put("NT:SCALAR:F64", 5.55)
        time.sleep(0.5)
        mon.close()
        assert len(received) > 0

    def test_ntscalar_array_float64(self, ctx_nt):
        val = ctx_nt.get("NT:ARRAY:F64", as_numpy=True)
        assert isinstance(val, np.ndarray)
        np.testing.assert_allclose(val, [1.0, 2.0, 3.0])

    def test_ntscalar_array_uint8(self, ctx_nt):
        val = ctx_nt.get("NT:ARRAY:U8", as_numpy=True)
        assert isinstance(val, np.ndarray)
        assert val.dtype == np.uint8 or np.issubdtype(val.dtype, np.unsignedinteger)
        assert list(val) == [0, 127, 255]

    def test_ntscalar_array_count_limit(self, ctx_nt):
        val = ctx_nt.get("NT:ARRAY:F64", count=2, as_numpy=True)
        assert len(val) <= 3  # up to the count requested

    def test_ntscalar_array_put(self, ctx_nt):
        new_array = np.array([10.0, 20.0, 30.0])
        ctx_nt.put("NT:ARRAY:F64", new_array)
        time.sleep(0.3)
        val = ctx_nt.get("NT:ARRAY:F64", as_numpy=True)
        np.testing.assert_allclose(val, new_array)

    def test_ntscalar_array_monitor(self, ctx_nt):
        received: list[Any] = []
        mon = ctx_nt.monitor("NT:ARRAY:F64", callback=lambda **kw: received.append(kw))
        ctx_nt.put("NT:ARRAY:F64", np.array([7.0, 8.0, 9.0]))
        time.sleep(0.5)
        mon.close()
        assert len(received) > 0

    def test_nttable_get_returns_value(self, ctx_nt):
        val = ctx_nt.get_with_metadata("NT:TABLE")
        assert val is not None

    def test_nttable_monitor(self, ctx_nt):
        received: list[Any] = []
        mon = ctx_nt.monitor("NT:TABLE", callback=lambda **kw: received.append(kw))
        time.sleep(0.4)
        mon.close()
        assert len(received) >= 0

    def test_ntenum_get(self, ctx_nt):
        val = ctx_nt.get("NT:ENUM")
        assert isinstance(val, int)

    def test_ntenum_get_as_string(self, ctx_nt):
        val = ctx_nt.get("NT:ENUM", as_string=True)
        assert val is not None

    def test_ntenum_monitor(self, ctx_nt):
        received: list[Any] = []
        mon = ctx_nt.monitor("NT:ENUM", callback=lambda **kw: received.append(kw))
        time.sleep(0.3)
        mon.close()

    def test_ntndarray_get(self, ctx_nt):
        result = ctx_nt.get_with_metadata("NT:NDARRAY")
        assert result is not None

    def test_ntndarray_monitor(self, ctx_nt):
        received: list[Any] = []
        mon = ctx_nt.monitor("NT:NDARRAY", callback=lambda **kw: received.append(kw))
        time.sleep(0.4)
        mon.close()

    def test_nturi_get(self, ctx_nt):
        result = ctx_nt.get_with_metadata("NT:URI")
        assert isinstance(result, str)
    """


class TestConcurrency:
    def test_concurrent_gets(self, ctx_ca, ioc_servers):
        errors: list[Exception] = []

        def do_get():
            try:
                ctx_ca.get("TEST:FLOAT", timeout=5.0)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=do_get) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        assert errors == [], f"Errors in concurrent gets: {errors}"

    def test_concurrent_puts(self, ctx_ca, ioc_servers):
        errors: list[Exception] = []

        def do_put(val):
            try:
                ctx_ca.put("TEST:INT", val, timeout=5.0)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=do_put, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        assert errors == [], f"Errors in concurrent puts: {errors}"

    def test_multiple_monitors_same_pv(self, ctx_ca, ioc_servers):
        monitors = []
        counters: list[list[Any]] = [[] for _ in range(3)]
        for i in range(3):
            mon = ctx_ca.monitor(
                "TEST:FLOAT",
                callback=lambda i=i, **kw: counters[i].append(kw)
            )
            monitors.append(mon)
        ctx_ca.put("TEST:FLOAT", float(i + 1))
        time.sleep(0.5)
        for mon in monitors:
            mon.close()
        for i, bucket in enumerate(counters):
            assert len(bucket) > 0, f"Monitor {i} received no callbacks"


if __name__ == "__main__":
    threads = [start_ca_server(), start_pva_server()]
    print("Serving PVs:")
    for name, meta in pv_data.items():
        print(name + " = " + str(meta["value"]))

    print("\nType exit or press Ctrl+C to exit.")
    try:
        while True:
            time.sleep(0.25)
    except KeyboardInterrupt:
        pass
