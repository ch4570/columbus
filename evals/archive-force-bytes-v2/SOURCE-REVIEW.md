# Pre-trial force_bytes semantics

Review scope is the 37 lexical owners and 46 direct sites in oracle.json, covering all 883 Python files under django/. Imported names refer to django.utils.encoding.force_bytes. No matching receiver calls are present; OracleParam.self.force_bytes is an attribute storing a value, not the imported callable. Nested to_bytes functions are separate lexical owners; their outer functions must not replace them in the caller set.

Common argument rule: a one-argument call uses encoding='utf-8', strings_only=False and errors='strict'. DEFAULT_CHARSET, cursor.charset and a parsed content-type charset are explicit alternatives, not necessarily UTF-8. Unspecified errors remains strict. smart_bytes forwards all three options. These common rules may be stated once and applied unambiguously to individual findings rather than repeated 37 times.

The target returns existing bytes unchanged when encoding is utf-8, otherwise decodes those bytes as UTF-8 before encoding to the requested encoding using errors. With strings_only=True it preserves protected types; memoryviews become bytes; other values use str(s).encode(). It resolves lazy values, unlike smart_bytes's Promise bypass. Do not claim every call necessarily allocates, every input is already text, every result must be bytes despite strings_only, or strict encoding errors are swallowed. Full enumeration of protected Python types is not required.

Each entry below requires accurate conversion input, purpose, options and relevant direct-call guards/exception paths. Unrelated surrounding behavior need not be catalogued. Quotes can substantiate omitted details but cannot repair contradictory prose. The automatic citation gate accepts one bounded direct-call citation per owner; owners with multiple distant sites must explain all their conversions, without requiring a single quote spanning more than the gate's 40-line bound. Same-line calls remain distinct sites.

## Authentication and GDAL

- PasswordResetForm.save: inside get_users(email), converts the primary key's value_to_string(user), then URL-safe base64 encodes it into the email context uid. Defaults apply. Extra email context is merged last and can override uid, but does not bypass the already executed conversion. No yielded users means no conversion. Domain selection does not change encoding.
- DataSource.__init__: only str/Path input is converted for capi.open_ds with vector/read-write flags. self.encoding does not replace force_bytes's default encoding. The open try catches GDALException and supplies a clearer error; valid datasource/driver pointer input bypasses conversion, invalid input raises. Do not describe it as catching UnicodeError.
- DataSource.__getitem__: string indices are converted for named layer lookup; GDALException becomes IndexError. Integer lookup bypasses conversion, with range checks; other types raise TypeError. Successful lookup wraps Layer.
- Driver.__init__: string input selects a case-insensitive alias when present, otherwise the original name, and converts it for driver lookup. Integer/pointer input bypasses conversion; unrecognized type or invalid driver pointer raises GDALException.
- Feature.index: converts field_name for get_field_index, then raises IndexError for a negative index; otherwise returns it.
- OGRGeometry.from_json: converts the JSON input, passes it to _from_json and wraps the result as OGRGeometry.
- OGRGeometry.from_gml: converts gml_string for capi.from_gml and constructs cls from the result.
- Layer.test_capability: converts the capability string for the native check and returns bool of its result.

## Raster

All calls here use default conversion options, including filenames; these are not explicit driver-specific encodings.

- GDALRaster.__init__: acts on preprocessed ds_input. A string is converted for open_ds, after rejecting a nonexistent non-VSI path; the GDALException is re-raised with path/error context. A bytes buffer sets write mode, retains a ctypes buffer and creates a random VSI name: that name is converted once for create_vsi_file_from_mem_buffer, again for open_ds, and on GDALException again for unlink_vsi_file before raising a creation error. The failure-only unlink conversion must not be described as always executed. Dictionary input converts name (default empty string) for create_ds, after driver/name, size and srid validation; subsequent band/SRS/property initialization is downstream, not extra direct conversions. Pointer input bypasses conversion, other invalid types raise. All five direct sites must be accounted for.
- GDALRaster.__del__: converts self.name for unlink only when is_vsi_based, then invokes superclass destruction. No local catch surrounds the conversion.
- GDALRaster.vsi_buffer: returns None unless both VSI-based and under the memory VSI prefix. Otherwise converts name for get_mem_buffer_from_vsi_file and returns string_at using its output length. Do not infer the delete-on-read flag's truth value from its name alone.
- GDALRaster.clone: chooses a truthy supplied name, otherwise original name plus '_copy.' and driver for non-MEM, otherwise a generated memory VSI path. Converts that chosen name for copy_ds and wraps the copied pointer in GDALRaster with existing write state.

## Spatial reference and GEOS

- SpatialReference.attr_value: requires target str and index int, else TypeError; converts target for get_attr_value.
- SpatialReference.auth_name: passes None directly; only non-None target is converted for get_auth_name.
- SpatialReference.auth_code: same None bypass for get_auth_code.
- SpatialReference.import_user_input: converts user_input for capi.from_user_input.
- SpatialReference.import_wkt: converts wkt, wraps in c_char_p/byref, and imports through capi.from_wkt.
- SpatialReference.xml: converts dialect (default empty string) for capi.to_xml alongside the output pointer.
- GEOSGeometryBase.from_ewkt: converts the whole EWKT before byte splitting on the first semicolon. Parses an optional SRID prefix, rejects an invalid prefix or empty WKT, and constructs GEOSGeometry from parsed WKT with the SRID.
- GEOSGeometryBase.relate_pattern: rejects non-str or length greater than 9, then converts pattern for native DE-9IM relation checking. Do not invent an exact-nine-character validation.
- GEOSGeometry.__init__: bytes are first force_str-converted. In the string branch, WKT match converts only extracted WKT for _from_wkt; hex match converts the complete input for the WKB reader. GeoJSON follows GDAL and contains no additional direct force_bytes call in this owner. Pointer, memoryview and geometry clone alternatives bypass these two sites; invalid strings/types raise, invalid geometry pointer and conflicting SRID can also reject downstream. Both parser branches forward max_geom_collections. No blanket catch absorbs conversion errors.
- _WKTReader.read: accepts only bytes/str, applies the geometry-collection limit before converting WKT for wkt_reader_read. Invalid type and limit rejection precede the call.

## Mail, signing and database

- EmailMessage._create_mime_attachment: only message/rfc822 content that is neither Django EmailMessage nor email.message.Message is force_bytes-converted and parsed by message_from_bytes. Django EmailMessage uses content.message(), existing Message is retained. This message branch uses SafeMIMEMessage and must not be confused with the non-text base64 branch or text charset setting.
- _cookie_signer_key: converts key with defaults and prepends the fixed b'django.http.cookies' namespace.
- OracleParam.__init__: datetime and unsupported-Boolean preprocessing occur first. bind_parameter and bytes/timedelta branches bypass the direct conversion. Otherwise force_str(param,cursor.charset,strings_only) is stored in self.force_bytes; only if that stored result is str does len(force_bytes(param,cursor.charset,strings_only)) compute byte size. errors defaults to strict. An input_size attribute takes priority; otherwise size over 4000 selects CLOB, with timestamp/Boolean/None alternatives. Do not say the direct force_bytes result is the value stored for binding, or count self.force_bytes as a method call.
- DatabaseOperations.convert_binaryfield_value: only Database.LOB is read and its result converted; other values return unchanged.

## Test requests and utility functions

- FakePayload.write: rejects writes after reading started before conversion. Converts b with defaults, writes the result to the internal buffer and increments length by its byte length.
- encode_multipart.to_bytes: nested helper converts its s using settings.DEFAULT_CHARSET, default strings_only/errors. The outer function uses it for multipart boundaries, field headers and non-file values/items, then joins lines with CRLF. File parts use encode_file; an outer None value is rejected before its field conversion. The outer function is not itself a direct force_bytes caller.
- encode_file.to_bytes: separate nested helper, same explicit charset/default options, used for boundaries, content headers and file.read() data. Filename/content-type selection precedes those calls; it returns multipart lines. Do not merge this owner with encode_multipart.to_bytes.
- RequestFactory._encode_data: multipart identity branch delegates to encode_multipart and bypasses its own force_bytes site. Otherwise a content-type regex match supplies charset, with DEFAULT_CHARSET fallback; converts data with encoding=charset.
- RequestFactory.generic: converts data unconditionally after path parsing, using DEFAULT_CHARSET; only truthy converted data adds CONTENT_LENGTH, CONTENT_TYPE and FakePayload to the WSGI request fields. Later extra fields can override request entries. Query-string selection is unrelated to this conversion and need not be fully described.
- AsyncRequestFactory.generic: same unconditional data conversion and charset; truthy data appends length/type headers and creates _body_file as FakePayload. Subsequent request assembly uses these fields. Other query/header processing is not another direct force_bytes site.
- salted_hmac: defaults secret only when None, converts key_salt and secret before the algorithm lookup, hashes their concatenation for a derived key, and converts value for hmac.new. All three calls use defaults. Invalid algorithm lookup raises InvalidAlgorithm before value conversion; it does not catch earlier conversion errors.
- constant_time_compare: converts both values on the same line with defaults and passes them to secrets.compare_digest. Preserve two direct sites in one owner.
- pbkdf2: defaults digest to sha256 when None, normalizes falsey dklen to None, converts password and salt with defaults, and passes them to hashlib.pbkdf2_hmac with digest().name, iterations and dklen.
- smart_bytes: returns Promise unchanged and bypasses force_bytes; otherwise forwards s, encoding, strings_only and errors, with its own defaults matching the target.
- uri_to_iri: None returns before conversion. Otherwise converts with defaults, selectively unquotes byte sequences and re-percent-encodes broken Unicode before final decoding. Do not describe it as decoding every percent escape or using errors='ignore'.

These are source-level criteria, not runtime execution evidence. No target builds, GDAL libraries, database connections or mail sending are needed for this review. No model trial has started.
