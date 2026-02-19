import sys

from .context import Context, Provider


def str_to_provider(provider: str) -> Provider:
    match provider.lower():
        case "pva":
            return Provider.PVA
        case "ca":
            return Provider.CA
        case _:
            return Provider.UNKNOWN


def cli_universal(command: str, provider: Provider, pv_name: str, pv_value: str | None = None) -> int:
    ctx = Context()

    match command:
        case "get":
            print(f"{ctx.get(pv_name, provider_override=provider)}")
            print(f"Time: {ctx.get_timevars(pv_name, provider_override=provider)}")
        case "info":
            if provider == Provider.PVA:
                print("Info command unimplemented for PVA.")
                return 1
            else:
                print(f"{ctx.info_ca(pv_name)}")
        case "put":
            ctx.put(pv_name, pv_value, provider_override=provider)
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


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: <get/info/put> <ca/pva/unknown> <PV name> <value (if put specified)>")
        sys.exit(1)

    sys.exit(cli_universal(sys.argv[1].strip(), str_to_provider(sys.argv[2].strip()), sys.argv[3].strip(), sys.argv[4].strip() if len(sys.argv) > 4 else None))
