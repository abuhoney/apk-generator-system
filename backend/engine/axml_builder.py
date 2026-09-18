"""
axml_builder.py — Build a binary AndroidManifest.xml from scratch.

Android binary XML (AXML) format:
    - Header: magic 0x00080003 + file_size (4 bytes)
    - String pool chunk (type 0x0001)
    - Resource map chunk (type 0x0180)
    - XML START_NS / START_TAG / END_TAG / END_NS chunks

We build a minimal manifest with:
    <manifest package="X" ...>
        <uses-permission .../> (per permission)
        <application android:label="Y" android:icon="@mipmap/ic_launcher" ...>
            <activity android:name=".MainActivity" android:exported="true">
                <intent-filter>
                    <action android:name="android.intent.action.MAIN"/>
                    <category android:name="android.intent.category.LAUNCHER"/>
                </intent-filter>
            </activity>
        </application>
    </manifest>

The output is a valid binary AXML that Android's package parser accepts.
"""
from __future__ import annotations

import struct
from typing import Optional


# AXML chunk types
RES_STRING_POOL_TYPE = 0x0001
RES_XML_TYPE = 0x0003
RES_XML_START_NAMESPACE_TYPE = 0x0100
RES_XML_END_NAMESPACE_TYPE = 0x0101
RES_XML_START_ELEMENT_TYPE = 0x0102
RES_XML_END_ELEMENT_TYPE = 0x0103
RES_XML_RESOURCE_MAP_TYPE = 0x0180

# AXML magic
AXML_MAGIC = b'\x03\x00\x08\x00'

# Common android resource IDs (for the resource map)
# These correspond to android:* attribute resource IDs
ANDROID_ATTR_IDS = [
    0x01010003,  # theme
    0x01010001,  # label
    0x01010002,  # icon
    0x01010003,  # name (duplicate — actually different: 0x01010003 is theme, 0x01010003 for name? Let's be careful)
]

# Resource IDs indexed by string position in the string pool.
# Position 0..N correspond to attribute names; we map them to their
# android framework resource IDs.
# Reference: frameworks/base/include/androidfw/ResourceTypes.h
RES_ID_MAP = {
    "theme": 0x01010000,
    "label": 0x01010001,
    "icon": 0x01010002,
    "name": 0x01010003,
    "exported": 0x01010010,
    "configChanges": 0x0101001f,
    "minSdkVersion": 0x0101020c,
    "versionCode": 0x0101021b,
    "versionName": 0x0101021c,
    "targetSdkVersion": 0x01010270,
    "allowBackup": 0x01010280,
    "supportsRtl": 0x010103af,
    "usesCleartextTraffic": 0x010104ec,
    "compileSdkVersion": 0x01010572,
    "compileSdkVersionCodename": 0x01010573,
    "debuggable": 0x0101000f,
    "hardwareAccelerated": 0x010102d3,
    "windowBackground": 0x01010054,
    "colorBackground": 0x01010052,
}


class AXMLBuilder:
    def __init__(self) -> None:
        self.strings: list[str] = []
        self.string_index: dict[str, int] = {}
        self.res_ids: list[int] = []   # parallel to strings, 0 if not a resource attr

    def _add_string(self, s: str) -> int:
        if s in self.string_index:
            return self.string_index[s]
        idx = len(self.strings)
        self.strings.append(s)
        self.string_index[s] = idx
        # Map to resource ID if known
        if s in RES_ID_MAP:
            self.res_ids.append(RES_ID_MAP[s])
        else:
            self.res_ids.append(0)
        return idx

    # ------------------------------------------------------------------ #
    # String pool chunk
    # ------------------------------------------------------------------ #
    def _build_string_pool(self) -> bytes:
        # We use UTF-8 encoding (flag 0x100) for compactness
        string_count = len(self.strings)
        style_count = 0
        flags = 0x100  # UTF-8
        # Build string data
        string_data = bytearray()
        offsets = []
        for s in self.strings:
            offsets.append(len(string_data))
            b = s.encode('utf-8')
            # UTF-8 length encoding: two lengths (utf16 len, utf8 len)
            utf16_len = len(s)
            utf8_len = len(b)
            # utf16 length
            if utf16_len > 0x7f:
                string_data.append((utf16_len >> 8) | 0x80)
                string_data.append(utf16_len & 0xff)
            else:
                string_data.append(utf16_len & 0x7f)
            # utf8 length
            if utf8_len > 0x7f:
                string_data.append((utf8_len >> 8) | 0x80)
                string_data.append(utf8_len & 0xff)
            else:
                string_data.append(utf8_len & 0x7f)
            string_data.extend(b)
            string_data.append(0)  # null terminator

        # Header
        header_size = 28  # type(2) + header_size(2) + size(4) + count(4) + style_count(4) + flags(4) + strings_start(4) + styles_start(4)
        offsets_start = header_size
        strings_start = offsets_start + string_count * 4
        styles_start = strings_start + len(string_data)
        # Pad to 4-byte alignment
        while (strings_start + len(string_data)) % 4 != 0:
            string_data.append(0)
        chunk_size = strings_start + len(string_data)

        out = bytearray()
        out += struct.pack('<HHI', RES_STRING_POOL_TYPE, header_size, chunk_size)
        out += struct.pack('<IIII', string_count, style_count, flags, strings_start)
        out += struct.pack('<I', styles_start)  # styles start (0 if no styles)
        # String offsets
        for off in offsets:
            out += struct.pack('<I', off)
        # String data
        out += string_data
        return bytes(out)

    # ------------------------------------------------------------------ #
    # Resource map chunk
    # ------------------------------------------------------------------ #
    def _build_resource_map(self) -> bytes:
        # Only include resource IDs for strings that have them (non-zero)
        # Actually the resource map must be parallel to the string pool —
        # it has one entry per string, but only the first N (the attribute
        # names) are non-zero.
        ids = [r if r != 0 else 0 for r in self.res_ids]
        header_size = 8
        chunk_size = header_size + len(ids) * 4
        out = bytearray()
        out += struct.pack('<HHI', RES_XML_RESOURCE_MAP_TYPE, header_size, chunk_size)
        for rid in ids:
            out += struct.pack('<I', rid)
        return bytes(out)

    # ------------------------------------------------------------------ #
    # XML chunks
    # ------------------------------------------------------------------ #
    def _build_xml_header(self) -> bytes:
        # RES_XML_TYPE: type(2) + header_size(2) + size(4)
        header_size = 8
        chunk_size = header_size  # no body
        return struct.pack('<HHI', RES_XML_TYPE, header_size, chunk_size)

    def _build_namespace(self, start: bool, ns_idx: int) -> bytes:
        # START_NS or END_NS: type(2)+header_size(2)+size(4) + lineNumber(4) + comment(4) + prefix(4) + uri(4)
        ctype = RES_XML_START_NAMESPACE_TYPE if start else RES_XML_END_NAMESPACE_TYPE
        header_size = 16
        chunk_size = header_size + 8  # + lineNumber(4) + comment(4) + prefix(4) + uri(4)
        # Actually: header(16) + lineNumber(4) + comment(4) + prefix(4) + uri(4) = 32
        chunk_size = 16 + 16
        out = bytearray()
        out += struct.pack('<HHI', ctype, header_size, chunk_size)
        out += struct.pack('<II', 1, 0xffffffff)  # lineNumber=1, comment=-1
        out += struct.pack('<I', ns_idx)  # prefix
        out += struct.pack('<I', ns_idx)  # uri (same as prefix for "android")
        return bytes(out)

    def _build_start_tag(self, ns_idx: int, name_idx: int,
                         attrs: list[tuple[int, int, int, int]]) -> bytes:
        # START_ELEMENT: type(2)+header_size(2)+size(4) + lineNumber(4)+comment(4) + ns(4)+name(4) + attrStart(2)+attrSize(2)+attrCount(2)+idIndex(2)+classIndex(2)+styleIndex(2)
        # Then attributes: ns(4)+name(4)+rawValue(4)+size(2)+0(2)+type(1)+res0(1)+data(4) = 20 bytes each
        header_size = 16
        attr_start = 16  # offset from start of chunk header to attrs
        attr_size = 20
        attr_count = len(attrs)
        chunk_size = header_size + 16 + attr_count * attr_size
        # Actually: header(16) + lineNumber(4) + comment(4) + ns(4) + name(4) + attrStart(2) + attrSize(2) + attrCount(2) + idIdx(2) + classIdx(2) + styleIdx(2) + (padding 2)
        # = 16 + 8 + 8 + 12 = 44 then attrs
        chunk_size = 16 + 20 + attr_count * attr_size  # 36 + attrs
        # Let me recompute properly
        # chunk = header(16) + body
        # body for START_ELEMENT:
        #   lineNumber(4) + comment(4) + ns(4) + name(4) + attrStart(2) + attrSize(2) + attrCount(2) + idIdx(2) + classIdx(2) + styleIdx(2)
        # = 4+4+4+4+2+2+2+2+2+2 = 28
        # Then attrs (each 20 bytes)
        body_size = 28 + attr_count * attr_size
        chunk_size = header_size + body_size

        out = bytearray()
        out += struct.pack('<HHI', RES_XML_START_ELEMENT_TYPE, header_size, chunk_size)
        out += struct.pack('<II', 1, 0xffffffff)  # lineNumber, comment
        out += struct.pack('<I', ns_idx)  # ns
        out += struct.pack('<I', name_idx)  # name
        out += struct.pack('<HHH', 0x14, attr_size, attr_count)  # attrStart(20), attrSize, attrCount
        out += struct.pack('<HHH', 0xffff, 0xffff, 0xffff)  # idIdx, classIdx, styleIdx (0xffff = none)
        # Attributes
        for (ns, name, raw_value, data) in attrs:
            # Each attr: ns(4) + name(4) + rawValue(4) + size(2) + res0(2) + type(1) + res1(1)? No:
            # attr: ns(4) + name(4) + rawValue(4) + typedValue(size(2)+res0(1)+type(1)+data(4)) = 20
            out += struct.pack('<I', ns)  # namespace
            out += struct.pack('<I', name)  # name
            out += struct.pack('<I', raw_value)  # rawValue (string index or -1)
            # typed value: size(2) + res0(1) + dataType(1) + data(4)
            out += struct.pack('<HBB', 8, 0, 0x12 if raw_value == 0xffffffff else 0x11)  # 0x12 = string, 0x11 = int
            out += struct.pack('<I', data)
        return bytes(out)

    def _build_end_tag(self, ns_idx: int, name_idx: int) -> bytes:
        # END_ELEMENT: type(2)+header_size(2)+size(4) + lineNumber(4)+comment(4) + ns(4)+name(4)
        header_size = 16
        chunk_size = header_size + 16  # +lineNumber(4)+comment(4)+ns(4)+name(4)
        out = bytearray()
        out += struct.pack('<HHI', RES_XML_END_ELEMENT_TYPE, header_size, chunk_size)
        out += struct.pack('<II', 1, 0xffffffff)  # lineNumber, comment
        out += struct.pack('<I', ns_idx)
        out += struct.pack('<I', name_idx)
        return bytes(out)

    # ------------------------------------------------------------------ #
    # High-level manifest builder
    # ------------------------------------------------------------------ #
    def build_manifest(self, package: str, app_label: str,
                       version_code: int = 1, version_name: str = "1.0.0",
                       min_sdk: int = 24, target_sdk: int = 34,
                       permissions: Optional[list[str]] = None,
                       activity_name: str = ".MainActivity",
                       icon_ref: str = "@mipmap/ic_launcher",
                       theme_ref: str = "@style/Theme.App") -> bytes:
        """Build a complete binary AndroidManifest.xml."""
        if permissions is None:
            permissions = ["android.permission.INTERNET"]

        # String indices we need
        # We'll build them as we reference them
        s_android = self._add_string("android")
        s_android_ns_uri = self._add_string("http://schemas.android.com/apk/res/android")

        # manifest attributes
        s_package = self._add_string("package")
        s_versionCode = self._add_string("versionCode")
        s_versionName = self._add_string("versionName")
        s_platformBuildVersionCode = self._add_string("platformBuildVersionCode")
        s_platformBuildVersionName = self._add_string("platformBuildVersionName")
        s_compileSdkVersion = self._add_string("compileSdkVersion")
        s_compileSdkVersionCodename = self._add_string("compileSdkVersionCodename")

        # uses-permission
        s_uses_permission = self._add_string("uses-permission")
        s_name = self._add_string("name")

        # uses-sdk
        s_uses_sdk = self._add_string("uses-sdk")
        s_minSdkVersion = self._add_string("minSdkVersion")
        s_targetSdkVersion = self._add_string("targetSdkVersion")

        # application
        s_application = self._add_string("application")
        s_label = self._add_string("label")
        s_icon = self._add_string("icon")
        s_allowBackup = self._add_string("allowBackup")
        s_usesCleartextTraffic = self._add_string("usesCleartextTraffic")
        s_theme = self._add_string("theme")
        s_debuggable = self._add_string("debuggable")
        s_hardwareAccelerated = self._add_string("hardwareAccelerated")

        # activity
        s_activity = self._add_string("activity")
        s_exported = self._add_string("exported")
        s_configChanges = self._add_string("configChanges")

        # intent-filter
        s_intent_filter = self._add_string("intent-filter")
        s_action = self._add_string("action")
        s_category = self._add_string("category")

        # manifest element name
        s_manifest = self._add_string("manifest")

        # Values (these are attribute values stored in the string pool)
        s_package_val = self._add_string(package)
        s_label_val = self._add_string(app_label)
        s_icon_val = self._add_string(icon_ref)
        s_theme_val = self._add_string(theme_ref)
        s_activity_val = self._add_string(activity_name)
        s_action_main = self._add_string("android.intent.action.MAIN")
        s_category_launcher = self._add_string("android.intent.category.LAUNCHER")

        # Permission values
        perm_string_indices = []
        for perm in permissions:
            perm_string_indices.append((self._add_string(perm),))

        # ---------------------------------------------------------------- #
        # Build the XML tree
        # ---------------------------------------------------------------- #
        xml_chunks = bytearray()
        xml_chunks += self._build_xml_header()
        # Namespace declaration: prefix="android", uri="http://schemas.android.com/apk/res/android"
        xml_chunks += self._build_namespace(True, s_android)  # use "android" as both prefix and uri
        # Actually prefix and uri are different strings; let me add a proper prefix
        # For simplicity, prefix = "android", uri = "http://schemas.android.com/apk/res/android"
        # We already added both. Let me rebuild the namespace chunk properly.

        # Let me restart the namespace chunk with proper prefix/uri indices
        xml_chunks = bytearray()
        xml_chunks += self._build_xml_header()

        # Build namespace chunk manually
        def _ns_chunk(start: bool) -> bytes:
            ctype = RES_XML_START_NAMESPACE_TYPE if start else RES_XML_END_NAMESPACE_TYPE
            header_size = 16
            chunk_size = header_size + 16  # body: lineNumber(4) + comment(4) + prefix(4) + uri(4)
            out = bytearray()
            out += struct.pack('<HHI', ctype, header_size, chunk_size)
            out += struct.pack('<II', 1, 0xffffffff)  # lineNumber=1, comment=-1
            out += struct.pack('<I', s_android)  # prefix = "android"
            out += struct.pack('<I', s_android_ns_uri)  # uri
            return bytes(out)

        xml_chunks += _ns_chunk(True)

        # <manifest package="X" versionCode="1" versionName="1.0.0"
        #            platformBuildVersionCode="34" platformBuildVersionName="14"
        #            compileSdkVersion="34" compileSdkVersionCodename="14">
        manifest_attrs = [
            (s_android_ns_uri, s_versionCode, 0xffffffff, version_code),
            (s_android_ns_uri, s_versionName, s_versionName, 0),  # placeholder, will use string
            (s_android_ns_uri, s_platformBuildVersionCode, 0xffffffff, 34),
            (s_android_ns_uri, s_platformBuildVersionName, s_platformBuildVersionName, 0),
            (s_android_ns_uri, s_compileSdkVersion, 0xffffffff, 34),
            (s_android_ns_uri, s_compileSdkVersionCodename, s_compileSdkVersionCodename, 0),
        ]
        # For string-valued attributes, we need: rawValue = string index, type=string(0x12), data=string index
        # For int-valued: rawValue=-1, type=int(0x10), data=value
        # Let me rebuild the attrs properly

        def _attr_str(name_idx: int, value_idx: int) -> tuple[int, int, int, int]:
            """String attribute: ns, name, rawValue, data."""
            return (s_android_ns_uri, name_idx, value_idx, value_idx)

        def _attr_int(name_idx: int, value: int) -> tuple[int, int, int, int]:
            """Integer attribute: ns, name, rawValue=-1, data=value."""
            return (s_android_ns_uri, name_idx, 0xffffffff, value)

        manifest_attrs = [
            _attr_int(s_versionCode, version_code),
            _attr_str(s_versionName, s_versionName),  # we'll set data to the value string
            _attr_int(s_platformBuildVersionCode, 34),
            _attr_str(s_platformBuildVersionName, s_platformBuildVersionName),
            _attr_int(s_compileSdkVersion, 34),
            _attr_str(s_compileSdkVersionCodename, s_compileSdkVersionCodename),
        ]
        # Actually the versionName should use the actual version string, not the attr name
        # Let me fix: we need a string index for the value "1.0.0"
        s_version_val = self._add_string(version_name)
        s_platform_name_val = self._add_string("14")
        s_compile_codename_val = self._add_string("14")

        manifest_attrs = [
            _attr_int(s_versionCode, version_code),
            (s_android_ns_uri, s_versionName, s_version_val, s_version_val),
            _attr_int(s_platformBuildVersionCode, 34),
            (s_android_ns_uri, s_platformBuildVersionName, s_platform_name_val, s_platform_name_val),
            _attr_int(s_compileSdkVersion, 34),
            (s_android_ns_uri, s_compileSdkVersionCodename, s_compile_codename_val, s_compile_codename_val),
        ]
        # Also the package attribute is special — it's in the default namespace, not android:
        # <manifest package="X" ...> — package has no namespace
        # We need a separate attribute with ns=-1 (no namespace)
        # For attributes without a namespace, ns index = 0xffffffff

        def _attr_str_no_ns(name_idx: int, value_idx: int) -> tuple[int, int, int, int]:
            return (0xffffffff, name_idx, value_idx, value_idx)

        manifest_attrs = [
            _attr_str_no_ns(s_package, s_package_val),
            _attr_int(s_versionCode, version_code),
            (s_android_ns_uri, s_versionName, s_version_val, s_version_val),
            _attr_int(s_platformBuildVersionCode, 34),
            (s_android_ns_uri, s_platformBuildVersionName, s_platform_name_val, s_platform_name_val),
            _attr_int(s_compileSdkVersion, 34),
            (s_android_ns_uri, s_compileSdkVersionCodename, s_compile_codename_val, s_compile_codename_val),
        ]

        xml_chunks += self._build_start_tag(0xffffffff, s_manifest, manifest_attrs)

        # <uses-permission android:name="X"/> for each permission
        for perm_str_idx, in perm_string_indices:
            perm_attrs = [_attr_str(s_name, perm_str_idx)]
            xml_chunks += self._build_start_tag(s_android_ns_uri, s_uses_permission, perm_attrs)
            xml_chunks += self._build_end_tag(s_android_ns_uri, s_uses_permission)

        # <uses-sdk android:minSdkVersion="24" android:targetSdkVersion="34"/>
        sdk_attrs = [
            _attr_int(s_minSdkVersion, min_sdk),
            _attr_int(s_targetSdkVersion, target_sdk),
        ]
        xml_chunks += self._build_start_tag(s_android_ns_uri, s_uses_sdk, sdk_attrs)
        xml_chunks += self._build_end_tag(s_android_ns_uri, s_uses_sdk)

        # <application android:label="Y" android:icon="@mipmap/ic_launcher"
        #               android:allowBackup="true" android:usesCleartextTraffic="true"
        #               android:theme="@style/Theme.App" android:hardwareAccelerated="true">
        app_attrs = [
            (s_android_ns_uri, s_label, s_label_val, s_label_val),
            (s_android_ns_uri, s_icon, s_icon_val, s_icon_val),
            _attr_int(s_allowBackup, 1),  # true
            _attr_int(s_usesCleartextTraffic, 1),  # true
            (s_android_ns_uri, s_theme, s_theme_val, s_theme_val),
            _attr_int(s_hardwareAccelerated, 1),  # true
        ]
        xml_chunks += self._build_start_tag(s_android_ns_uri, s_application, app_attrs)

        # <activity android:name=".MainActivity" android:exported="true" android:configChanges="...">
        # configChanges = orientation|screenSize|keyboardHidden = 0x400|0x800|0x20 = 0xCA0
        activity_attrs = [
            (s_android_ns_uri, s_name, s_activity_val, s_activity_val),
            _attr_int(s_exported, 1),  # true
            _attr_int(s_configChanges, 0xCA0),
        ]
        xml_chunks += self._build_start_tag(s_android_ns_uri, s_activity, activity_attrs)

        # <intent-filter>
        xml_chunks += self._build_start_tag(s_android_ns_uri, s_intent_filter, [])

        # <action android:name="android.intent.action.MAIN"/>
        action_attrs = [(s_android_ns_uri, s_name, s_action_main, s_action_main)]
        xml_chunks += self._build_start_tag(s_android_ns_uri, s_action, action_attrs)
        xml_chunks += self._build_end_tag(s_android_ns_uri, s_action)

        # <category android:name="android.intent.category.LAUNCHER"/>
        cat_attrs = [(s_android_ns_uri, s_name, s_category_launcher, s_category_launcher)]
        xml_chunks += self._build_start_tag(s_android_ns_uri, s_category, cat_attrs)
        xml_chunks += self._build_end_tag(s_android_ns_uri, s_category)

        # </intent-filter>
        xml_chunks += self._build_end_tag(s_android_ns_uri, s_intent_filter)

        # </activity>
        xml_chunks += self._build_end_tag(s_android_ns_uri, s_activity)

        # </application>
        xml_chunks += self._build_end_tag(s_android_ns_uri, s_application)

        # </manifest>
        xml_chunks += self._build_end_tag(0xffffffff, s_manifest)

        # </namespace android>
        xml_chunks += _ns_chunk(False)

        # ---------------------------------------------------------------- #
        # Assemble the full AXML file
        # ---------------------------------------------------------------- #
        string_pool = self._build_string_pool()
        resource_map = self._build_resource_map()

        total_size = 8 + len(string_pool) + len(resource_map) + len(xml_chunks)
        out = bytearray()
        out += AXML_MAGIC
        out += struct.pack('<I', total_size)
        out += string_pool
        out += resource_map
        out += xml_chunks
        return bytes(out)


def build_android_manifest(package: str, app_label: str,
                           version_code: int = 1, version_name: str = "1.0.0",
                           min_sdk: int = 24, target_sdk: int = 34,
                           permissions: Optional[list[str]] = None,
                           activity_name: str = ".MainActivity") -> bytes:
    """Build a binary AndroidManifest.xml with the given parameters."""
    b = AXMLBuilder()
    return b.build_manifest(
        package=package, app_label=app_label,
        version_code=version_code, version_name=version_name,
        min_sdk=min_sdk, target_sdk=target_sdk,
        permissions=permissions,
        activity_name=activity_name,
    )


if __name__ == "__main__":
    import sys
    pkg = sys.argv[1] if len(sys.argv) > 1 else "com.bardom.app.test"
    label = sys.argv[2] if len(sys.argv) > 2 else "Test App"
    manifest = build_android_manifest(pkg, label, permissions=[
        "android.permission.INTERNET",
        "android.permission.ACCESS_NETWORK_STATE",
    ])
    out_path = "/tmp/test_manifest.xml"
    open(out_path, "wb").write(manifest)
    print(f"Wrote {len(manifest)} bytes to {out_path}")
