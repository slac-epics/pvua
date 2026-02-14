# PV Unified Access

A light wrapper around p4p and pyepics.

### Testing

Run the following command to show a CLI wrapping methods on the `Context` class.

If `--test-server` is provided, test PVs served over both CA and PVA will be created.
The test dependency of `caproto` must be installed, installing the `test` optional dependencies
can be done with `pip install pvua[test]`.

```shell
python -m pvua.test.server [--test-server]
```
