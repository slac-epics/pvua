# PV Unified Access

A light wrapper around p4p and pyepics.

### CLI

When the package is installed, new commands will be added that call into it.

- `pvuaget <PV name> [ca/pva]`
- `pvuainfo <PV name> [ca/pva]`
  - Currently only Channel Access is supported for the info command.
- `pvuaput <PV name> <PV value> [ca/pva]`

If no provider is specified, both CA and PVA will be tried, with PVA tried first.

The following command will run the "universal" interface that the installed commands hook into:

```
python -m pvua.cli <get/info/put> <ca/pva/unknown> <PV name> <value (if put specified)>
```

### Testing

The following command will start a test IOC that serves three commands, which the CLI and library
can interact with.

The test dependency of `caproto` must be installed, installing the `test` optional dependencies
can be done with `pip install pvua[test]`.

```
python -m pvua.test.server
```
