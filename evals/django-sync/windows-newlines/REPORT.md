# Windows probe-byte fixture correction

Portable distribution run 34162331719 at 9386530 failed the new probe accounting assertion on Windows: 44 actual bytes versus 42 expected. The fixture used write_text, which translates its LF newline to CRLF on Windows, but calculated its expected read volume from LF-only byte literals. The implementation correctly counts the bytes read.

The regression now writes exact byte payloads and exercises both LF and CRLF in separate subtests on every platform. Each case checks zero warm source hashing and parsing, four probes across the two passes, and exactly twice the text-plus-binary payload lengths. This preserves the exact accounting assertion instead of loosening its tolerance. Local sync suites pass 21 tests with both pinned and candidate Java dependencies. Full Windows CI must still validate the corrected fixture; local results are not a Windows pass.

The earlier candidate run 34162363469 was still executing its Windows jobs when the failure was diagnosed. Its source is unchanged and retains the incorrect test expectation. A new run for the corrected commit is justified by this code change, not by an observation timeout.
