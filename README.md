# PV Unified Access

A light wrapper around p4p and pyepics.

### CLI

The following command to perform operations that can be done in code.

```
python -m pvua.cli <get/get_timevars/info/put> <ca/pva/unknown> <PV name> <value (if put specified)>
```

### Testing

The following command will start a test IOC that serves three commands, which the CLI and library
can interact with.

The test dependency of `caproto` must be installed, installing the `test` optional dependencies
can be done with `pip install pvua[test]`.

```
python -m pvua.test.server
```
