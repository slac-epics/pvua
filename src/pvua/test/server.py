import asyncio
import threading
import time

from caproto.server import PVGroup, pvproperty, run as caproto_run
from caproto import ChannelType
from p4p.server import Server as P4PServer
from p4p.server.thread import SharedPV
from p4p.nt import NTScalar


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
}
pv_lock = threading.Lock()


# noinspection PyTypeChecker
def start_ca_server():
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

    def run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        ioc = SIOC(prefix="TEST:")
        caproto_run(ioc.pvdb, startup_hook=None, log_pv_names=True)

    thread = threading.Thread(target=run, daemon=True, name="pvua-test-ca")
    thread.start()
    return thread


def start_pva_server():
    pvs = {}

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

    pvs = {name: SharedPV(handler=PVHandler(name), initial=NTScalar(data["type"]).wrap(data["value"])) for name, data in pv_data.items()}

    def update_pvs(pvs):
        while True:
            with pv_lock:
                current = {k: v for k, v in pv_data.items()}
            for name, value in current.items():
                if name in pvs:
                    try:
                        new_value = pvs[name].current()
                        new_value["value"] = value["value"]
                        pvs[name].post(new_value)
                    except Exception as e:
                        print(f"[PVA] Error: {e}")
            time.sleep(0.25)

    def run():
        with P4PServer(providers=[pvs]) as server:
            update_thread = threading.Thread(target=update_pvs, args=(pvs,), daemon=True, name="pvua-test-pva-update")
            update_thread.start()
            try:
                while True:
                    time.sleep(0.25)
            finally:
                server.stop()

    thread = threading.Thread(target=run, daemon=True, name="pvua-test-pva")
    thread.start()
    return thread


def main():
    threads = [start_ca_server(), start_pva_server()]
    print("Serving PVs:")
    for name, meta in pv_data.items():
        print(f"{name} = {meta['value']}")

    print("\nType exit or press Ctrl+C to exit.")
    try:
        while True:
            time.sleep(0.25)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
