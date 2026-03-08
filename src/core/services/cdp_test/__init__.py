"""
CDP Test Recorder — browser-based test recording, validation, and replay.

Uses Chrome DevTools Protocol (via ``cdp_client``) to:
- Record user interactions with a foreign web page
- Save them as reusable test suites
- Replay them for regression testing

Sub-modules:
    models.py    — TestStep, TestSuite, TestRunResult data shapes
    storage.py   — JSON file I/O for suites and results
    session.py   — Active recording session management (Phase 2)
    recorder.py  — CDP injection + event capture (Phase 2)
    replayer.py  — CDP-driven step execution (Phase 5)
"""
