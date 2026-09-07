# Installed caller options

The clean-distribution verifier now checks caller path filtering before counting, expanded lexical source ranges, zero context and rejection of context above 40. These checks run through both the installed wheel CLI and the bootstrapped portable ZIP entrypoint, alongside source-hash and stale-source checks. Local clean installation, unrelated working directory and paths with spaces passed; local.json retains the receipt. Root tests passed 53 cases. This is a local installation result, not an all-platform result or actual token measurement.

The corrected newline fixture is under ordinary CI run 34162541531 and candidate CI run 34162546275 at 7fa421e. Both were confirmed in progress during this audit. Do not restart either merely due to an observation timeout. These runs precede this additional verifier coverage; a subsequent ordinary distribution run will exercise the expanded gate. No published release was changed.
