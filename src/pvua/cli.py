from pvua import Context, Provider


def cli(args: list[str]) -> int:
    if len(args) < 3:
        print("Usage: <get/get_timevars/info/put> <ca/pva/unknown> <PV name> <value (if put specified)>")
        return 1

    ctx = Context()

    control_values = [s.strip() for s in args]
    match control_values[0].lower():
        case "get" if len(control_values) > 2:
            match control_values[1].lower():
                case "pva":
                    print(f"{ctx.get(control_values[2], provider_override=Provider.PVA)}")
                case "ca":
                    print(f"{ctx.get(control_values[2], provider_override=Provider.CA)}")
                case "unknown":
                    print(f"{ctx.get(control_values[2], provider_override=Provider.UNKNOWN)}")
                case _:
                    print(f"Unknown argument at position 1: {control_values[1]}")
                    return 1
        case "get_timevars" if len(control_values) > 2:
            match control_values[1].lower():
                case "pva":
                    print(f"{ctx.get_timevars(control_values[2], provider_override=Provider.PVA)}")
                case "ca":
                    print(f"{ctx.get_timevars(control_values[2], provider_override=Provider.CA)}")
                case "unknown":
                    print(f"{ctx.get_timevars(control_values[2], provider_override=Provider.UNKNOWN)}")
                case _:
                    print(f"Unknown argument at position 1: {control_values[1]}")
                    return 1
        case "info" if len(control_values) > 1:
            match control_values[1].lower():
                case "pva" | "unknown":
                    print("Info command unimplemented for PVA.")
                case "ca":
                    print(f"{ctx.info_ca(control_values[1])}")
                case _:
                    print(f"Unknown argument at position 1: {control_values[1]}")
                    return 1
        case "put" if len(control_values) > 3:
            match control_values[1].lower():
                case "pva":
                    print(f"{ctx.put(control_values[2], control_values[3], provider_override=Provider.PVA)}")
                case "ca":
                    print(f"{ctx.put(control_values[2], control_values[3], provider_override=Provider.CA)}")
                case "unknown":
                    print(f"{ctx.put(control_values[2], control_values[3], provider_override=Provider.UNKNOWN)}")
                case _:
                    print(f"Unknown argument at position 1: {control_values[1]}")
                    return 1
        case _:
            print(f"Unknown argument at position 0: {control_values[0]}")
            return 1

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(cli(sys.argv[1:]))
