# Bundled runtime dependencies

`openvr/__init__.py`, `openvr/version.py`, and `openvr/error_code/__init__.py`
are unmodified pyopenvr 2.12.1401 files copied from the user's installed package.
Source: https://github.com/cmbruns/pyopenvr. License: PYOPENVR-LICENSE.txt.

`openvr/libopenvr_api_64.so` is Valve's Linux ARM64 library, renamed from
`bin/linuxarm64/libopenvr_api.so` for pyopenvr's loader. It is not the x86_64
library bundled by PyPI. Source commit:
https://github.com/ValveSoftware/openvr/commit/0924064316de3effbcd1acf1e309182a2deb1c05

SHA256: cc3671d24dd23fb61494e8a8327cf4fe7f638a60508ff7225984a03f2f5947e9

License: OPENVR-LICENSE.txt. This binary requires physical Frame validation.
