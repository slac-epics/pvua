import asyncio
import sys
import threading
import time

from caproto.server import PVGroup, pvproperty, run as caproto_run
from caproto import ChannelType
from p4p.server import Server as P4PServer
from p4p.server.thread import SharedPV
from p4p.nt import NTScalar
from pvua import Context, Provider


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
        def __init__(self, pv_name: str):
            self.pv_name = pv_name

        def put(self, pv: SharedPV, op):
            value = op.value()
            with pv_lock:
                pv_data[self.pv_name]["value"] = value["value"]
            new_value = pvs[self.pv_name].current()
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
    threads = []
    if len(sys.argv) > 1:
        for arg in sys.argv[1:]:
            if arg.lower() == "--test-server":
                threads = [start_ca_server(), start_pva_server()]
                print("Serving PVs:")
                for name, meta in pv_data.items():
                    print(f"{name} = {meta['value']}")
                break

    print("\nSupported commands:")
    print("caget <name>")
    print("cainfo <name>")
    print("caput <name> <value>")
    print("pvget <name>")
    print("pvput <name> <value>")
    print("get <CA/PVA/UNK> <name>")
    print("get_timevars <CA/PVA/UNK> <name>")
    print("put <CA/PVA/UNK> <name> <value>")
    print("\nType exit or press Ctrl+C to exit.\n")

    ctx = Context()

    try:
        while True:
            control_values = [s.strip() for s in input("> ").split(' ')]
            if control_values[0].lower() == "caget":
                control_values[0] = "get"
                control_values.insert(1, "ca")
            elif control_values[0].lower() == "caput":
                control_values[0] = "put"
                control_values.insert(1, "ca")
            elif control_values[0].lower() == "pvget":
                control_values[0] = "get"
                control_values.insert(1, "pva")
            elif control_values[0].lower() == "pvput":
                control_values[0] = "put"
                control_values.insert(1, "pva")

            match control_values[0].lower():
                case "exit":
                    break
                case "cainfo" if len(control_values) > 1:
                    print(f"{ctx.info_ca(control_values[1])}")
                case "get" if len(control_values) > 2:
                    match control_values[1].lower():
                        case "pva":
                            print(f"{ctx.get(control_values[2], provider_override=Provider.PVA)}")
                        case "ca":
                            print(f"{ctx.get(control_values[2], provider_override=Provider.CA)}")
                        case "unk":
                            print(f"{ctx.get(control_values[2], provider_override=Provider.UNKNOWN)}")
                        case _:
                            print("Unknown argument at position 1")
                case "get_timevars" if len(control_values) > 2:
                    match control_values[1].lower():
                        case "pva":
                            print(f"{ctx.get_timevars(control_values[2], provider_override=Provider.PVA)}")
                        case "ca":
                            print(f"{ctx.get_timevars(control_values[2], provider_override=Provider.CA)}")
                        case "unk":
                            print(f"{ctx.get_timevars(control_values[2], provider_override=Provider.UNKNOWN)}")
                        case "_":
                            print("Unknown argument at position 1")
                case "put" if len(control_values) > 3:
                    match control_values[1].lower():
                        case "pva":
                            print(f"{ctx.put(control_values[2], control_values[3], provider_override=Provider.PVA)}")
                        case "ca":
                            print(f"{ctx.put(control_values[2], control_values[3], provider_override=Provider.CA)}")
                        case "unk":
                            print(f"{ctx.put(control_values[2], control_values[3], provider_override=Provider.UNKNOWN)}")
                        case _:
                            print("Unknown argument at position 1")
                case _:
                    print("Unknown argument at position 0")

    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
