from datetime import datetime
import sys
import time

from .context import Context, Provider


def str_to_provider(provider: str) -> Provider:
    match provider.lower():
        case "pva":
            return Provider.PVA
        case "ca":
            return Provider.CA
        case _:
            return Provider.UNKNOWN


def cli_universal(command: str, provider: Provider, pvname: str, pv_value: str | None = None) -> int:
    ctx = Context()

    match command:
        case "get":
            timevars = ctx.get_timevars(pvname, provider_override=provider)
            ms, ns = divmod((int(timevars['posixseconds'] * 1_000_000_000) + timevars['nanoseconds']) // 1_000_000, 1_000)
            print(f"{pvname}\t{ctx.get(pvname, provider_override=provider)}\t{datetime.fromtimestamp(ms).strftime(f"%Y:%m:%d %H:%M:%S.{ns:03d}")}")
        case "info":
            if provider == Provider.PVA:
                print("Info command unimplemented for PVA.")
                return 1
            else:
                print(f"{ctx.info_ca(pvname)}")
        case "put":
            ctx.put(pvname, pv_value, provider_override=provider)
        case "monitor":
            ctx.monitor(pvname, callback=lambda **kwargs: print(kwargs["pvname"] + " " + str(kwargs["value"])), provider_override=provider)
            try:
                while True:
                    time.sleep(0.25)
            except KeyboardInterrupt:
                pass
        case _:
            print(f"Unknown command: {command}")
            return 1
    return 0


def cli_get_entrypoint() -> int:
    if len(sys.argv) < 2:
        print("Usage: <PV name> [ca/pva]")
        return 1
    return cli_universal("get", str_to_provider(sys.argv[2].strip()) if len(sys.argv) > 2 else Provider.UNKNOWN, sys.argv[1].strip())


def cli_info_entrypoint() -> int:
    if len(sys.argv) < 2:
        print("Usage: <PV name> [ca/pva]")
        return 1
    return cli_universal("info", str_to_provider(sys.argv[2].strip()) if len(sys.argv) > 2 else Provider.UNKNOWN, sys.argv[1].strip())


def cli_put_entrypoint() -> int:
    if len(sys.argv) < 3:
        print("Usage: <PV name> <PV value> [ca/pva]")
        return 1
    return cli_universal("put", str_to_provider(sys.argv[3].strip()) if len(sys.argv) > 3 else Provider.UNKNOWN, sys.argv[1].strip(), sys.argv[2].strip())


def cli_monitor_entrypoint() -> int:
    if len(sys.argv) < 2:
        print("Usage: <PV name> [ca/pva]")
        return 1
    return cli_universal("monitor", str_to_provider(sys.argv[2].strip()) if len(sys.argv) > 2 else Provider.UNKNOWN, sys.argv[1].strip())


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: <get/info/put/monitor> <ca/pva/unknown> <PV name> <value (if put specified)>")
        sys.exit(1)

    sys.exit(cli_universal(sys.argv[1].strip(), str_to_provider(sys.argv[2].strip()), sys.argv[3].strip(), sys.argv[4].strip() if len(sys.argv) > 4 else None))
